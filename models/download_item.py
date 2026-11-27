from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Union
from urllib.parse import urlparse


class DownloadStatus(str, Enum):
    QUEUED = "En cola"
    CONNECTING = "Conectando"
    DOWNLOADING = "Descargando"
    PAUSED = "Pausado"
    COMPLETED = "Completado"
    ERROR = "Error"
    CANCELED = "Cancelado"
    NEEDS_REFRESH = "Requiere actualización"   # Cuando el token o cookie expiró


class DownloadCategory(str, Enum):
    ALL = "Todos"
    COMPRESSED = "Comprimidos"
    DOCUMENTS = "Documentos"
    MUSIC = "Música"
    PROGRAMS = "Programas"
    VIDEO = "Video"
    OTHER = "Otros"

    @classmethod
    def from_filename(cls, filename: str) -> "DownloadCategory":
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        if ext in ["zip", "rar", "7z", "tar", "gz", "bz2", "iso"]:
            return cls.COMPRESSED
        if ext in ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "epub"]:
            return cls.DOCUMENTS
        if ext in ["mp3", "wav", "flac", "aac", "ogg", "m4a"]:
            return cls.MUSIC
        if ext in ["exe", "msi", "dmg", "pkg", "deb", "rpm", "appimage", "apk"]:
            return cls.PROGRAMS
        if ext in ["mp4", "mkv", "avi", "mov", "webm", "flv"]:
            return cls.VIDEO
        return cls.OTHER


@dataclass
class DownloadItem:
    """
    Representa una tarea o archivo individual dentro del gestor.
    Sigue el patrón de objeto de datos puro para desacoplar la lógica de la UI.
    """
    id: str
    url: str
    filename: str
    save_path: str
    total_size: int = 0          # Tamaño en bytes (0 = desconocido)
    downloaded_size: int = 0     # Bytes descargados hasta ahora
    speed: float = 0.0           # Bytes por segundo
    status: DownloadStatus = DownloadStatus.QUEUED
    category: Union[str, DownloadCategory] = DownloadCategory.OTHER
    queue_name: str = "Cola Principal"
    eta_seconds: int = 0         # Tiempo estimado restante
    date_added: datetime = field(default_factory=datetime.now)
    error_message: Optional[str] = None
    retry_count: int = 0
    has_custom_filename: bool = False  # Si el usuario editó explícitamente el nombre
    cookies: Optional[str] = None       # Cookies de sesión para descargas protegidas
    referer: Optional[str] = None       # Cabecera Referer HTTP
    user_agent: Optional[str] = None    # Cabecera User-Agent del navegador

    @property
    def domain(self) -> str:
        """Devuelve el dominio/servidor de la descarga (ej. mediafire.com, drive.google.com)."""
        try:
            parsed = urlparse(self.url)
            netloc = parsed.netloc.lower()
            if netloc.startswith("www."):
                netloc = netloc[4:]
            return netloc or "Desconocido"
        except Exception:
            return "Desconocido"

    @property
    def progress_percentage(self) -> float:
        """Calcula el porcentaje de 0 a 100%."""
        if self.total_size <= 0:
            return 0.0
        return min(100.0, (self.downloaded_size / self.total_size) * 100.0)

    @property
    def formatted_total_size(self) -> str:
        return self._format_bytes(self.total_size)

    @property
    def formatted_downloaded_size(self) -> str:
        return self._format_bytes(self.downloaded_size)

    @property
    def formatted_speed(self) -> str:
        if self.status != DownloadStatus.DOWNLOADING or self.speed <= 0:
            return ""
        return f"{self._format_bytes(int(self.speed))}/s"

    @property
    def formatted_eta(self) -> str:
        if self.status != DownloadStatus.DOWNLOADING or self.eta_seconds <= 0:
            return ""
        hours, remainder = divmod(self.eta_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    @staticmethod
    def _format_bytes(num_bytes: int) -> str:
        """Convierte bytes a formato legible (KB, MB, GB)."""
        if num_bytes <= 0:
            return "Desconocido" if num_bytes < 0 else "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(num_bytes)
        for unit in units:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"
