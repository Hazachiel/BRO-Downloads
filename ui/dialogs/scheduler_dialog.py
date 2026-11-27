from typing import List, Dict, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QWidget,
    QLabel, QLineEdit, QPushButton, QCheckBox, QRadioButton,
    QButtonGroup, QSpinBox, QTimeEdit, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QGroupBox, QComboBox, QInputDialog, QMessageBox, QAbstractItemView,
    QMenu
)
from PySide6.QtCore import Qt, QTime, Signal, QTimer
from core.settings_manager import SettingsManager
from core.queue_manager import QueueManager, QueueScheduleConfig
from models.download_item import DownloadItem, DownloadStatus
from models.table_model import DownloadTableModel


class RefreshUrlDialog(QDialog):
    """
    Diálogo para renovar una URL de descarga expirada (token vencido o sesión caducada)
    sin perder el progreso de los bytes ya descargados en disco.
    """

    def __init__(self, item: DownloadItem, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Actualizar dirección de descarga")
        self.resize(540, 200)
        self.item = item
        self.new_url = ""

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        info_lbl = QLabel(
            f"<b>Archivo:</b> {self.item.filename}<br>"
            f"<b>Progreso actual:</b> {self.item.progress_percentage:.1f}% ({self.item.formatted_downloaded_size})<br>"
            "Introduce la nueva URL generada por el servidor para continuar la descarga:"
        )
        layout.addWidget(info_lbl)

        self.txt_new_url = QLineEdit(self)
        self.txt_new_url.setPlaceholderText("https://... (nueva URL con token renovado)")
        self.txt_new_url.setText(self.item.url)
        self.txt_new_url.selectAll()
        layout.addWidget(self.txt_new_url)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_save = QPushButton("💾 Actualizar y Reanudar", self)
        btn_save.setDefault(True)
        btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(btn_save)

        btn_cancel = QPushButton("Cancelar", self)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        layout.addLayout(btn_layout)

    def _on_save(self):
        url = self.txt_new_url.text().strip()
        if not url:
            QMessageBox.warning(self, "URL requerida", "Por favor ingresa una URL válida.")
            return
        self.new_url = url
        self.accept()


class PriorityTableWidget(QTableWidget):
    """
    QTableWidget especializado en reordenamiento de filas enteras por Drag & Drop.
    Bloquea el arrastre a nivel de celdas o columnas individuales y
    mueve la fila entera insertándola en la nueva posición sin sobreescribir datos.
    """

    def __init__(self, rows: int = 0, columns: int = 5, parent=None):
        super().__init__(rows, columns, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropOverwriteMode(False)
        self.setDropIndicatorShown(True)

        # Configuración de cabecera interactiva y menú contextual
        self._is_adjusting_columns = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self._persist_table_state)

        header = self.horizontalHeader()
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_header_context_menu)
        header.sectionResized.connect(self._on_section_resized)

    def setup_header_customization(self):
        """Aplica la visibilidad y anchos de columnas guardados en la configuración."""
        self._is_adjusting_columns = True
        try:
            settings = SettingsManager().settings
            visible_cols = set(settings.scheduler_table_visible_columns)
            widths = settings.scheduler_table_column_widths or {}
            header = self.horizontalHeader()

            for col_idx in range(self.columnCount()):
                col_item = self.horizontalHeaderItem(col_idx)
                col_name = col_item.text() if col_item else f"Columna {col_idx}"
                header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)

                if col_name in widths:
                    self.setColumnWidth(col_idx, widths[col_name])
                elif col_idx == 0:
                    self.setColumnWidth(col_idx, 75)
                elif col_idx == 1:
                    self.setColumnWidth(col_idx, 300)
                else:
                    self.setColumnWidth(col_idx, 120)

                is_visible = col_name in visible_cols
                self.setColumnHidden(col_idx, not is_visible)
        finally:
            self._is_adjusting_columns = False

    def _show_header_context_menu(self, pos):
        menu = QMenu(self)
        title_action = menu.addAction("Columnas Visibles:")
        title_action.setEnabled(False)
        menu.addSeparator()

        settings = SettingsManager().settings
        visible_cols = set(settings.scheduler_table_visible_columns)

        for col_idx in range(self.columnCount()):
            col_item = self.horizontalHeaderItem(col_idx)
            col_name = col_item.text() if col_item else f"Columna {col_idx}"
            action = menu.addAction(col_name)
            action.setCheckable(True)
            action.setChecked(col_name in visible_cols)
            action.triggered.connect(
                lambda checked, idx=col_idx, name=col_name: self._toggle_column(idx, name, checked)
            )

        menu.exec(self.horizontalHeader().mapToGlobal(pos))

    def _toggle_column(self, col_idx: int, col_name: str, checked: bool):
        settings = SettingsManager().settings
        visible_cols = list(settings.scheduler_table_visible_columns)

        if not checked:
            if len(visible_cols) <= 1 and col_name in visible_cols:
                QMessageBox.warning(self, "Aviso", "Debe permanecer al menos una columna visible.")
                return
            if col_name in visible_cols:
                visible_cols.remove(col_name)
        else:
            if col_name not in visible_cols:
                visible_cols.append(col_name)

        settings.scheduler_table_visible_columns = visible_cols
        self.setColumnHidden(col_idx, not checked)
        SettingsManager().save()

    def _on_section_resized(self, logical_index: int, old_size: int, new_size: int):
        if getattr(self, "_is_adjusting_columns", False) or new_size <= 0:
            return
        col_item = self.horizontalHeaderItem(logical_index)
        col_name = col_item.text() if col_item else f"Columna {logical_index}"
        settings = SettingsManager().settings
        settings.scheduler_table_column_widths[col_name] = new_size
        self._save_timer.start()

    def _persist_table_state(self):
        SettingsManager().save()

    def dragEnterEvent(self, event):
        if event.source() == self:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.source() == self:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.source() != self:
            event.ignore()
            return

        source_row = self.currentRow()
        if source_row < 0:
            event.ignore()
            return

        drop_pos = event.position().toPoint()
        target_item = self.itemAt(drop_pos)

        if target_item:
            target_row = target_item.row()
        else:
            # Si se suelta en el espacio vacío debajo de la última fila
            target_row = self.rowCount() - 1

        if target_row < 0 or target_row == source_row:
            event.ignore()
            return

        # Mover la fila completa de forma limpia
        self.move_row(source_row, target_row)
        event.accept()

    def move_row(self, from_row: int, to_row: int):
        """Mueve una fila completa de from_row a to_row desplazando las demás sin sobreescribir."""
        if from_row == to_row or from_row < 0 or to_row < 0:
            return
        if from_row >= self.rowCount() or to_row >= self.rowCount():
            return

        cols = self.columnCount()
        # 1. Extraer todos los ítems de la fila de origen
        items = [self.takeItem(from_row, col) for col in range(cols)]

        # 2. Remover la fila de origen
        self.removeRow(from_row)

        # 3. Insertar la fila en la posición destino
        self.insertRow(to_row)
        for col, item in enumerate(items):
            self.setItem(to_row, col, item)

        # 4. Mantener la selección en la fila movida y renumerar
        self.selectRow(to_row)
        self.renumber_priorities()

    def renumber_priorities(self):
        """Actualiza las etiquetas de prioridad (#1, #2, #3...) en la primera columna."""
        for r in range(self.rowCount()):
            item = self.item(r, 0)
            if item:
                item.setText(f"#{r + 1}")


