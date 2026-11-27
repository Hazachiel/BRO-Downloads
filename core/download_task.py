import os
import re
import json
import time
import requests
from pathlib import Path
from typing import List, Dict, Optional, Any
from urllib.parse import unquote, urlparse

from PySide6.QtCore import QObject, Signal, QTimer
from models.download_item import DownloadItem, DownloadStatus
from .download_worker import DownloadWorker
from .stream_worker import StreamDownloadWorker


class DownloadTask(QObject):
    """
    Controlador y orquestador de una descarga individual.
    Maneja la sonda previa (HTTP HEAD), preasignación en disco (sparse allocation),
    división en chunks concurrentes, persistencia en archivo sidecar .brodownloads
    y actualización dinámica de URLs expiradas.
    """

    progress_updated = Signal(DownloadItem)
    status_changed = Signal(str, DownloadStatus)
    task_finished = Signal(str)
    task_error = Signal(str, str)
    needs_url_refresh = Signal(str, str)

    def __init__(self, item: DownloadItem, num_connections: int = 8, parent=None):
        super().__init__(parent)
        self.item = item
        self.num_connections = max(1, num_connections)

        self._target_file_path = os.path.join(self.item.save_path, self.item.filename)
        self._metadata_path = self._target_file_path + ".brodownloads"

        self._workers: List[DownloadWorker] = []
        self._segments: List[Dict[str, Any]] = []
        self._supports_ranges: bool = False
        self._etag: str = ""

        # Métricas de velocidad y throttling
        self._last_time = time.time()
        self._last_bytes = self.item.downloaded_size
        self._speed_samples: List[float] = []

        # Timer para notificaciones fluidas a la UI (4 veces por segundo)
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(250)
        self._progress_timer.timeout.connect(self._on_progress_tick)

        # Timer para guardar metadatos en disco periódicamente (cada 2 segundos)
        self._metadata_timer = QTimer(self)
        self._metadata_timer.setInterval(2000)
        self._metadata_timer.timeout.connect(self._save_metadata)

        self._stream_worker: Optional[StreamDownloadWorker] = None

    def _is_stream_download(self) -> bool:
        """Determina si la descarga corresponde a un stream HLS/DASH o video de plataforma."""
        url = self.item.url.lower()
        clean = url.split("?")[0].split("#")[0]
        if clean.endswith(".m3u8") or clean.endswith(".mpd"):
            return True
        if any(h in url for h in ("youtube.com", "youtu.be", "vimeo.com", "tiktok.com", "twitter.com", "x.com", "reddit.com", "instagram.com")):
            return True
        return False

    # =========================================================================
    # CICLO DE VIDA DE LA DESCARGA
    # =========================================================================

    def start(self):
        """Inicia o reanuda la descarga del archivo."""
        if self.item.status == DownloadStatus.DOWNLOADING:
            return

        self.item.status = DownloadStatus.CONNECTING
        self.status_changed.emit(self.item.id, DownloadStatus.CONNECTING)

        # 0. Si es un stream multimedia o video de plataforma, delegar al StreamDownloadWorker
        if self._is_stream_download():
            self._launch_stream_worker()
            return

        # 1. Verificar si ya existen metadatos de una sesión previa (.brodownloads)
        if os.path.exists(self._metadata_path):
            if self._load_metadata():
                self._launch_workers()
                return

        # 2. Si es una descarga nueva, hacer la sonda HTTP (HEAD / GET 0-0)
        self._probe_and_initialize()

    def _launch_stream_worker(self):
        """Lanza el worker de ensamblado de streaming (FFmpeg / yt-dlp)."""
        self.item.status = DownloadStatus.DOWNLOADING
        self.status_changed.emit(self.item.id, DownloadStatus.DOWNLOADING)

        self._stream_worker = StreamDownloadWorker(
            url=self.item.url,
            target_path=self.item.save_path,
            filename=self.item.filename,
            cookies=self.item.cookies,
            referer=self.item.referer,
            user_agent=self.item.user_agent,
            parent=self
        )
        self._stream_worker.bytes_progress.connect(self._on_stream_bytes)
        self._stream_worker.stream_finished.connect(self._on_stream_finished)
        self._stream_worker.stream_error.connect(self._on_stream_error)
        self._stream_worker.start()

    def _on_stream_bytes(self, downloaded: int, total: int, speed: float, eta: int):
        self.item.downloaded_size = downloaded
        if total > 0:
            self.item.total_size = total
        self.item.speed = speed
        self.item.eta_seconds = eta
        self.progress_updated.emit(self.item)

    def _on_stream_finished(self, final_filename: str):
        if final_filename:
            self.item.filename = final_filename
        final_path = os.path.join(self.item.save_path, self.item.filename)
        if os.path.exists(final_path):
            try:
                fsize = os.path.getsize(final_path)
                self.item.total_size = fsize
                self.item.downloaded_size = fsize
            except Exception:
                pass

        self.item.status = DownloadStatus.COMPLETED
        self.item.speed = 0.0
        self.item.eta_seconds = 0
        self.status_changed.emit(self.item.id, DownloadStatus.COMPLETED)
        self.progress_updated.emit(self.item)
        self.task_finished.emit(self.item.id)

    def _on_stream_error(self, err_msg: str):
        self._handle_error(err_msg)

    def pause(self):
        """Pausa limpiamente todos los workers y guarda el progreso en .brodownloads."""
        self._progress_timer.stop()
        self._metadata_timer.stop()

        if self._stream_worker:
            self._stream_worker.request_stop()
            self._stream_worker.wait(1500)
            self._stream_worker = None

        for worker in self._workers:
            worker.request_stop()

        for worker in self._workers:
            worker.wait(1500)

        self._workers.clear()
        self._save_metadata()

        self.item.status = DownloadStatus.PAUSED
        self.item.speed = 0.0
        self.item.eta_seconds = 0
        self.status_changed.emit(self.item.id, DownloadStatus.PAUSED)
        self.progress_updated.emit(self.item)

    def stop(self):
        """Detiene la descarga."""
        self.pause()
        self.item.status = DownloadStatus.CANCELED
        self.status_changed.emit(self.item.id, DownloadStatus.CANCELED)

    def update_url(self, new_url: str):
        """
        Función estrella: actualiza la URL expirada (ej. token caducado)
        y reanuda la descarga sin perder los bytes ya guardados en disco.
        """
        self.item.url = new_url
        if self._segments:
            self._save_metadata()

        self.item.status = DownloadStatus.QUEUED
        self.item.error_message = None
        self.status_changed.emit(self.item.id, DownloadStatus.QUEUED)

    # =========================================================================
    # SONDA PREVIA Y PREASIGNACIÓN DE ESPACIO EN DISCO
    # =========================================================================

    def _probe_and_initialize(self):
        """Envía una petición inicial para detectar tamaño, rangos y nombre real del archivo."""
        headers = {
            "User-Agent": self.item.user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BRO-Downloads/1.0",
            "Range": "bytes=0-0"
        }
        if self.item.referer:
            headers["Referer"] = self.item.referer
        if self.item.cookies:
            headers["Cookie"] = self.item.cookies

        try:
            # Petición ligera
            resp = requests.get(self.item.url, headers=headers, stream=True, timeout=12)

            # Verificar si el enlace está vencido o no autorizado
            if resp.status_code in (401, 403, 410):
                self.item.status = DownloadStatus.NEEDS_REFRESH
                self.item.error_message = f"Enlace expirado o no autorizado (HTTP {resp.status_code})"
                self.status_changed.emit(self.item.id, DownloadStatus.NEEDS_REFRESH)
                self.needs_url_refresh.emit(self.item.id, self.item.error_message)
                resp.close()
                return

            if resp.status_code not in (200, 206):
                self._handle_error(f"Error HTTP del servidor: {resp.status_code}")
                resp.close()
                return

            # Detección de soporte para descarga segmentada (Range)
            accept_ranges = resp.headers.get("Accept-Ranges", "").lower()
            content_range = resp.headers.get("Content-Range", "")
            self._supports_ranges = (resp.status_code == 206 or "bytes" in accept_ranges or "bytes" in content_range)

            # Tamaño total
            if content_range and "/" in content_range:
                try:
                    self.item.total_size = int(content_range.split("/")[-1])
                except ValueError:
                    self.item.total_size = int(resp.headers.get("Content-Length", 0))
            else:
                self.item.total_size = int(resp.headers.get("Content-Length", 0))

            self._etag = resp.headers.get("ETag", "")

            # Detección del nombre real desde Content-Disposition
            # IMPORTANTE: Solo actualizar el nombre si el usuario NO escribió un nombre personalizado explícito
            if not self.item.has_custom_filename:
                disposition = resp.headers.get("Content-Disposition", "")
                real_name = self._extract_filename_from_disposition(disposition)
                if real_name:
                    self.item.filename = real_name
                    self._target_file_path = os.path.join(self.item.save_path, self.item.filename)
                    self._metadata_path = self._target_file_path + ".brodownloads"

            resp.close()

            # Preasignar archivo en disco en milisegundos (sparse file)
            self._preallocate_target_file()

            # Generar segmentos
            self._create_segments()
            self._save_metadata()

            # Iniciar workers
            self._launch_workers()

        except Exception as e:
            self._handle_error(f"Error al conectar con el servidor: {e}")

    def _sanitize_filename(self, filename: str) -> str:
        """Limpia caracteres ilegales en nombres de archivo de Windows (< > : \" / \\ | ? *)."""
        clean = re.sub(r'[<>:"/\\|?*]', '_', filename)
        return clean.strip() or "archivo_descarga"

    def _extract_filename_from_disposition(self, disposition: str) -> Optional[str]:
        if not disposition:
            return None

        raw_name = None
        # RFC 5987 / 6266: filename*=UTF-8''...
        match_utf = re.search(r"filename\*\s*=\s*UTF-8''([^;\r\n]+)", disposition, re.IGNORECASE)
        if match_utf:
            raw_name = match_utf.group(1).strip("\"'")
        else:
            # filename="..."
            match_std = re.search(r'filename\s*=\s*"([^"]+)"', disposition, re.IGNORECASE)
            if match_std:
                raw_name = match_std.group(1)
            else:
                match_bare = re.search(r'filename\s*=\s*([^;\r\n]+)', disposition, re.IGNORECASE)
                if match_bare:
                    raw_name = match_bare.group(1).strip("\"'")

        if raw_name:
            # Decodificar secuencias %XX como %5B, %20, etc.
            decoded = unquote(raw_name)
            return self._sanitize_filename(decoded)
        return None

    def _preallocate_target_file(self):
        """Crea la estructura del archivo en disco de forma instantánea."""
        os.makedirs(self.item.save_path, exist_ok=True)
        if self.item.total_size > 0:
            with open(self._target_file_path, "wb") as f:
                f.seek(self.item.total_size - 1)
                f.write(b"\0")
        else:
            with open(self._target_file_path, "wb") as f:
                pass

    def _create_segments(self):
        """Divide el archivo en rangos de bytes según el número de conexiones permitidas."""
        self._segments = []
        total = self.item.total_size

        # Si el servidor no soporta rangos o el archivo es pequeño (< 3 MB), usar 1 conexión
        if not self._supports_ranges or total < 3 * 1024 * 1024 or self.num_connections <= 1:
            self._segments.append({
                "id": 0,
                "start": 0,
                "end": max(0, total - 1) if total > 0 else 0,
                "current": 0,
                "completed": False
            })
            return

        chunk_size = total // self.num_connections
        for i in range(self.num_connections):
            start = i * chunk_size
            end = total - 1 if i == self.num_connections - 1 else (start + chunk_size - 1)
            self._segments.append({
                "id": i,
                "start": start,
                "end": end,
                "current": start,
                "completed": False
            })

    # =========================================================================
    # PERSISTENCIA (.brodownloads)
    # =========================================================================

    def _save_metadata(self):
        """Guarda el estado exacto de cada segmento en el archivo sidecar .brodownloads."""
        if not self._segments:
            return

        # Sincronizar posiciones actuales desde los workers activos
        worker_map = {w.segment_id: w for w in self._workers}
        for seg in self._segments:
            w = worker_map.get(seg["id"])
            if w:
                seg["current"] = w.current_byte
                seg["completed"] = w.is_completed

        data = {
            "id": self.item.id,
            "url": self.item.url,
            "filename": self.item.filename,
            "total_size": self.item.total_size,
            "supports_ranges": self._supports_ranges,
            "etag": self._etag,
            "segments": self._segments,
            "last_updated": time.time()
        }

        try:
            with open(self._metadata_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[DownloadTask] Error guardando metadatos: {e}")

    def _load_metadata(self) -> bool:
        """Carga y reanuda el progreso desde el archivo .brodownloads existente."""
        try:
            with open(self._metadata_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._supports_ranges = data.get("supports_ranges", False)
            self._etag = data.get("etag", "")
            self.item.total_size = data.get("total_size", self.item.total_size)
            self._segments = data.get("segments", [])

            # Calcular bytes ya descargados acumulados
            downloaded = 0
            for seg in self._segments:
                downloaded += max(0, seg["current"] - seg["start"])
            self.item.downloaded_size = downloaded

            return len(self._segments) > 0
        except Exception as e:
            print(f"[DownloadTask] Error cargando .brodownloads: {e}")
            return False

    # =========================================================================
    # WORKERS Y FLUJO DE DATOS
    # =========================================================================

    def _launch_workers(self):
        """Lanza los hilos de descarga para los segmentos que aún no están completos."""
        self._workers.clear()
        self.item.status = DownloadStatus.DOWNLOADING
        self.status_changed.emit(self.item.id, DownloadStatus.DOWNLOADING)

        self._last_time = time.time()
        self._last_bytes = self.item.downloaded_size
        self._speed_samples.clear()

        incomplete_count = 0
        for seg in self._segments:
            if not seg.get("completed", False):
                worker = DownloadWorker(
                    segment_id=seg["id"],
                    url=self.item.url,
                    target_path=self._target_file_path,
                    start_byte=seg["start"],
                    end_byte=seg["end"],
                    current_byte=seg["current"],
                    cookies=self.item.cookies,
                    referer=self.item.referer,
                    user_agent=self.item.user_agent,
                    parent=self
                )
                worker.bytes_received.connect(self._on_worker_bytes)
                worker.segment_finished.connect(self._on_worker_finished)
                worker.segment_error.connect(self._on_worker_error)
                self._workers.append(worker)
                worker.start()
                incomplete_count += 1

        if incomplete_count == 0:
            self._check_all_completed()
        else:
            self._progress_timer.start()
            self._metadata_timer.start()

    def _on_worker_bytes(self, segment_id: int, count: int):
        self.item.downloaded_size += count

    def _on_worker_finished(self, segment_id: int):
        for seg in self._segments:
            if seg["id"] == segment_id:
                seg["completed"] = True
                break
        self._check_all_completed()

    def _on_worker_error(self, segment_id: int, error_msg: str):
        if "AUTH_EXPIRED" in error_msg:
            # Token expirado: pausar y solicitar actualización
            self.pause()
            self.item.status = DownloadStatus.NEEDS_REFRESH
            self.item.error_message = "Enlace caducado. Requiere actualizar dirección."
            self.status_changed.emit(self.item.id, DownloadStatus.NEEDS_REFRESH)
            self.needs_url_refresh.emit(self.item.id, self.item.error_message)
        else:
            self.pause()
            self._handle_error(f"Error en segmento #{segment_id}: {error_msg}")

    def _check_all_completed(self):
        all_done = all(seg.get("completed", False) for seg in self._segments)
        if all_done:
            self._progress_timer.stop()
            self._metadata_timer.stop()

            self.item.status = DownloadStatus.COMPLETED
            self.item.speed = 0.0
            self.item.eta_seconds = 0
            if self.item.total_size > 0:
                self.item.downloaded_size = self.item.total_size

            # Eliminar archivo sidecar de metadatos (.brodownloads)
            if os.path.exists(self._metadata_path):
                try:
                    os.remove(self._metadata_path)
                except Exception:
                    pass

            self.status_changed.emit(self.item.id, DownloadStatus.COMPLETED)
            self.progress_updated.emit(self.item)
            self.task_finished.emit(self.item.id)

    def _on_progress_tick(self):
        """Calcula velocidad instantánea media y tiempo estimado restante (ETA)."""
        now = time.time()
        elapsed = now - self._last_time

        if elapsed >= 0.25:
            delta_bytes = self.item.downloaded_size - self._last_bytes
            instant_speed = delta_bytes / elapsed if elapsed > 0 else 0.0

            # Suavizado de velocidad con media móvil de 4 muestras
            self._speed_samples.append(instant_speed)
            if len(self._speed_samples) > 4:
                self._speed_samples.pop(0)

            avg_speed = sum(self._speed_samples) / len(self._speed_samples)
            self.item.speed = avg_speed

            # Cálculo de ETA
            if avg_speed > 0 and self.item.total_size > self.item.downloaded_size:
                remaining = self.item.total_size - self.item.downloaded_size
                self.item.eta_seconds = int(remaining / avg_speed)
            else:
                self.item.eta_seconds = 0

            self._last_time = now
            self._last_bytes = self.item.downloaded_size

            self.progress_updated.emit(self.item)

    def _handle_error(self, message: str):
        self.item.status = DownloadStatus.ERROR
        self.item.error_message = message
        self.item.speed = 0.0
        self.status_changed.emit(self.item.id, DownloadStatus.ERROR)
        self.task_error.emit(self.item.id, message)
        self.progress_updated.emit(self.item)
