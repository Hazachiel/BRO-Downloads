import os
import subprocess
from typing import List, Optional
from PySide6.QtWidgets import QTableView, QHeaderView, QMenu, QMessageBox
from PySide6.QtCore import Qt, Signal, QModelIndex, QTimer
from PySide6.QtGui import QAction, QClipboard, QGuiApplication
from core.settings_manager import SettingsManager

from models.download_item import DownloadItem, DownloadStatus
from models.table_model import DownloadTableModel
from models.filter_proxy_model import DownloadFilterProxyModel
from .progress_delegate import ProgressBarDelegate


class DownloadTableView(QTableView):
    """
    Vista de tabla optimizada para listas de descargas concurrentes.
    Usa renderizado por delegado para barras de progreso y menú contextual completo.
    """

    resume_requested = Signal(list)     # List[DownloadItem]
    pause_requested = Signal(list)      # List[DownloadItem]
    stop_requested = Signal(list)       # List[DownloadItem]
    delete_requested = Signal(list)     # List[DownloadItem]
    refresh_url_requested = Signal(DownloadItem)  # DownloadItem

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_table()

    def _init_table(self):
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)

        # Asignar delegado para la columna 3 (Progreso)
        self.setItemDelegateForColumn(3, ProgressBarDelegate(self))

        # Menú contextual sobre las filas
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Menú contextual y redimensionamiento sobre la cabecera
        header = self.horizontalHeader()
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_header_context_menu)

        # Timer para evitar escrituras excesivas a disco al redimensionar columnas
        self._is_adjusting_columns = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self._persist_table_state)
        header.sectionResized.connect(self._on_section_resized)

    def setModel(self, model):
        super().setModel(model)
        if model:
            self._adjust_column_widths()

    def _adjust_column_widths(self):
        model = self.model()
        if not model:
            return

        self._is_adjusting_columns = True
        try:
            settings = SettingsManager().settings
            visible_cols = set(settings.main_table_visible_columns)
            widths = settings.main_table_column_widths or {}
            header = self.horizontalHeader()

            for col_idx in range(model.columnCount()):
                col_name = model.headerData(col_idx, Qt.Orientation.Horizontal)
                header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)

                if col_name in widths:
                    self.setColumnWidth(col_idx, widths[col_name])
                elif col_idx == 0:
                    self.setColumnWidth(col_idx, 300)
                elif col_idx == 3:  # Progreso
                    self.setColumnWidth(col_idx, 150)
                else:
                    self.setColumnWidth(col_idx, 120)

                is_visible = col_name in visible_cols
                self.setColumnHidden(col_idx, not is_visible)
        finally:
            self._is_adjusting_columns = False

    def _show_header_context_menu(self, pos):
        """Muestra menú contextual en la cabecera para activar u ocultar columnas."""
        model = self.model()
        if not model:
            return

        menu = QMenu(self)
        title_action = menu.addAction("Columnas Visibles:")
        title_action.setEnabled(False)
        menu.addSeparator()

        settings = SettingsManager().settings
        visible_cols = set(settings.main_table_visible_columns)

        for col_idx in range(model.columnCount()):
            col_name = model.headerData(col_idx, Qt.Orientation.Horizontal)
            action = menu.addAction(col_name)
            action.setCheckable(True)
            action.setChecked(col_name in visible_cols)
            action.triggered.connect(
                lambda checked, idx=col_idx, name=col_name: self._toggle_column(idx, name, checked)
            )

        menu.exec(self.horizontalHeader().mapToGlobal(pos))

    def _toggle_column(self, col_idx: int, col_name: str, checked: bool):
        """Muestra u oculta una columna y persiste la elección en settings.json."""
        settings = SettingsManager().settings
        visible_cols = list(settings.main_table_visible_columns)

        if not checked:
            if len(visible_cols) <= 1 and col_name in visible_cols:
                QMessageBox.warning(self, "Aviso", "Debe permanecer al menos una columna visible.")
                return
            if col_name in visible_cols:
                visible_cols.remove(col_name)
        else:
            if col_name not in visible_cols:
                visible_cols.append(col_name)

        settings.main_table_visible_columns = visible_cols
        self.setColumnHidden(col_idx, not checked)
        SettingsManager().save()

    def _on_section_resized(self, logical_index: int, old_size: int, new_size: int):
        """Captura el nuevo ancho definido por el usuario al arrastrar el borde."""
        if getattr(self, "_is_adjusting_columns", False) or new_size <= 0:
            return
        model = self.model()
        if not model:
            return
        col_name = model.headerData(logical_index, Qt.Orientation.Horizontal)
        if col_name:
            settings = SettingsManager().settings
            settings.main_table_column_widths[col_name] = new_size
            self._save_timer.start()

    def _persist_table_state(self):
        SettingsManager().save()

    def get_selected_items(self) -> List[DownloadItem]:
        """Devuelve los DownloadItems correspondientes a las filas seleccionadas."""
        selection_model = self.selectionModel()
        if not selection_model:
            return []

        indexes = selection_model.selectedRows()
        items: List[DownloadItem] = []
        proxy_model: DownloadFilterProxyModel = self.model()

        for idx in indexes:
            item = proxy_model.data(idx, DownloadTableModel.ITEM_OBJECT_ROLE)
            if item:
                items.append(item)
        return items

    def _show_context_menu(self, pos):
        index = self.indexAt(pos)
        if not index.isValid():
            return

        # Si el usuario hace clic derecho sobre una fila que no estaba dentro de la selección actual,
        # seleccionar exclusivamente esa fila para aplicar el menú sobre ella sola.
        selection_model = self.selectionModel()
        if selection_model and not selection_model.isRowSelected(index.row(), index.parent()):
            self.selectRow(index.row())

        selected_items = self.get_selected_items()
        if not selected_items:
            return

        menu = QMenu(self)

        action_resume = QAction("▶️ Reanudar", self)
        action_resume.triggered.connect(lambda: self.resume_requested.emit(selected_items))
        menu.addAction(action_resume)

        action_pause = QAction("⏸️ Pausar", self)
        action_pause.triggered.connect(lambda: self.pause_requested.emit(selected_items))
        menu.addAction(action_pause)

        action_stop = QAction("⏹️ Detener", self)
        action_stop.triggered.connect(lambda: self.stop_requested.emit(selected_items))
        menu.addAction(action_stop)

        menu.addSeparator()

        # Operaciones sobre un único elemento
        if len(selected_items) == 1:
            item = selected_items[0]

            # Opción: Actualizar dirección de descarga
            action_refresh_url = QAction("🔄 Actualizar dirección de descarga...", self)
            action_refresh_url.triggered.connect(lambda: self.refresh_url_requested.emit(item))
            menu.addAction(action_refresh_url)

            action_open = QAction("📂 Abrir archivo", self)
            action_open.setEnabled(item.status == DownloadStatus.COMPLETED)
            action_open.triggered.connect(lambda: self._open_file(item))
            menu.addAction(action_open)

            action_open_folder = QAction("📁 Abrir carpeta contenedora", self)
            action_open_folder.triggered.connect(lambda: self._open_folder(item))
            menu.addAction(action_open_folder)

            action_copy_url = QAction("🔗 Copiar enlace de descarga", self)
            action_copy_url.triggered.connect(lambda: self._copy_url(item.url))
            menu.addAction(action_copy_url)

            menu.addSeparator()

        action_delete = QAction("🗑️ Eliminar de la lista", self)
        action_delete.triggered.connect(lambda: self.delete_requested.emit(selected_items))
        menu.addAction(action_delete)

        menu.exec(self.mapToGlobal(pos))

    def _copy_url(self, url: str):
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(url)

    def _open_file(self, item: DownloadItem):
        full_path = os.path.join(item.save_path, item.filename)
        if os.path.exists(full_path):
            os.startfile(full_path)
        else:
            QMessageBox.warning(self, "No encontrado", f"El archivo no existe:\n{full_path}")

    def _open_folder(self, item: DownloadItem):
        if os.path.exists(item.save_path):
            os.startfile(item.save_path)
        else:
            QMessageBox.warning(self, "No encontrado", f"La carpeta no existe:\n{item.save_path}")