class SchedulerDialog(QDialog):
    """
    Ventana del Programador de Descargas y Gestor de Colas.
    Permite configurar horarios, automatización de apagado/suspensión, reintentos inteligentes,
    límites de concurrencia simultánea (cola + por servidor) y reordenamiento de prioridad.
    """

    queue_updated = Signal(str)

    def __init__(self, table_model: DownloadTableModel, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Programador de Descargas y Gestor de Colas")
        self.resize(880, 640)

        self.table_model = table_model
        self.queue_manager = QueueManager()

        self._current_queue_name = "Cola Principal"

        self._init_ui()
        self._populate_queues_list()
        self._select_queue("Cola Principal")

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # Divisor principal horizontal (Izquierda: Colas | Derecha: Pestañas de configuración)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # -------------------------------------------------------------
        # PANEL IZQUIERDO: LISTA DE COLAS
        # -------------------------------------------------------------
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        left_layout.addWidget(QLabel("<b>Colas de Descarga:</b>"))

        self.list_queues = QListWidget()
        self.list_queues.currentItemChanged.connect(self._on_queue_selection_changed)
        left_layout.addWidget(self.list_queues)

        left_btn_layout = QHBoxLayout()
        self.btn_new_queue = QPushButton("➕ Nueva Cola")
        self.btn_del_queue = QPushButton("🗑️ Eliminar")
        self.btn_new_queue.clicked.connect(self._create_new_queue)
        self.btn_del_queue.clicked.connect(self._delete_current_queue)
        left_btn_layout.addWidget(self.btn_new_queue)
        left_btn_layout.addWidget(self.btn_del_queue)
        left_layout.addLayout(left_btn_layout)

        splitter.addWidget(left_widget)

        # -------------------------------------------------------------
        # PANEL DERECHO: PESTAÑAS DE LA COLA SELECCIONADA
        # -------------------------------------------------------------
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # Encabezado con estado de la cola
        header_layout = QHBoxLayout()
        self.lbl_queue_title = QLabel("<h2>⚡ Cola Principal</h2>")
        header_layout.addWidget(self.lbl_queue_title)
        header_layout.addStretch()

        self.lbl_queue_status = QLabel("● Detenida")
        self.lbl_queue_status.setStyleSheet("color: #a1a1aa; font-weight: bold; font-size: 13px;")
        header_layout.addWidget(self.lbl_queue_status)
        right_layout.addLayout(header_layout)

        # Pestañas
        self.tabs = QTabWidget()
        self.tab_schedule = self._create_schedule_tab()
        self.tab_priority = self._create_priority_tab()

        self.tabs.addTab(self.tab_schedule, "🕒 Horarios y Automatización")
        self.tabs.addTab(self.tab_priority, "⚡ Prioridad y Concurrencia")
        right_layout.addWidget(self.tabs)

        splitter.addWidget(right_widget)
        splitter.setSizes([220, 660])
        main_layout.addWidget(splitter)

        # -------------------------------------------------------------
        # BARRA INFERIOR DE ACCIONES GLOBALES
        # -------------------------------------------------------------
        bottom_layout = QHBoxLayout()

        self.btn_start_queue = QPushButton("▶️ Iniciar Cola Ahora")
        self.btn_start_queue.setStyleSheet("background-color: #059669; color: white; font-weight: bold;")
        self.btn_start_queue.clicked.connect(self._toggle_queue_execution)
        bottom_layout.addWidget(self.btn_start_queue)

        bottom_layout.addStretch()

        self.btn_save = QPushButton("💾 Guardar y Aplicar")
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self._save_current_queue_ui)
        bottom_layout.addWidget(self.btn_save)

        self.btn_close = QPushButton("Cerrar")
        self.btn_close.clicked.connect(self.accept)
        bottom_layout.addWidget(self.btn_close)

        main_layout.addLayout(bottom_layout)

    # =========================================================================
    # 1. PESTAÑA: HORARIOS Y AUTOMATIZACIÓN
    # =========================================================================
    def _create_schedule_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        # A. Horarios
        grp_time = QGroupBox("Programación por Horario")
        grp_time_layout = QVBoxLayout(grp_time)

        # Iniciar a las
        h_start = QHBoxLayout()
        self.chk_start_time = QCheckBox("Iniciar descargas automáticamente a las:")
        self.time_start = QTimeEdit()
        self.time_start.setDisplayFormat("HH:mm")
        self.time_start.setTime(QTime(2, 0))
        self.chk_start_time.toggled.connect(self.time_start.setEnabled)
        h_start.addWidget(self.chk_start_time)
        h_start.addWidget(self.time_start)
        h_start.addStretch()
        grp_time_layout.addLayout(h_start)

        # Detener a las
        h_stop = QHBoxLayout()
        self.chk_stop_time = QCheckBox("Detener descargas automáticamente a las:")
        self.time_stop = QTimeEdit()
        self.time_stop.setDisplayFormat("HH:mm")
        self.time_stop.setTime(QTime(8, 0))
        self.chk_stop_time.toggled.connect(self.time_stop.setEnabled)
        h_stop.addWidget(self.chk_stop_time)
        h_stop.addWidget(self.time_stop)
        h_stop.addStretch()
        grp_time_layout.addLayout(h_stop)

        # Comportamiento al detener
        grp_time_layout.addWidget(QLabel("Al llegar la hora de detención:"))
        self.rad_stop_wait = QRadioButton("Esperar a que finalicen las descargas activas antes de detener la cola (Recomendado)")
        self.rad_stop_immediate = QRadioButton("Pausar de inmediato todas las descargas al cumplirse la hora")
        self.rad_stop_wait.setChecked(True)

        self.stop_behavior_group = QButtonGroup(self)
        self.stop_behavior_group.addButton(self.rad_stop_wait, 0)
        self.stop_behavior_group.addButton(self.rad_stop_immediate, 1)

        grp_time_layout.addWidget(self.rad_stop_wait)
        grp_time_layout.addWidget(self.rad_stop_immediate)

        layout.addWidget(grp_time)

        # B. Conectividad y Reintentos
        grp_conn = QGroupBox("Gestión Inteligente de Red y Reintentos")
        grp_conn_layout = QVBoxLayout(grp_conn)

        self.chk_check_internet = QCheckBox(
            "Verificar conexión a Internet antes de reintentar (evita gastar reintentos si se cortó la red)"
        )
        self.chk_check_internet.setChecked(True)
        grp_conn_layout.addWidget(self.chk_check_internet)

        h_retry = QHBoxLayout()
        h_retry.addWidget(QLabel("Reintentar descarga fallida hasta:"))
        self.spin_retries = QSpinBox()
        self.spin_retries.setRange(1, 10)
        self.spin_retries.setValue(3)
        h_retry.addWidget(self.spin_retries)
        h_retry.addWidget(QLabel("veces, esperando:"))
        self.spin_retry_interval = QSpinBox()
        self.spin_retry_interval.setRange(5, 300)
        self.spin_retry_interval.setValue(30)
        h_retry.addWidget(self.spin_retry_interval)
        h_retry.addWidget(QLabel("segundos entre cada intento."))
        h_retry.addStretch()
        grp_conn_layout.addLayout(h_retry)

        self.chk_move_failed_to_end = QCheckBox(
            "Si falla teniendo Internet (enlace/cookie expirado o timeout), mover al final de la cola en espera de actualización"
        )
        self.chk_move_failed_to_end.setChecked(True)
        grp_conn_layout.addWidget(self.chk_move_failed_to_end)

        layout.addWidget(grp_conn)

        # C. Qué hacer al finalizar todas las descargas
        grp_finish = QGroupBox("Al Completar Todas las Descargas de esta Cola")
        grp_finish_layout = QVBoxLayout(grp_finish)

        h_finish = QHBoxLayout()
        h_finish.addWidget(QLabel("Acción a ejecutar:"))
        self.combo_finish_action = QComboBox()
        self.combo_finish_action.addItems([
            "🚫 No hacer nada (permanecer abierto)",
            "🚪 Salir de BRO-Downloads",
            "🌙 Suspender el equipo (Modo Reposo)",
            "🔌 Apagar el equipo (Shutdown)"
        ])
        h_finish.addWidget(self.combo_finish_action, stretch=2)
        h_finish.addStretch()
        grp_finish_layout.addLayout(h_finish)

        self.chk_shutdown_countdown = QCheckBox(
            "Mostrar cuenta regresiva de 30 segundos con opción de cancelar antes de apagar/suspender"
        )
        self.chk_shutdown_countdown.setChecked(True)
        grp_finish_layout.addWidget(self.chk_shutdown_countdown)

        layout.addWidget(grp_finish)
        layout.addStretch()
        return widget

    # =========================================================================
    # 2. PESTAÑA: PRIORIDAD Y CONCURRENCIA
    # =========================================================================
    def _create_priority_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        # A. Limitadores Dobles de Descargas Simultáneas
        grp_limits = QGroupBox("Limitadores de Descargas Simultáneas")
        grp_limits_layout = QVBoxLayout(grp_limits)

        h_limits = QHBoxLayout()

        # Limitador 1: En la cola
        h_limits.addWidget(QLabel("Descargas simultáneas en esta cola:"))
        self.spin_concurrent_queue = QSpinBox()
        self.spin_concurrent_queue.setRange(1, 10)
        self.spin_concurrent_queue.setValue(2)
        h_limits.addWidget(self.spin_concurrent_queue)

        h_limits.addSpacing(20)

        # Limitador 2: Por Servidor
        h_limits.addWidget(QLabel("Máx. descargas simultáneas por servidor:"))
        self.spin_concurrent_server = QSpinBox()
        self.spin_concurrent_server.setRange(1, 5)
        self.spin_concurrent_server.setValue(1)
        h_limits.addWidget(self.spin_concurrent_server)

        h_limits.addStretch()
        grp_limits_layout.addLayout(h_limits)

        layout.addWidget(grp_limits)

        # B. Tabla de Prioridad de Descargas
        grp_priority = QGroupBox("Orden de Prioridad en la Cola (El orden superior se descarga primero)")
        grp_priority_layout = QHBoxLayout(grp_priority)

        # Tabla con soporte seguro de drag and drop fila a fila
        self.table_priority = PriorityTableWidget(0, 5, self)
        self.table_priority.setHorizontalHeaderLabels([
            "Prioridad", "Nombre de Archivo", "Servidor", "Tamaño", "Estado"
        ])
        self.table_priority.setup_header_customization()

        grp_priority_layout.addWidget(self.table_priority, stretch=4)

        # Botones de Reordenamiento
        btn_v_layout = QVBoxLayout()
        self.btn_move_up = QPushButton("🔼 Subir")
        self.btn_move_down = QPushButton("🔽 Bajar")
        self.btn_refresh_url = QPushButton("🔄 Actualizar Enlace...")

        self.btn_move_up.setToolTip("Mover descarga hacia arriba en prioridad")
        self.btn_move_down.setToolTip("Mover descarga hacia abajo en prioridad")
        self.btn_refresh_url.setToolTip("Renovar URL expirada sin perder los bytes descargados")

        self.btn_move_up.clicked.connect(self._move_item_up)
        self.btn_move_down.clicked.connect(self._move_item_down)
        self.btn_refresh_url.clicked.connect(self._on_refresh_url_clicked)

        btn_v_layout.addWidget(self.btn_move_up)
        btn_v_layout.addWidget(self.btn_move_down)
        btn_v_layout.addSpacing(10)
        btn_v_layout.addWidget(self.btn_refresh_url)
        btn_v_layout.addStretch()

        grp_priority_layout.addLayout(btn_v_layout)
        layout.addWidget(grp_priority)

        return widget

    # =========================================================================
    # LÓGICA DE GESTIÓN Y SINCRONIZACIÓN DE COLAS
    # =========================================================================
    def _populate_queues_list(self):
        self.list_queues.clear()
        for name in self.queue_manager.queues.keys():
            item = QListWidgetItem(f"📋 {name}")
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.list_queues.addItem(item)

    def _select_queue(self, queue_name: str):
        for i in range(self.list_queues.count()):
            item = self.list_queues.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == queue_name:
                self.list_queues.setCurrentItem(item)
                break

    def _on_queue_selection_changed(self, current: QListWidgetItem, previous: QListWidgetItem):
        if not current:
            return
        # Guardar en memoria la cola anterior antes de cambiar
        if previous:
            self._save_queue_config_from_ui(previous.data(Qt.ItemDataRole.UserRole))

        queue_name = current.data(Qt.ItemDataRole.UserRole)
        self._current_queue_name = queue_name
        self._load_queue_config_into_ui(queue_name)

    def _load_queue_config_into_ui(self, queue_name: str):
        cfg = self.queue_manager.get_or_create_queue(queue_name)
        self.lbl_queue_title.setText(f"<h2>⚡ {queue_name}</h2>")

        is_running = self.queue_manager.is_queue_running(queue_name)
        if is_running:
            self.lbl_queue_status.setText("● Procesando")
            self.lbl_queue_status.setStyleSheet("color: #10b981; font-weight: bold; font-size: 13px;")
            self.btn_start_queue.setText("⏹️ Detener Cola")
            self.btn_start_queue.setStyleSheet("background-color: #ef4444; color: white; font-weight: bold;")
        else:
            self.lbl_queue_status.setText("● Detenida")
            self.lbl_queue_status.setStyleSheet("color: #a1a1aa; font-weight: bold; font-size: 13px;")
            self.btn_start_queue.setText("▶️ Iniciar Cola Ahora")
            self.btn_start_queue.setStyleSheet("background-color: #059669; color: white; font-weight: bold;")

        # 1. Pestaña Horarios
        self.chk_start_time.setChecked(cfg.enable_start_time)
        self.time_start.setEnabled(cfg.enable_start_time)
        h, m = map(int, cfg.start_time.split(":"))
        self.time_start.setTime(QTime(h, m))

        self.chk_stop_time.setChecked(cfg.enable_stop_time)
        self.time_stop.setEnabled(cfg.enable_stop_time)
        h, m = map(int, cfg.stop_time.split(":"))
        self.time_stop.setTime(QTime(h, m))

        if cfg.stop_behavior == "pause_immediate":
            self.rad_stop_immediate.setChecked(True)
        else:
            self.rad_stop_wait.setChecked(True)

        self.chk_check_internet.setChecked(cfg.check_internet_before_retry)
        self.spin_retries.setValue(cfg.max_retries)
        self.spin_retry_interval.setValue(cfg.retry_interval_seconds)
        self.chk_move_failed_to_end.setChecked(cfg.move_failed_to_end_on_auth_error)

        action_idx = {"none": 0, "exit_app": 1, "sleep": 2, "shutdown": 3}.get(cfg.action_on_finish, 0)
        self.combo_finish_action.setCurrentIndex(action_idx)
        self.chk_shutdown_countdown.setChecked(cfg.shutdown_countdown_seconds > 0)

        # 2. Pestaña Concurrencia y Prioridad
        self.spin_concurrent_queue.setValue(cfg.max_concurrent_downloads)
        self.spin_concurrent_server.setValue(cfg.max_concurrent_per_server)

        self._load_priority_table_for_queue(queue_name, cfg.ordered_download_ids)

    def _load_priority_table_for_queue(self, queue_name: str, ordered_ids: List[str]):
        """Carga las descargas asociadas a esta cola ordenadas por su lista de prioridad."""
        all_items = self.table_model.get_all_items()
        queue_items = [it for it in all_items if it.queue_name == queue_name]

        # Ordenar según la lista de IDs guardada
        id_order = {item_id: idx for idx, item_id in enumerate(ordered_ids)}
        queue_items.sort(key=lambda it: id_order.get(it.id, 999999))

        item_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled

        self.table_priority.setRowCount(0)
        for idx, it in enumerate(queue_items):
            row = self.table_priority.rowCount()
            self.table_priority.insertRow(row)

            # Columna 0: Prioridad (#1, #2...)
            item_prio = QTableWidgetItem(f"#{idx + 1}")
            item_prio.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_prio.setData(Qt.ItemDataRole.UserRole, it.id)
            item_prio.setFlags(item_flags)

            # Columna 1: Nombre
            item_name = QTableWidgetItem(it.filename)
            item_name.setFlags(item_flags)

            # Columna 2: Servidor/Dominio
            item_domain = QTableWidgetItem(it.domain)
            item_domain.setFlags(item_flags)

            # Columna 3: Tamaño
            item_size = QTableWidgetItem(it.formatted_total_size)
            item_size.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item_size.setFlags(item_flags)

            # Columna 4: Estado
            item_status = QTableWidgetItem(it.status.value)
            item_status.setFlags(item_flags)
            if it.status == DownloadStatus.NEEDS_REFRESH:
                item_status.setForeground(Qt.GlobalColor.yellow)

            self.table_priority.setItem(row, 0, item_prio)
            self.table_priority.setItem(row, 1, item_name)
            self.table_priority.setItem(row, 2, item_domain)
            self.table_priority.setItem(row, 3, item_size)
            self.table_priority.setItem(row, 4, item_status)

    def _save_queue_config_from_ui(self, queue_name: str):
        if not queue_name:
            return
        cfg = self.queue_manager.get_or_create_queue(queue_name)

        cfg.enable_start_time = self.chk_start_time.isChecked()
        cfg.start_time = self.time_start.time().toString("HH:mm")

        cfg.enable_stop_time = self.chk_stop_time.isChecked()
        cfg.stop_time = self.time_stop.time().toString("HH:mm")

        cfg.stop_behavior = "pause_immediate" if self.rad_stop_immediate.isChecked() else "wait_active"
        cfg.check_internet_before_retry = self.chk_check_internet.isChecked()
        cfg.max_retries = self.spin_retries.value()
        cfg.retry_interval_seconds = self.spin_retry_interval.value()
        cfg.move_failed_to_end_on_auth_error = self.chk_move_failed_to_end.isChecked()

        action_map = {0: "none", 1: "exit_app", 2: "sleep", 3: "shutdown"}
        cfg.action_on_finish = action_map.get(self.combo_finish_action.currentIndex(), "none")
        cfg.shutdown_countdown_seconds = 30 if self.chk_shutdown_countdown.isChecked() else 0

        cfg.max_concurrent_downloads = self.spin_concurrent_queue.value()
        cfg.max_concurrent_per_server = self.spin_concurrent_server.value()

        # Guardar lista de IDs en orden de prioridad
        ordered_ids = []
        for r in range(self.table_priority.rowCount()):
            prio_item = self.table_priority.item(r, 0)
            if prio_item:
                download_id = prio_item.data(Qt.ItemDataRole.UserRole)
                if download_id:
                    ordered_ids.append(download_id)
        cfg.ordered_download_ids = ordered_ids

    def _save_current_queue_ui(self):
        self._save_queue_config_from_ui(self._current_queue_name)
        self.queue_manager.save()
        self.queue_updated.emit(self._current_queue_name)
        QMessageBox.information(self, "Guardado", f"Configuración de '{self._current_queue_name}' guardada correctamente.")

    # =========================================================================
    # REORDENAMIENTO DE PRIORIDAD
    # =========================================================================
    def _move_item_up(self):
        row = self.table_priority.currentRow()
        if row > 0:
            self.table_priority.move_row(row, row - 1)

    def _move_item_down(self):
        row = self.table_priority.currentRow()
        if 0 <= row < self.table_priority.rowCount() - 1:
            self.table_priority.move_row(row, row + 1)

    def _on_refresh_url_clicked(self):
        row = self.table_priority.currentRow()
        if row < 0:
            QMessageBox.information(self, "Seleccionar descarga", "Por favor selecciona una descarga para actualizar su dirección.")
            return

        download_id = self.table_priority.item(row, 0).data(Qt.ItemDataRole.UserRole)
        # Buscar el item en el modelo
        target_item = None
        for it in self.table_model.get_all_items():
            if it.id == download_id:
                target_item = it
                break

        if not target_item:
            return

        dialog = RefreshUrlDialog(target_item, parent=self)
        if dialog.exec():
            target_item.url = dialog.new_url
            target_item.status = DownloadStatus.QUEUED
            target_item.error_message = None
            self.table_model.update_download(target_item.id)
            self.table_priority.item(row, 4).setText(DownloadStatus.QUEUED.value)
            QMessageBox.information(
                self,
                "Enlace Renovado",
                f"La URL de '{target_item.filename}' ha sido actualizada y la descarga está lista para reanudarse."
            )

    # =========================================================================
    # ACCIONES DE COLA (CREAR, ELIMINAR, INICIAR)
    # =========================================================================
    def _create_new_queue(self):
        name, ok = QInputDialog.getText(self, "Nueva Cola", "Nombre de la nueva cola:")
        if ok and name.strip():
            new_name = name.strip()
            self.queue_manager.get_or_create_queue(new_name)
            self._populate_queues_list()
            self._select_queue(new_name)

    def _delete_current_queue(self):
        if self._current_queue_name == "Cola Principal":
            QMessageBox.warning(self, "Operación no permitida", "No es posible eliminar la Cola Principal del sistema.")
            return

        confirm = QMessageBox.question(
            self,
            "Eliminar Cola",
            f"¿Seguro que deseas eliminar la cola '{self._current_queue_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.queue_manager.remove_queue(self._current_queue_name)
            self._populate_queues_list()
            self._select_queue("Cola Principal")

    def _toggle_queue_execution(self):
        is_running = self.queue_manager.is_queue_running(self._current_queue_name)
        if is_running:
            self.queue_manager.stop_queue(self._current_queue_name)
        else:
            self.queue_manager.start_queue(self._current_queue_name)
        self._load_queue_config_into_ui(self._current_queue_name)
