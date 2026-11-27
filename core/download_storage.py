import os
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from models.download_item import DownloadItem, DownloadStatus, DownloadCategory


class DownloadStorage:
    """
    Gestor de persistencia para la lista de descargas y su estado.
    Guarda y recupera todas las descargas desde ~/.brodownloads/downloads.json
    garantizando que el historial, progreso y estado se mantengan entre sesiones.
    """

    def __init__(self, storage_dir: Optional[str] = None):
        self._storage_dir = Path(storage_dir) if storage_dir else Path.home() / ".brodownloads"
        self._file_path = self._storage_dir / "downloads.json"

    def save_downloads(self, items: List[DownloadItem]):
        """Persiste la lista completa de DownloadItems en formato JSON."""
        data = []
        for it in items:
            # Si el usuario cierra la app mientras descargaba o conectaba, guardar como PAUSADO
            saved_status = it.status.value
            if it.status in (DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING):
                saved_status = DownloadStatus.PAUSED.value

            data.append({
                "id": it.id,
                "url": it.url,
                "filename": it.filename,
                "save_path": it.save_path,
                "total_size": it.total_size,
                "downloaded_size": it.downloaded_size,
                "status": saved_status,
                "category": it.category.value if hasattr(it.category, "value") else str(it.category),
                "queue_name": it.queue_name,
                "date_added": it.date_added.isoformat(),
                "error_message": it.error_message,
                "retry_count": it.retry_count,
                "has_custom_filename": it.has_custom_filename,
                "cookies": it.cookies,
                "referer": it.referer,
                "user_agent": it.user_agent
            })

        try:
            self._storage_dir.mkdir(parents=True, exist_ok=True)
            with open(self._file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[DownloadStorage] Error guardando descargas: {e}")

    def load_downloads(self) -> List[DownloadItem]:
        """Carga y reconstruye la lista de DownloadItems desde el archivo JSON."""
        if not self._file_path.exists():
            return []

        items: List[DownloadItem] = []
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for d in data:
                # Reconstruir enums de estado y categoría
                try:
                    status = DownloadStatus(d.get("status", DownloadStatus.PAUSED.value))
                except ValueError:
                    status = DownloadStatus.PAUSED

                cat_raw = d.get("category", DownloadCategory.OTHER.value)
                try:
                    category = DownloadCategory(cat_raw)
                except ValueError:
                    category = str(cat_raw)

                # Reconstruir fecha
                raw_date = d.get("date_added")
                if raw_date:
                    try:
                        date_added = datetime.fromisoformat(raw_date)
                    except Exception:
                        date_added = datetime.now()
                else:
                    date_added = datetime.now()

                item = DownloadItem(
                    id=d.get("id"),
                    url=d.get("url", ""),
                    filename=d.get("filename", "descarga"),
                    save_path=d.get("save_path", str(Path.home() / "Downloads")),
                    total_size=d.get("total_size", 0),
                    downloaded_size=d.get("downloaded_size", 0),
                    speed=0.0,
                    status=status,
                    category=category,
                    queue_name=d.get("queue_name", "Cola Principal"),
                    eta_seconds=0,
                    date_added=date_added,
                    error_message=d.get("error_message"),
                    retry_count=d.get("retry_count", 0),
                    has_custom_filename=d.get("has_custom_filename", False),
                    cookies=d.get("cookies"),
                    referer=d.get("referer"),
                    user_agent=d.get("user_agent")
                )

                # Verificar si el archivo final ya existe completo en el disco
                target_path = os.path.join(item.save_path, item.filename)
                if item.total_size > 0 and os.path.exists(target_path):
                    try:
                        file_size_on_disk = os.path.getsize(target_path)
                        if file_size_on_disk >= item.total_size:
                            item.status = DownloadStatus.COMPLETED
                            item.downloaded_size = item.total_size
                    except OSError:
                        pass

                items.append(item)

        except Exception as e:
            print(f"[DownloadStorage] Error cargando descargas: {e}")

        return items
