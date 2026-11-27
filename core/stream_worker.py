# -*- coding: utf-8 -*-
"""
stream_worker.py - Worker especializado en la descarga y ensamblado de streams multimedia.
Soporta:
1. Streaming HLS (.m3u8) y DASH (.mpd) mediante FFmpeg con transcodificación y remuxing lossless.
2. Videos de plataformas (YouTube, Vimeo, Twitter, etc.) mediante yt-dlp y muxing de audio+video con FFmpeg.
Emite métricas de progreso fluidas compatibles con el modelo de tabla de BRO-Downloads.
"""

import os
import sys
import re
import time
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

from PySide6.QtCore import QThread, Signal
from core.media_tools import get_ffmpeg_path, is_ffmpeg_available


class StreamDownloadWorker(QThread):
    """
    Worker que se ejecuta en segundo plano para procesar y ensamblar streams de video.
    """

    bytes_progress = Signal(int, int, float, int)  # (downloaded_bytes, total_bytes, speed_bps, eta_sec)
    stream_finished = Signal(str)                  # (final_filename)
    stream_error = Signal(str)                     # (error_message)

    def __init__(
        self,
        url: str,
        target_path: str,
        filename: str,
        cookies: Optional[str] = None,
        referer: Optional[str] = None,
        user_agent: Optional[str] = None,
        parent=None
    ):
        super().__init__(parent)
        self.url = url
        self.target_path = target_path
        self.filename = filename
        self.cookies = cookies
        self.referer = referer
        self.user_agent = user_agent

        self._stop_requested = False
        self._subprocess: Optional[subprocess.Popen] = None
        self._last_progress_time = 0.0

    def request_stop(self):
        """Cancela limpiamente la descarga en curso."""
        self._stop_requested = True
        if self._subprocess and self._subprocess.poll() is None:
            try:
                self._subprocess.terminate()
            except Exception:
                pass

    def run(self):
        # Determinar si es una plataforma de video (YouTube, Vimeo, etc.) o stream directo (.m3u8)
        lower_url = self.url.lower()
        is_platform = (
            "youtube.com" in lower_url or
            "youtu.be" in lower_url or
            "vimeo.com" in lower_url or
            "twitter.com" in lower_url or
            "x.com" in lower_url or
            "tiktok.com" in lower_url or
            "reddit.com" in lower_url or
            "instagram.com" in lower_url
        )

        is_hls = ".m3u8" in lower_url or ".mpd" in lower_url

        try:
            if is_platform:
                self._download_with_ytdlp()
            elif is_hls or is_ffmpeg_available():
                self._download_hls_with_ffmpeg()
            else:
                # Fallback con yt-dlp si está disponible
                self._download_with_ytdlp()
        except Exception as e:
            if not self._stop_requested:
                self.stream_error.emit(str(e))

    # =========================================================================
    # 1. DESCARGA MEDIANTE YT-DLP (YouTube y plataformas web)
    # =========================================================================

    def _download_with_ytdlp(self):
        try:
            import yt_dlp
        except ImportError:
            self.stream_error.emit("yt-dlp no está instalado. Ejecuta 'pip install yt-dlp'.")
            return

        ffmpeg_bin = get_ffmpeg_path()

        # Construir plantilla de guardado en la carpeta de destino
        out_template = os.path.join(self.target_path, "%(title)s.%(ext)s")
        if self.filename and not self.filename.endswith(".mp4"):
            clean_name = os.path.splitext(self.filename)[0]
            out_template = os.path.join(self.target_path, f"{clean_name}.%(ext)s")

        final_filename = [self.filename]

        def ytdl_progress_hook(d):
            if self._stop_requested:
                raise Exception("Descarga cancelada por el usuario.")

            status = d.get("status")
            if status == "downloading":
                now = time.time()
                if now - self._last_progress_time >= 0.25:  # Throttle 4 veces por segundo
                    self._last_progress_time = now
                    downloaded = d.get("downloaded_bytes", 0)
                    total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                    speed = float(d.get("speed") or 0.0)
                    eta = int(d.get("eta") or 0)
                    self.bytes_progress.emit(downloaded, total, speed, eta)
            elif status == "finished":
                filename_res = d.get("filename", "")
                if filename_res:
                    final_filename[0] = os.path.basename(filename_res)

        headers = {}
        if self.user_agent:
            headers["User-Agent"] = self.user_agent
        if self.referer:
            headers["Referer"] = self.referer
        if self.cookies:
            headers["Cookie"] = self.cookies

        ydl_opts = {
            "outtmpl": out_template,
            "progress_hooks": [ytdl_progress_hook],
            "quiet": True,
            "no_warnings": True,
            # Preferir video y audio unidos en MP4 de la mejor calidad
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
        }

        if ffmpeg_bin:
            ydl_opts["ffmpeg_location"] = os.path.dirname(ffmpeg_bin) if os.path.isdir(ffmpeg_bin) else ffmpeg_bin

        if headers:
            ydl_opts["http_headers"] = headers

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])

            if not self._stop_requested:
                self.stream_finished.emit(final_filename[0])
        except Exception as e:
            if not self._stop_requested:
                self.stream_error.emit(f"Error yt-dlp: {e}")

    # =========================================================================
    # 2. DESCARGA DIRECTA DE STREAMS HLS / DASH (.m3u8) MEDIANTE FFMPEG
    # =========================================================================

    def _download_hls_with_ffmpeg(self):
        ffmpeg_bin = get_ffmpeg_path()
        if not ffmpeg_bin:
            self.stream_error.emit(
                "FFmpeg no está instalado. Puedes descargarlo en Opciones > General o instalarlo en Windows."
            )
            return

        # Asegurar extensión .mp4 en el archivo final
        out_filename = self.filename
        if not out_filename.lower().endswith(".mp4"):
            out_filename = os.path.splitext(out_filename)[0] + ".mp4"

        final_dest = os.path.join(self.target_path, out_filename)

        # Construir cabeceras HTTP para FFmpeg si existen
        headers_list = []
        if self.user_agent:
            headers_list.append(f"User-Agent: {self.user_agent}")
        if self.referer:
            headers_list.append(f"Referer: {self.referer}")
        if self.cookies:
            headers_list.append(f"Cookie: {self.cookies}")

        cmd = [ffmpeg_bin, "-y"]

        if headers_list:
            headers_str = "\r\n".join(headers_list) + "\r\n"
            cmd.extend(["-headers", headers_str])

        # Argumentos de streaming
        cmd.extend([
            "-i", self.url,
            "-c", "copy",
            "-bsf:a", "aac_adtstoasc",
            "-progress", "pipe:1",
            "-nostats",
            final_dest
        ])

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW

        self._subprocess = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            text=True,
            encoding="utf-8",
            errors="ignore"
        )

        total_bytes_approx = 0
        last_bytes = 0
        last_time = time.time()

        # Parsear salida progress pipe:1 de ffmpeg
        if self._subprocess.stdout:
            for line in self._subprocess.stdout:
                if self._stop_requested:
                    break

                line = line.strip()
                if line.startswith("total_size="):
                    try:
                        raw_val = line.split("=")[1].strip()
                        if raw_val != "N/A":
                            current_bytes = int(raw_val)
                            now = time.time()
                            dt = now - last_time
                            if dt >= 0.25:
                                speed = max(0.0, (current_bytes - last_bytes) / dt) if dt > 0 else 0.0
                                last_bytes = current_bytes
                                last_time = now

                                # Si el tamaño total es dinámico, asumimos un progreso incremental
                                self.bytes_progress.emit(
                                    current_bytes,
                                    max(current_bytes, total_bytes_approx),
                                    speed,
                                    0
                                )
                    except Exception:
                        pass
                elif line.startswith("progress=end"):
                    break

        self._subprocess.wait()

        if self._stop_requested:
            # Si se canceló, limpiar archivo incompleto
            if os.path.exists(final_dest):
                try:
                    os.remove(final_dest)
                except Exception:
                    pass
            return

        if self._subprocess.returncode == 0:
            self.stream_finished.emit(out_filename)
        else:
            stderr_err = ""
            if self._subprocess.stderr:
                stderr_err = self._subprocess.stderr.read()
            self.stream_error.emit(f"FFmpeg falló (código {self._subprocess.returncode}): {stderr_err[:200]}")
