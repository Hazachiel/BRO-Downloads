# -*- coding: utf-8 -*-
"""
media_tools.py - Utilidades y gestor de herramientas multimedia (FFmpeg) para BRO-Downloads.
Permite detectar ffmpeg en el PATH o en ~/.brodownloads/bin, y ofrece descarga
automática e instalación desatendida de un binario ligero y portátil para Windows.
"""

import os
import sys
import shutil
import zipfile
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtCore import QThread, Signal
from core.settings_manager import SettingsManager


def get_bin_dir() -> Path:
    """Devuelve la carpeta binaria local ~/.brodownloads/bin."""
    bin_dir = Path.home() / ".brodownloads" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    return bin_dir


def get_ffmpeg_path() -> Optional[str]:
    """
    Busca el ejecutable de ffmpeg en el siguiente orden:
    1. Ruta personalizada guardada en settings.json
    2. Binario local en ~/.brodownloads/bin/ffmpeg.exe
    3. En el PATH del sistema operativo (shutil.which)
    """
    settings = SettingsManager().settings
    if hasattr(settings, "ffmpeg_path") and settings.ffmpeg_path:
        custom_path = Path(settings.ffmpeg_path)
        if custom_path.exists() and custom_path.is_file():
            return str(custom_path)

    # 2. Local en ~/.brodownloads/bin
    local_bin = get_bin_dir() / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if local_bin.exists() and local_bin.is_file():
        return str(local_bin)

    # 3. En PATH
    which_ffmpeg = shutil.which("ffmpeg")
    if which_ffmpeg:
        return which_ffmpeg

    return None


def is_ffmpeg_available() -> bool:
    """Verifica si ffmpeg está instalado y disponible para ejecutarse."""
    return get_ffmpeg_path() is not None


class FfmpegDownloaderWorker(QThread):
    """
    Descarga e instala automáticamente una compilación portátil de FFmpeg para Windows
    sin requerir instalación manual por parte del usuario, al estilo JDownloader.
    """

    progress_updated = Signal(int, str)  # (porcentaje 0-100, texto descriptivo)
    download_finished = Signal(bool, str)  # (éxito, mensaje o ruta)

    # Compilación oficial optimizada y ligera de ffmpeg essentials para Windows x64
    FFMPEG_ZIP_URL = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        bin_dir = get_bin_dir()
        temp_zip = bin_dir / "ffmpeg_temp.zip"

        try:
            self.progress_updated.emit(5, "Conectando con el servidor de descargas...")

            # 1. Descargar el archivo zip con reporte de progreso
            req = urllib.request.Request(
                self.FFMPEG_ZIP_URL,
                headers={"User-Agent": "Mozilla/5.0 BRO-Downloads/1.0"}
            )

            with urllib.request.urlopen(req, timeout=15) as response, open(temp_zip, "wb") as out_file:
                total_size = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                block_size = 128 * 1024  # 128 KB

                while True:
                    if self._is_cancelled:
                        out_file.close()
                        if temp_zip.exists():
                            temp_zip.unlink()
                        self.download_finished.emit(False, "Descarga cancelada por el usuario.")
                        return

                    buffer = response.read(block_size)
                    if not buffer:
                        break

                    out_file.write(buffer)
                    downloaded += len(buffer)

                    if total_size > 0:
                        percent = int((downloaded / total_size) * 85) + 5
                        mb_done = downloaded / (1024 * 1024)
                        mb_total = total_size / (1024 * 1024)
                        self.progress_updated.emit(
                            percent,
                            f"Descargando FFmpeg: {mb_done:.1f} MB / {mb_total:.1f} MB ({percent}%)"
                        )

            # 2. Extraer ffmpeg.exe y ffprobe.exe del ZIP
            self.progress_updated.emit(90, "Extrayendo ejecutables de FFmpeg...")

            extracted_ffmpeg = None
            with zipfile.ZipFile(temp_zip, "r") as zf:
                for member in zf.namelist():
                    filename = Path(member).name.lower()
                    if filename in ("ffmpeg.exe", "ffprobe.exe"):
                        target_file = bin_dir / filename
                        with zf.open(member) as source, open(target_file, "wb") as target:
                            shutil.copyfileobj(source, target)
                        if filename == "ffmpeg.exe":
                            extracted_ffmpeg = str(target_file)

            # Eliminar archivo ZIP temporal
            if temp_zip.exists():
                temp_zip.unlink()

            if extracted_ffmpeg and os.path.exists(extracted_ffmpeg):
                # Guardar ruta en configuraciones
                settings_mgr = SettingsManager()
                settings_mgr.settings.ffmpeg_path = extracted_ffmpeg
                settings_mgr.save()

                self.progress_updated.emit(100, "¡FFmpeg instalado exitosamente!")
                self.download_finished.emit(True, extracted_ffmpeg)
            else:
                self.download_finished.emit(False, "No se encontró ffmpeg.exe en el paquete descargado.")

        except Exception as e:
            if temp_zip.exists():
                try:
                    temp_zip.unlink()
                except Exception:
                    pass
            self.download_finished.emit(False, f"Error descargando FFmpeg: {e}")
