import os
import uuid
from typing import List, Optional
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QSplitter,
    QStatusBar, QLabel, QMessageBox, QCheckBox
)
from PySide6.QtCore import Qt

from models.download_item import DownloadItem, DownloadStatus, DownloadCategory
from models.table_model import DownloadTableModel
from models.filter_proxy_model import DownloadFilterProxyModel
from core.settings_manager import SettingsManager
from core.queue_manager import QueueManager
from core.download_engine import DownloadEngine
from core.api_server import ApiServer

from ui.components.menu_bar import MainMenuBar
from ui.components.tool_bar import QuickToolBar
from ui.components.sidebar import SidebarWidget
from ui.components.filter_bar import FilterBarWidget
from ui.components.download_table import DownloadTableView
from ui.dialogs.add_download_dialog import AddDownloadDialog
from ui.dialogs.options_dialog import OptionsDialog
from ui.dialogs.scheduler_dialog import SchedulerDialog, RefreshUrlDialog
from ui.dialogs.shutdown_countdown_dialog import ShutdownCountdownDialog
from ui.styles import MODERN_STYLE


class MainWindow(QMainWindow):
    """
    Ventana principal de BRO-Downloads.
    Totalmente conectada con el motor de descargas DownloadEngine, el micro-servidor API
    para extensiones de navegador, persistencia en downloads.json y el gestor de colas.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("BRO-Downloads v1.0")
        self.resize(930, 560)

        # 1. Cargar gestores del Core
        self.settings_manager = SettingsManager()
        self.queue_manager = QueueManager()
        self.engine = DownloadEngine(parent=self)

        # 2. Servidor API local para integración con navegadores (Chrome / Firefox / Edge)
        self.api_server = ApiServer(parent=self)
        self.api_server.download_received.connect(self._on_browser_download_received)
        if self.settings_manager.settings.browser_integration:
            self.api_server.start()

        # 3. Aplicar tema oscuro moderno estilo Windows Fluent
        self.setStyleSheet(MODERN_STYLE)

        # 4. Modelos de Datos (Arquitectura Model/View)
        self.table_model = DownloadTableModel()
        self.proxy_model = DownloadFilterProxyModel()
        self.proxy_model.setSourceModel(self.table_model)

        # 5. Inicializar Componentes de Interfaz
        self._init_ui()
        self._connect_signals()
        self._connect_engine_signals()

        # 6. Sincronizar categorías y colas iniciales con el sidebar
        self._sync_categories_to_sidebar()
        self._sync_queues_to_sidebar()

        # 7. Cargar descargas persistentes desde downloads.json
        self._load_persisted_downloads()

    def _init_ui(self):
        # A. Barra de Menú Superior
        self.menu_bar = MainMenuBar(self)
        self.setMenuBar(self.menu_bar)

        # B. Barra de Herramientas Rápida
        self.tool_bar = QuickToolBar(self)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.tool_bar)

        # C. Contenedor Central con Divisor (Splitter)
        central_widget = QWidget(self)
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(10, 10, 10, 10)
        central_layout.setSpacing(8)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # Panel Izquierdo: Árbol de Colas y Categorías
        self.sidebar = SidebarWidget(self)
        self.splitter.addWidget(self.sidebar)

        # Panel Derecho: Filtros + Tabla
        right_container = QWidget(self)
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(1, 0, 0, 0)
        right_layout.setSpacing(8)

        self.filter_bar = FilterBarWidget(self)
        right_layout.addWidget(self.filter_bar)

        self.download_table = DownloadTableView(self)
        self.download_table.setModel(self.proxy_model)
        right_layout.addWidget(self.download_table)

        self.splitter.addWidget(right_container)

        # Distribución de anchos inicial (250px sidebar, 850px tabla)
        self.splitter.setSizes([250, 850])
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)

        central_layout.addWidget(self.splitter)
        self.setCentralWidget(central_widget)

        # D. Barra de Estado
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)

        self.status_label_total = QLabel("Total: 0 descargas", self)
        self.status_label_speed = QLabel("Velocidad global: 0 KB/s", self)
        self.status_bar.addWidget(self.status_label_total, 1)
        self.status_bar.addPermanentWidget(self.status_label_speed)

    def _connect_signals(self):
        # Acciones de la Barra de Menús y Barra de Herramientas
        self.tool_bar.action_add_url.triggered.connect(self._open_add_download_dialog)
        self.menu_bar.action_add_url.triggered.connect(self._open_add_download_dialog)

        # Botón "Reanudar" de la barra superior: reanuda seleccionadas o todas
        self.tool_bar.action_resume.triggered.connect(self._on_toolbar_resume_clicked)
        self.menu_bar.action_resume.triggered.connect(self._on_toolbar_resume_clicked)

        self.tool_bar.action_pause.triggered.connect(self._pause_selected)
        self.menu_bar.action_pause.triggered.connect(self._pause_selected)

        self.tool_bar.action_stop.triggered.connect(self._stop_selected)
        self.menu_bar.action_stop.triggered.connect(self._stop_selected)

        self.tool_bar.action_stop_all.triggered.connect(self._stop_all)
        self.menu_bar.action_stop_all.triggered.connect(self._stop_all)

        self.tool_bar.action_delete.triggered.connect(self._delete_selected)
        self.menu_bar.action_delete.triggered.connect(self._delete_selected)

        # Opciones y Programador
        self.tool_bar.action_options.triggered.connect(self._open_options_dialog)
        self.menu_bar.action_options.triggered.connect(self._open_options_dialog)

        self.tool_bar.action_scheduler.triggered.connect(self._open_scheduler_dialog)
        self.menu_bar.action_scheduler.triggered.connect(self._open_scheduler_dialog)

        self.menu_bar.action_toggle_sidebar.toggled.connect(self.sidebar.setVisible)
        self.menu_bar.action_exit.triggered.connect(self.close)
        self.menu_bar.action_about.triggered.connect(self._show_about_dialog)

        # Panel Lateral (Filtros y Sincronización)
        self.sidebar.filter_requested.connect(self._apply_sidebar_filter)
        self.sidebar.queue_deleted.connect(self.queue_manager.remove_queue)

        # Filtros de Búsqueda
        self.filter_bar.search_changed.connect(self.proxy_model.set_search_text)
        self.filter_bar.status_filter_changed.connect(self.proxy_model.set_status_filter)

        # Eventos de la Tabla
        self.download_table.resume_requested.connect(self._on_context_menu_resume)
        self.download_table.pause_requested.connect(self._pause_items)
        self.download_table.stop_requested.connect(self._stop_items)
        self.download_table.delete_requested.connect(self._delete_items)
        self.download_table.refresh_url_requested.connect(self._open_refresh_url_dialog)
        self.download_table.doubleClicked.connect(self._on_table_double_clicked)

    def _connect_engine_signals(self):
        """Conecta las señales del motor de descargas en vivo con la UI."""
        self.engine.task_progress.connect(self._on_engine_progress)
        self.engine.task_status_changed.connect(self._on_engine_status_changed)
        self.engine.task_finished.connect(self._on_engine_task_finished)
        self.engine.task_error.connect(self._on_engine_task_error)
        self.engine.task_needs_url_refresh.connect(self._on_engine_needs_refresh)
        self.engine.global_stats_updated.connect(self._on_engine_stats_updated)

    # =========================================================================
    # INTEGRACIÓN CON LA EXTENSIÓN DEL NAVEGADOR
    # =========================================================================

    def _on_browser_download_received(self, data: dict):
        """
        Invocado cuando la extensión del navegador intercepta una descarga
        y la envía mediante el micro-servidor local.
        """
        url = data.get("url", "")
        filename = data.get("filename", "")
        cookies = data.get("cookies", "")
        referer = data.get("referer", "")
        user_agent = data.get("userAgent", "")

        # Traer la ventana principal al frente
        self.showNormal()
        self.activateWindow()
        self.raise_()

        # Abrir el diálogo de descarga con la URL, nombre y cookies pre-rellenados
        current_queues = self.sidebar.get_all_queues()
        dialog = AddDownloadDialog(
            initial_url=url,
            initial_filename=filename,
            existing_queues=current_queues,
            initial_cookies=cookies,
            initial_referer=referer,
            initial_user_agent=user_agent,
            parent=self
        )
        dialog.queue_created.connect(self.sidebar.add_custom_queue)

        if dialog.exec():
            item = dialog.created_item
            if not item:
                return

            item = self._handle_duplicate_policy(item)
            if not item:
                return

            self.table_model.add_download(item)
            if getattr(dialog, "speculative_already_completed", False):
                self.engine.register_item(item)
                self.engine.task_status_changed.emit(item.id, DownloadStatus.COMPLETED)
                self.engine.task_finished.emit(item)
                self.engine.save_state()
            else:
                self.engine.add_download(item, start_now=dialog.download_immediately)

    # =========================================================================
    # RESPUESTA A SEÑALES DEL ENGINE
    # =========================================================================

    def _on_engine_progress(self, item: DownloadItem):
        self.table_model.update_download(item.id)

    def _on_engine_status_changed(self, download_id: str, status: DownloadStatus):
        self.table_model.update_download(download_id)

    def _on_engine_task_finished(self, item: DownloadItem):
        self.table_model.update_download(item.id)

        if self.settings_manager.settings.notify_on_finish:
            self.status_bar.showMessage(f"✅ Descarga completada: {item.filename}", 5000)

        cfg = self.queue_manager.get_or_create_queue(item.queue_name)
        if cfg.action_on_finish in ("shutdown", "sleep", "exit_app"):
            queue_items = [it for it in self.table_model.get_all_items() if it.queue_name == item.queue_name]
            all_done = all(it.status == DownloadStatus.COMPLETED for it in queue_items)

            if all_done and queue_items:
                if cfg.action_on_finish == "exit_app":
                    self.close()
                elif cfg.action_on_finish in ("shutdown", "sleep"):
                    dialog = ShutdownCountdownDialog(
                        action=cfg.action_on_finish,
                        countdown_seconds=cfg.shutdown_countdown_seconds,
                        parent=self
                    )
                    dialog.exec()

    def _on_engine_task_error(self, item: DownloadItem, error_msg: str):
        self.table_model.update_download(item.id)
        self.status_bar.showMessage(f"❌ Error en {item.filename}: {error_msg}", 6000)

    def _on_engine_needs_refresh(self, item: DownloadItem, reason: str):
        self.table_model.update_download(item.id)
        reply = QMessageBox.warning(
            self,
            "Enlace Expirado",
            f"El enlace de descarga para '{item.filename}' ha expirado o requiere autenticación.\n\n"
            f"¿Deseas actualizar la dirección de descarga ahora?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._open_refresh_url_dialog(item)

    def _on_engine_stats_updated(self, total_speed: float, active_count: int, total_count: int):
        speed_str = DownloadItem._format_bytes(int(total_speed))
        self.status_label_total.setText(f"Total: {total_count} descargas ({active_count} activas)")
        self.status_label_speed.setText(f"Velocidad global: {speed_str}/s")

    # =========================================================================
    # ACCIONES DE USUARIO (AÑADIR, PAUSAR, REANUDAR, ELIMINAR)
    # =========================================================================

    def _open_add_download_dialog(self):
        current_queues = self.sidebar.get_all_queues()
        dialog = AddDownloadDialog(existing_queues=current_queues, parent=self)
        dialog.queue_created.connect(self.sidebar.add_custom_queue)

        if dialog.exec():
            item = dialog.created_item
            if not item:
                return

            item = self._handle_duplicate_policy(item)
            if not item:
                return

            self.table_model.add_download(item)
            if getattr(dialog, "speculative_already_completed", False):
                self.engine.register_item(item)
                self.engine.task_status_changed.emit(item.id, DownloadStatus.COMPLETED)
                self.engine.task_finished.emit(item)
                self.engine.save_state()
            else:
                self.engine.add_download(item, start_now=dialog.download_immediately)

    def _handle_duplicate_policy(self, new_item: DownloadItem) -> Optional[DownloadItem]:
        policy = self.settings_manager.settings.duplicate_action
        all_items = self.table_model.get_all_items()

        existing = next((it for it in all_items if it.url == new_item.url or (it.filename == new_item.filename and it.save_path == new_item.save_path)), None)

        if not existing:
            return new_item

        if policy == "smart":
            target_path = os.path.join(existing.save_path, existing.filename)
            if existing.status == DownloadStatus.COMPLETED and os.path.exists(target_path):
                res = QMessageBox.question(
                    self,
                    "Archivo ya descargado",
                    f"El archivo '{existing.filename}' ya fue completado previamente.\n\n"
                    f"¿Deseas abrir el archivo existente?\n(Elige 'No' para descargar una copia nueva)",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
                )
                if res == QMessageBox.StandardButton.Yes:
                    os.startfile(target_path)
                    return None
                elif res == QMessageBox.StandardButton.Cancel:
                    return None
                policy = "numbered"
            else:
                self.engine.resume_specific([existing.id])
                return None

        if policy == "numbered":
            name_parts = os.path.splitext(new_item.filename)
            base_name, ext = name_parts[0], name_parts[1]
            counter = 1
            while any(it.filename == f"{base_name} ({counter}){ext}" for it in all_items):
                counter += 1
            new_item.filename = f"{base_name} ({counter}){ext}"
            return new_item

        return new_item

    def _on_toolbar_resume_clicked(self):
        selected_items = self.download_table.get_selected_items()
        if selected_items:
            self.engine.resume_specific([it.id for it in selected_items])
        else:
            self.engine.resume_all()

    def _on_context_menu_resume(self, items: List[DownloadItem]):
        if items:
            self.engine.resume_specific([it.id for it in items])

    def _pause_selected(self):
        items = self.download_table.get_selected_items()
        self._pause_items(items)

    def _stop_selected(self):
        items = self.download_table.get_selected_items()
        self._stop_items(items)

    def _stop_all(self):
        self.engine.pause_all()

    def _delete_selected(self):
        items = self.download_table.get_selected_items()
        self._delete_items(items)

    def _pause_items(self, items: List[DownloadItem]):
        for it in items:
            self.engine.pause_download(it.id)

    def _stop_items(self, items: List[DownloadItem]):
        for it in items:
            self.engine.stop_download(it.id)

    def _delete_items(self, items: List[DownloadItem]):
        if not items:
            return

        msg = QMessageBox(self)
        msg.setWindowTitle("Eliminar Descargas")
        msg.setText(f"¿Deseas eliminar {len(items)} descarga(s) de la lista?")
        chk_delete_disk = QCheckBox("Eliminar también los archivos parciales o completos del disco", msg)
        msg.setCheckBox(chk_delete_disk)
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if msg.exec() == QMessageBox.StandardButton.Yes:
            delete_files = chk_delete_disk.isChecked()
            all_items = self.table_model.get_all_items()

            for target in items:
                self.engine.remove_download(target.id, delete_files=delete_files)
                if target in all_items:
                    row = all_items.index(target)
                    self.table_model.remove_download(row)

    def _open_refresh_url_dialog(self, item: DownloadItem):
        dialog = RefreshUrlDialog(item, parent=self)
        if dialog.exec():
            self.engine.update_download_url(item.id, dialog.new_url)

    def _on_table_double_clicked(self, index):
        item = self.proxy_model.data(index, DownloadTableModel.ITEM_OBJECT_ROLE)
        if not item:
            return

        if item.status == DownloadStatus.COMPLETED:
            full_path = os.path.join(item.save_path, item.filename)
            if os.path.exists(full_path):
                os.startfile(full_path)
            else:
                QMessageBox.warning(self, "No encontrado", f"El archivo ya no existe en el disco:\n{full_path}")
        elif item.status == DownloadStatus.DOWNLOADING:
            self.engine.pause_download(item.id)
        elif item.status in (DownloadStatus.PAUSED, DownloadStatus.QUEUED, DownloadStatus.ERROR):
            self.engine.resume_specific([item.id])
        elif item.status == DownloadStatus.NEEDS_REFRESH:
            self._open_refresh_url_dialog(item)

    # =========================================================================
    # PERSISTENCIA Y CARGA DE DATOS
    # =========================================================================

    def _load_persisted_downloads(self):
        """Carga las descargas persistentes desde ~/.brodownloads/downloads.json."""
        saved_items = self.engine.storage.load_downloads()

        if not saved_items:
            default_dir = self.settings_manager.settings.default_save_path
            saved_items = []
            """ saved_items = [
                DownloadItem(
                    id=str(uuid.uuid4()),
                    url="https://proof.ovh.net/files/10Mb.dat",
                    filename="archivo_prueba_10Mb.dat",
                    save_path=default_dir,
                    total_size=10_485_760,
                    downloaded_size=0,
                    speed=0.0,
                    status=DownloadStatus.PAUSED,
                    category=DownloadCategory.OTHER,
                    queue_name="Cola Principal"
                ),
                DownloadItem(
                    id=str(uuid.uuid4()),
                    url="https://raw.githubusercontent.com/git/git/master/README.md",
                    filename="git_readme.md",
                    save_path=default_dir,
                    total_size=0,
                    downloaded_size=0,
                    speed=0.0,
                    status=DownloadStatus.PAUSED,
                    category=DownloadCategory.DOCUMENTS,
                    queue_name="Cola Principal"
                )
            ] """
            self.engine.storage.save_downloads(saved_items)

        for it in saved_items:
            self.table_model.add_download(it)
            self.engine.register_item(it)

        self._update_status_bar()

    def closeEvent(self, event):
        """Guarda el estado completo y apaga el micro-servidor al cerrar la app."""
        self.api_server.stop()
        self.engine.save_state()
        super().closeEvent(event)

    def _update_status_bar(self):
        items = self.table_model.get_all_items()
        total_count = len(items)
        active_count = sum(1 for it in items if it.status == DownloadStatus.DOWNLOADING)
        total_speed = sum(it.speed for it in items if it.status == DownloadStatus.DOWNLOADING)

        speed_str = DownloadItem._format_bytes(int(total_speed))
        self.status_label_total.setText(f"Total: {total_count} descargas ({active_count} activas)")
        self.status_label_speed.setText(f"Velocidad global: {speed_str}/s")

    # =========================================================================
    # DIÁLOGOS DE OPCIONES Y PROGRAMADOR
    # =========================================================================

    def _sync_categories_to_sidebar(self):
        self.sidebar.update_categories(self.settings_manager.settings.categories)

    def _sync_queues_to_sidebar(self):
        for q_name in self.queue_manager.queues.keys():
            if q_name != "Cola Principal" and not self.sidebar.has_queue(q_name):
                self.sidebar.add_custom_queue(q_name)

    def _open_options_dialog(self):
        dialog = OptionsDialog(parent=self)
        dialog.settings_saved.connect(self._sync_categories_to_sidebar)
        dialog.exec()

    def _open_scheduler_dialog(self):
        dialog = SchedulerDialog(self.table_model, parent=self)
        dialog.queue_updated.connect(self._sync_queues_to_sidebar)
        dialog.exec()
        self._sync_queues_to_sidebar()

    def _apply_sidebar_filter(self, filter_type: str, filter_value: str):
        if filter_type == "status":
            self.proxy_model.set_status_filter(filter_value)
            self.proxy_model.set_category_filter("ALL")
            self.proxy_model.set_queue_filter("ALL")
        elif filter_type == "category":
            self.proxy_model.set_category_filter(filter_value)
            self.proxy_model.set_status_filter("ALL")
            self.proxy_model.set_queue_filter("ALL")
        elif filter_type == "queue":
            self.proxy_model.set_queue_filter(filter_value)
            self.proxy_model.set_status_filter("ALL")
            self.proxy_model.set_category_filter("ALL")

    def _show_about_dialog(self):
        QMessageBox.about(
            self,
            "Acerca de BRO-Downloads",
            "<h3>BRO-Downloads v1.0</h3>"
            "<p>Gestor de descargas de alto rendimiento.</p>"
            "<p>Motor multihilo con soporte de HTTP Range chunks, integración con navegadores y actualización dinámica de enlaces.</p>"
        )
