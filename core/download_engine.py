import os
from typing import Dict, List, Optional
from PySide6.QtCore import QObject, Signal, QTimer

from models.download_item import DownloadItem, DownloadStatus
from core.settings_manager import SettingsManager
from core.queue_manager import QueueManager
from core.download_task import DownloadTask
from core.download_storage import DownloadStorage


class DownloadEngine(QObject):
    """
    Orquestador global del motor de descargas de BRO-Downloads.
    Administra la cola activa, aplica los límites de concurrencia simultánea
    (por cola y por servidor), maneja la resiliencia ante pérdida de red y
    coordina la persistencia y ciclo de vida de todas las descargas.
    """

    task_progress = Signal(DownloadItem)
    task_status_changed = Signal(str, DownloadStatus)
    task_finished = Signal(DownloadItem)
    task_error = Signal(DownloadItem, str)
    task_needs_url_refresh = Signal(DownloadItem, str)
    global_stats_updated = Signal(float, int, int)  # (total_speed_bytes, active_count, total_count)

    _instance: Optional["DownloadEngine"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, parent=None):
        if getattr(self, "_initialized", False):
            return
        super().__init__(parent)

        self.settings_manager = SettingsManager()
        self.queue_manager = QueueManager()
        self.storage = DownloadStorage()

        self._tasks: Dict[str, DownloadTask] = {}
        self._all_items: Dict[str, DownloadItem] = {}

        # Escuchar cambios de conectividad a internet
        self.queue_manager.internet_status_changed.connect(self._on_internet_status_changed)

        # Timer para recalcular estadísticas globales cada 500ms
        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(500)
        self._stats_timer.timeout.connect(self._emit_global_stats)
        self._stats_timer.start()

        self._initialized = True

    # =========================================================================
    # GESTIÓN DE TAREAS Y DESCARGAS
    # =========================================================================

    def register_item(self, item: DownloadItem):
        """Registra un DownloadItem en el motor."""
        self._all_items[item.id] = item

    def add_download(self, item: DownloadItem, start_now: bool = True):
        """Agrega una nueva descarga y la inicia inmediatamente o la deja en cola."""
        self.register_item(item)

        if start_now:
            item.status = DownloadStatus.QUEUED
            self._process_queues()
        else:
            item.status = DownloadStatus.PAUSED
            self.task_status_changed.emit(item.id, DownloadStatus.PAUSED)

        self.save_state()

    def resume_specific(self, download_ids: List[str]):
        """
        Reanuda EXCLUSIVAMENTE las descargas seleccionadas por el usuario.
        No reactiva otras descargas que estén pausadas en la cola.
        """
        for d_id in download_ids:
            item = self._all_items.get(d_id)
            if item and item.status != DownloadStatus.DOWNLOADING:
                self._start_task(item)

        self.save_state()

    def resume_all(self):
        """Reanuda todas las descargas pausadas en la lista que no estén completadas."""
        for item in self._all_items.values():
            if item.status in (DownloadStatus.PAUSED, DownloadStatus.ERROR, DownloadStatus.CANCELED):
                item.status = DownloadStatus.QUEUED
                self.task_status_changed.emit(item.id, DownloadStatus.QUEUED)

        self._process_queues()
        self.save_state()

    def pause_download(self, download_id: str):
        """Pausa una descarga activa."""
        task = self._tasks.get(download_id)
        if task:
            task.pause()
        else:
            item = self._all_items.get(download_id)
            if item:
                item.status = DownloadStatus.PAUSED
                item.speed = 0.0
                self.task_status_changed.emit(item.id, DownloadStatus.PAUSED)

        self.save_state()
        self._process_queues()

    def stop_download(self, download_id: str):
        """Detiene una descarga."""
        task = self._tasks.get(download_id)
        if task:
            task.stop()
        else:
            item = self._all_items.get(download_id)
            if item:
                item.status = DownloadStatus.CANCELED
                item.speed = 0.0
                self.task_status_changed.emit(item.id, DownloadStatus.CANCELED)

        self.save_state()
        self._process_queues()

    def pause_all(self):
        """Pausa todas las descargas activas simultáneamente."""
        for task in list(self._tasks.values()):
            task.pause()

        for item in self._all_items.values():
            if item.status in (DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING, DownloadStatus.QUEUED):
                item.status = DownloadStatus.PAUSED
                item.speed = 0.0
                self.task_status_changed.emit(item.id, DownloadStatus.PAUSED)

        self.save_state()

    def remove_download(self, download_id: str, delete_files: bool = False):
        """Detiene y elimina una descarga del motor (y opcionalmente sus archivos en disco)."""
        self.stop_download(download_id)

        task = self._tasks.pop(download_id, None)
        item = self._all_items.pop(download_id, None)

        if delete_files and item:
            target_path = os.path.join(item.save_path, item.filename)
            metadata_path = target_path + ".brodownloads"

            for path in (target_path, metadata_path):
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception as e:
                        print(f"[DownloadEngine] Error eliminando archivo {path}: {e}")

        self.save_state()
        self._process_queues()

    def update_download_url(self, download_id: str, new_url: str):
        """Actualiza la URL de una descarga existente y reintenta."""
        item = self._all_items.get(download_id)
        if not item:
            return

        item.url = new_url
        item.status = DownloadStatus.QUEUED
        item.error_message = None

        task = self._tasks.get(download_id)
        if task:
            task.update_url(new_url)

        self.task_status_changed.emit(item.id, DownloadStatus.QUEUED)
        self.save_state()
        self._process_queues()

    def save_state(self):
        """Guarda todas las descargas actuales en downloads.json."""
        self.storage.save_downloads(list(self._all_items.values()))

    # =========================================================================
    # DESPACHADOR DE COLAS Y CONTROL DE CONCURRENCIA
    # =========================================================================

    def _process_queues(self):
        """
        Revisa todas las colas y arranca las tareas en espera (QUEUED) respetando:
        1. Estado de conexión a internet.
        2. Límite de descargas simultáneas en la cola (max_concurrent_downloads).
        3. Límite de descargas simultáneas por servidor (max_concurrent_per_server).
        4. Orden de prioridad de la cola.
        """
        if not self.queue_manager.has_internet:
            return

        queues_map: Dict[str, List[DownloadItem]] = {}
        for item in self._all_items.values():
            queues_map.setdefault(item.queue_name, []).append(item)

        for queue_name, items in queues_map.items():
            cfg = self.queue_manager.get_or_create_queue(queue_name)

            active_items = [it for it in items if it.status in (DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING)]

            server_active_counts: Dict[str, int] = {}
            for it in active_items:
                server_active_counts[it.domain] = server_active_counts.get(it.domain, 0) + 1

            queued_items = [it for it in items if it.status == DownloadStatus.QUEUED]

            id_order = {item_id: idx for idx, item_id in enumerate(cfg.ordered_download_ids)}
            queued_items.sort(key=lambda it: id_order.get(it.id, 999999))

            for item in queued_items:
                if len(active_items) >= cfg.max_concurrent_downloads:
                    break

                server = item.domain
                current_server_count = server_active_counts.get(server, 0)
                if current_server_count >= cfg.max_concurrent_per_server:
                    continue

                self._start_task(item)
                active_items.append(item)
                server_active_counts[server] = current_server_count + 1

    def _start_task(self, item: DownloadItem):
        """Crea o reutiliza una DownloadTask y la inicia."""
        task = self._tasks.get(item.id)
        if not task:
            conns = self.settings_manager.get_connections_for_url(item.url)
            task = DownloadTask(item, num_connections=conns, parent=self)

            task.progress_updated.connect(self.task_progress.emit)
            task.status_changed.connect(self._on_task_status_changed)
            task.task_finished.connect(self._on_task_finished)
            task.task_error.connect(self._on_task_error)
            task.needs_url_refresh.connect(self._on_task_needs_refresh)

            self._tasks[item.id] = task

        task.start()

    # =========================================================================
    # EVENTOS Y MANEJO DE ERRORES DE TAREAS
    # =========================================================================

    def _on_task_status_changed(self, download_id: str, status: DownloadStatus):
        self.task_status_changed.emit(download_id, status)
        self.save_state()

    def _on_task_finished(self, download_id: str):
        item = self._all_items.get(download_id)
        if item:
            self.task_finished.emit(item)
        self.save_state()
        self._process_queues()

    def _on_task_error(self, download_id: str, error_msg: str):
        item = self._all_items.get(download_id)
        if item:
            self.task_error.emit(item, error_msg)
        self.save_state()
        self._process_queues()

    def _on_task_needs_refresh(self, download_id: str, reason: str):
        item = self._all_items.get(download_id)
        if item:
            self.task_needs_url_refresh.emit(item, reason)
        self.save_state()
        self._process_queues()

    def _on_internet_status_changed(self, online: bool):
        if online:
            self._process_queues()
        else:
            for task in self._tasks.values():
                if task.item.status == DownloadStatus.DOWNLOADING:
                    task.pause()
                    task.item.status = DownloadStatus.PAUSED
                    self.task_status_changed.emit(task.item.id, DownloadStatus.PAUSED)
            self.save_state()

    def _emit_global_stats(self):
        total_speed = 0.0
        active_count = 0
        total_count = len(self._all_items)

        for item in self._all_items.values():
            if item.status == DownloadStatus.DOWNLOADING:
                total_speed += item.speed
                active_count += 1

        self.global_stats_updated.emit(total_speed, active_count, total_count)
