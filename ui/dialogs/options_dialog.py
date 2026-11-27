import os
import secrets
from pathlib import Path
from typing import Dict, List
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QPushButton, QCheckBox, QRadioButton,
    QButtonGroup, QSpinBox, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QInputDialog, QMessageBox, QGroupBox, QPlainTextEdit,
    QApplication, QProgressDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from core.settings_manager import SettingsManager, AppSettings, CategoryRule
from core.media_tools import get_ffmpeg_path, is_ffmpeg_available, FfmpegDownloaderWorker
from core.constants import APP_DIR, EXTENSION_DIR


class OptionsDialog(QDialog):
    """
    Ventana de configuración y preferencias de BRO-Downloads.
    Organizada en 5 pestañas modernas estilo Fluent Dark con integración completa del navegador.
    """

    settings_saved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Opciones y Preferencias")
        self.resize(760, 580)

        self.settings_manager = SettingsManager()
        self._current_settings = self.settings_manager.settings

        self._init_ui()
        self._load_values()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(14, 14, 14, 14)

        # Contenedor de Pestañas
        self.tabs = QTabWidget(self)

        self.tab_general = self._create_general_tab()
        self.tab_file_types = self._create_file_types_tab()
        self.tab_categories = self._create_categories_tab()
        self.tab_downloads = self._create_downloads_tab()
        self.tab_connections = self._create_connections_tab()

        self.tabs.addTab(self.tab_general, "🖥️ General e Integración")
        self.tabs.addTab(self.tab_file_types, "📄 Tipos y Exclusiones")
        self.tabs.addTab(self.tab_categories, "📂 Categorías")
        self.tabs.addTab(self.tab_downloads, "⬇️ Descargas")
        self.tabs.addTab(self.tab_connections, "🌐 Conexiones")

        main_layout.addWidget(self.tabs)

        # Botones inferiores (Guardar / Cancelar)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_save = QPushButton("💾 Guardar y Aplicar", self)
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(self.btn_save)

        self.btn_cancel = QPushButton("Cancelar", self)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        main_layout.addLayout(btn_layout)

    # =========================================================================
    # 1. PESTAÑA: GENERAL E INTEGRACIÓN
    # =========================================================================
    def _create_general_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(14)

        # Grupo: Inicio del Sistema
        grp_system = QGroupBox("Inicio del Sistema y Comportamiento")
        grp_system_layout = QVBoxLayout(grp_system)

        self.chk_start_windows = QCheckBox("Iniciar BRO-Downloads automáticamente al arrancar Windows")
        self.chk_start_minimized = QCheckBox("Iniciar minimizado en la bandeja del sistema (System Tray)")
        self.chk_start_windows.toggled.connect(self.chk_start_minimized.setEnabled)

        grp_system_layout.addWidget(self.chk_start_windows)
        grp_system_layout.addWidget(self.chk_start_minimized)
        layout.addWidget(grp_system)

        # Grupo: Integración con Extensión de Navegador
        grp_browser = QGroupBox("Integración con Navegadores (Micro-Servidor Local API)")
        grp_browser_layout = QVBoxLayout(grp_browser)

        self.chk_browser_integration = QCheckBox("Habilitar micro-servidor para capturar descargas desde navegadores")
        grp_browser_layout.addWidget(self.chk_browser_integration)

        h_server = QHBoxLayout()
        h_server.addWidget(QLabel("Puerto local (127.0.0.1):"))
        self.spin_server_port = QSpinBox()
        self.spin_server_port.setRange(1024, 65535)
        self.spin_server_port.setValue(9876)
        h_server.addWidget(self.spin_server_port)

        h_server.addSpacing(14)
        h_server.addWidget(QLabel("Token de seguridad:"))
        self.txt_server_token = QLineEdit()
        self.txt_server_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_server_token.setReadOnly(True)
        h_server.addWidget(self.txt_server_token, stretch=2)

        self.btn_copy_token = QPushButton("📋 Copiar")
        self.btn_copy_token.setToolTip("Copiar token de seguridad al portapapeles")
        self.btn_copy_token.clicked.connect(self._copy_token_to_clipboard)
        h_server.addWidget(self.btn_copy_token)

        self.btn_new_token = QPushButton("🔄 Nuevo")
        self.btn_new_token.setToolTip("Generar un nuevo token criptográfico seguro")
        self.btn_new_token.clicked.connect(self._generate_new_token)
        h_server.addWidget(self.btn_new_token)

        grp_browser_layout.addLayout(h_server)

        btn_extension_actions = QHBoxLayout()
        btn_open_ext = QPushButton("📂 Abrir carpeta de la Extensión Web")
        btn_open_ext.setToolTip("Abre la carpeta para cargar la extensión en Chrome, Edge o Brave")
        btn_open_ext.clicked.connect(self._open_extension_folder)
        btn_extension_actions.addWidget(btn_open_ext)

        btn_install_native = QPushButton("🔌 Registrar Puente Nativo en Windows")
        btn_install_native.setToolTip("Registra el host en el Registro de Windows (HKCU) para captura nativa automática")
        btn_install_native.clicked.connect(self._register_native_bridge)
        btn_extension_actions.addWidget(btn_install_native)

        btn_ext_guide = QPushButton("❓ ¿Cómo instalar la extensión?")
        btn_ext_guide.clicked.connect(self._show_extension_guide)
        btn_extension_actions.addWidget(btn_ext_guide)
        grp_browser_layout.addLayout(btn_extension_actions)

        layout.addWidget(grp_browser)

        # Grupo: Ensamblado Multimedia (FFmpeg)
        grp_ffmpeg = QGroupBox("Herramientas de Streaming y Ensamblado de Video (FFmpeg)")
        grp_ffmpeg_layout = QVBoxLayout(grp_ffmpeg)

        self.lbl_ffmpeg_status = QLabel()
        self.lbl_ffmpeg_status.setWordWrap(True)
        grp_ffmpeg_layout.addWidget(self.lbl_ffmpeg_status)

        h_ffmpeg_btns = QHBoxLayout()
        self.btn_download_ffmpeg = QPushButton("⬇️ Descargar FFmpeg automáticamente")
        self.btn_download_ffmpeg.setToolTip("Descarga e instala una compilación portátil de FFmpeg en ~/.brodownloads/bin")
        self.btn_download_ffmpeg.clicked.connect(self._start_ffmpeg_download)
        h_ffmpeg_btns.addWidget(self.btn_download_ffmpeg)

        self.btn_browse_ffmpeg = QPushButton("Examinar...")
        self.btn_browse_ffmpeg.setToolTip("Seleccionar un ejecutable ffmpeg.exe personalizado")
        self.btn_browse_ffmpeg.clicked.connect(self._browse_custom_ffmpeg)
        h_ffmpeg_btns.addWidget(self.btn_browse_ffmpeg)

        grp_ffmpeg_layout.addLayout(h_ffmpeg_btns)
        layout.addWidget(grp_ffmpeg)
        self._update_ffmpeg_status_label()

        # Grupo: Carpeta por defecto
        grp_folder = QGroupBox("Ubicación General de Descargas")
        grp_folder_layout = QHBoxLayout(grp_folder)

        self.txt_default_folder = QLineEdit()
        self.txt_default_folder.setReadOnly(True)
        btn_browse_folder = QPushButton("Examinar...")
        btn_browse_folder.clicked.connect(self._browse_general_folder)

        grp_folder_layout.addWidget(self.txt_default_folder, stretch=3)
        grp_folder_layout.addWidget(btn_browse_folder)
        layout.addWidget(grp_folder)

        layout.addStretch()
        return widget

    def _copy_token_to_clipboard(self):
        token = self.txt_server_token.text()
        if token:
            QGuiApplication.clipboard().setText(token)
            QMessageBox.information(self, "Token Copiado", "El token de seguridad ha sido copiado al portapapeles.\nPégalo en el popup de la extensión.")

    def _generate_new_token(self):
        new_token = secrets.token_hex(16)
        self.txt_server_token.setText(new_token)

    def _open_extension_folder(self):
        if EXTENSION_DIR.exists():
            os.startfile(str(EXTENSION_DIR))
        else:
            QMessageBox.warning(self, "No encontrado", f"No se encontró la carpeta:\n{EXTENSION_DIR}")

    def _register_native_bridge(self):
        try:
            from native_host.install_host import install
            install()
            QMessageBox.information(
                self,
                "Puente Nativo Registrado",
                "El puente Native Messaging ha sido registrado correctamente en Windows (HKCU) para Chrome, Edge y Brave.\n\nYa puedes cargar o recargar la extensión en tu navegador sin configurar tokens."
            )
        except Exception as e:
            QMessageBox.critical(self, "Error al registrar", f"No se pudo registrar el host nativo:\n{e}")

    def _show_extension_guide(self):
        QMessageBox.information(
            self,
            "Instalación de la Extensión y Puente Nativo",
            "<h3>Cómo instalar la integración con Chrome, Edge o Brave:</h3>"
            "<ol>"
            "<li>Haz clic en el botón <b>'🔌 Registrar Puente Nativo en Windows'</b> (o ejecuta <code>install_native_host.bat</code>).</li>"
            "<li>Abre <b>chrome://extensions</b> o <b>edge://extensions</b> en tu navegador.</li>"
            "<li>Activa el interruptor <b>'Modo de desarrollador'</b> (esquina superior).</li>"
            "<li>Haz clic en el botón <b>'Cargar descomprimida'</b> y selecciona la carpeta <b>'extension'</b>.</li>"
            "<li>¡Listo! El puente nativo se conectará automáticamente sin necesidad de tokens. Si la app está cerrada, Chrome la abrirá automáticamente al iniciar una descarga.</li>"
            "</ol>"
        )

    def _browse_general_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta general de descargas", self.txt_default_folder.text())
        if folder:
            self.txt_default_folder.setText(folder)

    def _update_ffmpeg_status_label(self):
        path = get_ffmpeg_path()
        if path:
            self.lbl_ffmpeg_status.setText(f"<b>Estado:</b> <span style='color:#51cf66'>✅ FFmpeg disponible</span><br><small style='color:#8c92a4'>Ruta: {path}</small>")
            if hasattr(self, "btn_download_ffmpeg"):
                self.btn_download_ffmpeg.setText("🔄 Reinstalar / Actualizar FFmpeg")
        else:
            self.lbl_ffmpeg_status.setText("<b>Estado:</b> <span style='color:#ff6b6b'>❌ FFmpeg no detectado</span> (necesario para streaming HLS y videos de YouTube)")
            if hasattr(self, "btn_download_ffmpeg"):
                self.btn_download_ffmpeg.setText("⬇️ Descargar FFmpeg automáticamente")

    def _browse_custom_ffmpeg(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar ejecutable ffmpeg.exe",
            "",
            "Ejecutable FFmpeg (ffmpeg.exe);;Todos los archivos (*.*)"
        )
        if file_path:
            self.settings_manager.settings.ffmpeg_path = file_path
            self.settings_manager.save()
            self._update_ffmpeg_status_label()
            QMessageBox.information(self, "FFmpeg configurado", f"Se ha vinculado FFmpeg correctamente:\n{file_path}")

    def _start_ffmpeg_download(self):
        progress = QProgressDialog("Descargando FFmpeg portátil oficial...", "Cancelar", 0, 100, self)
        progress.setWindowTitle("Instalador de FFmpeg")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(5)

        worker = FfmpegDownloaderWorker(self)

        def on_progress(percent, text):
            progress.setValue(percent)
            progress.setLabelText(text)

        def on_finished(success, message):
            progress.close()
            if success:
                self._update_ffmpeg_status_label()
                QMessageBox.information(self, "FFmpeg instalado", f"¡FFmpeg se ha instalado y configurado correctamente!\nUbicación:\n{message}")
            else:
                QMessageBox.warning(self, "Instalación de FFmpeg", message)

        worker.progress_updated.connect(on_progress)
        worker.download_finished.connect(on_finished)
        progress.canceled.connect(worker.cancel)
        worker.start()

    # =========================================================================
    # 2. PESTAÑA: TIPOS DE ARCHIVO Y EXCLUSIONES
    # =========================================================================
    def _create_file_types_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        grp_exts = QGroupBox("Extensiones de Captura Automática")
        grp_exts_layout = QVBoxLayout(grp_exts)
        grp_exts_layout.addWidget(QLabel("Capturar automáticamente enlaces que terminen en las siguientes extensiones (separadas por espacio):"))

        self.txt_extensions = QPlainTextEdit()
        self.txt_extensions.setMaximumHeight(80)
        grp_exts_layout.addWidget(self.txt_extensions)
        layout.addWidget(grp_exts)

        grp_sites = QGroupBox("Sitios Excluidos (No descargar automáticamente)")
        grp_sites_layout = QVBoxLayout(grp_sites)
        grp_sites_layout.addWidget(QLabel("No interceptar descargas de páginas que coincidan con estos patrones (comodín *):"))

        sites_h_layout = QHBoxLayout()
        self.list_excluded_sites = QListWidget()
        sites_h_layout.addWidget(self.list_excluded_sites, stretch=3)

        sites_btn_layout = QVBoxLayout()
        btn_add_site = QPushButton("➕ Añadir...")
        btn_edit_site = QPushButton("✏️ Editar...")
        btn_del_site = QPushButton("🗑️ Eliminar")

        btn_add_site.clicked.connect(self._add_excluded_site)
        btn_edit_site.clicked.connect(self._edit_excluded_site)
        btn_del_site.clicked.connect(self._delete_excluded_site)

        sites_btn_layout.addWidget(btn_add_site)
        sites_btn_layout.addWidget(btn_edit_site)
        sites_btn_layout.addWidget(btn_del_site)
        sites_btn_layout.addStretch()

        sites_h_layout.addLayout(sites_btn_layout)
        grp_sites_layout.addLayout(sites_h_layout)
        layout.addWidget(grp_sites)

        return widget

    def _add_excluded_site(self):
        pattern, ok = QInputDialog.getText(self, "Añadir Exclusión", "Patrón de URL o dominio (ej: *.banco*.com/*):")
        if ok and pattern.strip():
            self.list_excluded_sites.addItem(pattern.strip().lower())

    def _edit_excluded_site(self):
        item = self.list_excluded_sites.currentItem()
        if not item:
            return
        pattern, ok = QInputDialog.getText(self, "Editar Exclusión", "Patrón de URL o dominio:", text=item.text())
        if ok and pattern.strip():
            item.setText(pattern.strip().lower())

    def _delete_excluded_site(self):
        row = self.list_excluded_sites.currentRow()
        if row >= 0:
            self.list_excluded_sites.takeItem(row)

    # =========================================================================
    # 3. PESTAÑA: GESTOR DE CATEGORÍAS PERSONALIZADAS
    # =========================================================================
    def _create_categories_tab(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setSpacing(14)

        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Categorías:"))
        self.list_categories = QListWidget()
        self.list_categories.currentRowChanged.connect(self._on_category_selected)
        left_layout.addWidget(self.list_categories)

        cat_btn_layout = QHBoxLayout()
        self.btn_add_cat = QPushButton("➕ Nueva")
        self.btn_del_cat = QPushButton("🗑️ Eliminar")
        self.btn_add_cat.clicked.connect(self._add_category)
        self.btn_del_cat.clicked.connect(self._delete_category)

        cat_btn_layout.addWidget(self.btn_add_cat)
        cat_btn_layout.addWidget(self.btn_del_cat)
        left_layout.addLayout(cat_btn_layout)
        layout.addLayout(left_layout, stretch=2)

        right_grp = QGroupBox("Propiedades de la Categoría")
        right_layout = QVBoxLayout(right_grp)
        right_layout.setSpacing(10)

        right_layout.addWidget(QLabel("Nombre de la categoría:"))
        self.txt_cat_name = QLineEdit()
        self.txt_cat_name.textChanged.connect(self._update_current_cat_memory)
        right_layout.addWidget(self.txt_cat_name)

        right_layout.addWidget(QLabel("Extensiones asociadas (separadas por espacio):"))
        self.txt_cat_extensions = QLineEdit()
        self.txt_cat_extensions.setPlaceholderText("ejemplo: stl obj fbx blend")
        self.txt_cat_extensions.textChanged.connect(self._update_current_cat_memory)
        right_layout.addWidget(self.txt_cat_extensions)

        right_layout.addWidget(QLabel("Carpeta de destino predeterminada:"))
        cat_folder_layout = QHBoxLayout()
        self.txt_cat_folder = QLineEdit()
        self.txt_cat_folder.textChanged.connect(self._update_current_cat_memory)
        btn_browse_cat_folder = QPushButton("Examinar...")
        btn_browse_cat_folder.clicked.connect(self._browse_cat_folder)
        cat_folder_layout.addWidget(self.txt_cat_folder)
        cat_folder_layout.addWidget(btn_browse_cat_folder)
        right_layout.addLayout(cat_folder_layout)

        right_layout.addStretch()
        layout.addWidget(right_grp, stretch=3)

        self._categories_in_memory: List[CategoryRule] = []
        return widget

    def _browse_cat_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Carpeta para categoría", self.txt_cat_folder.text())
        if folder:
            self.txt_cat_folder.setText(folder)

    def _on_category_selected(self, row: int):
        if 0 <= row < len(self._categories_in_memory):
            cat = self._categories_in_memory[row]
            self.txt_cat_name.blockSignals(True)
            self.txt_cat_extensions.blockSignals(True)
            self.txt_cat_folder.blockSignals(True)

            self.txt_cat_name.setText(cat.name)
            self.txt_cat_extensions.setText(" ".join(cat.extensions))
            self.txt_cat_folder.setText(cat.default_folder)

            self.txt_cat_name.blockSignals(False)
            self.txt_cat_extensions.blockSignals(False)
            self.txt_cat_folder.blockSignals(False)

    def _update_current_cat_memory(self):
        row = self.list_categories.currentRow()
        if 0 <= row < len(self._categories_in_memory):
            cat = self._categories_in_memory[row]
            cat.name = self.txt_cat_name.text().strip() or "Sin nombre"
            raw_exts = self.txt_cat_extensions.text().replace(",", " ").split()
            cat.extensions = [e.lstrip(".").lower() for e in raw_exts if e.strip()]
            cat.default_folder = self.txt_cat_folder.text().strip()
            self.list_categories.item(row).setText(f"{cat.icon} {cat.name}")

    def _add_category(self):
        name, ok = QInputDialog.getText(self, "Nueva Categoría", "Nombre de la categoría:")
        if ok and name.strip():
            new_cat = CategoryRule(
                name=name.strip(),
                extensions=[],
                default_folder=str(Path.home() / "Downloads" / name.strip()),
                icon="📁"
            )
            self._categories_in_memory.append(new_cat)
            self.list_categories.addItem(f"{new_cat.icon} {new_cat.name}")
            self.list_categories.setCurrentRow(len(self._categories_in_memory) - 1)

    def _delete_category(self):
        row = self.list_categories.currentRow()
        if row >= 0:
            cat_name = self._categories_in_memory[row].name
            confirm = QMessageBox.question(
                self,
                "Eliminar Categoría",
                f"¿Eliminar la categoría '{cat_name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if confirm == QMessageBox.StandardButton.Yes:
                del self._categories_in_memory[row]
                self.list_categories.takeItem(row)

    # =========================================================================
    # 4. PESTAÑA: OPCIONES DE DESCARGAS Y DUPLICADOS
    # =========================================================================
    def _create_downloads_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(14)

        grp_notif = QGroupBox("Notificaciones del Sistema")
        grp_notif_layout = QVBoxLayout(grp_notif)

        self.chk_notif_start = QCheckBox("Mostrar notificación emergente cuando se inicie una descarga")
        self.chk_notif_finish = QCheckBox("Mostrar notificación emergente cuando se complete una descarga")
        self.chk_sound_finish = QCheckBox("Reproducir sonido al finalizar descarga")
        self.chk_speculative = QCheckBox("⚡ Iniciar descarga anticipada en segundo plano al capturar enlace")

        grp_notif_layout.addWidget(self.chk_speculative)
        grp_notif_layout.addWidget(self.chk_notif_start)
        grp_notif_layout.addWidget(self.chk_notif_finish)
        grp_notif_layout.addWidget(self.chk_sound_finish)
        layout.addWidget(grp_notif)

        grp_dups = QGroupBox("Si se añade un enlace de descarga duplicado:")
        grp_dups_layout = QVBoxLayout(grp_dups)
        grp_dups_layout.setSpacing(10)

        self.rad_smart = QRadioButton(
            "🧠 Comportamiento inteligente:\n"
            "   Si el archivo ya está completo, ofrecer abrirlo; si está incompleto o pausado, reanudar descarga."
        )
        self.rad_numbered = QRadioButton(
            "🔢 Descargar siempre una copia numerada (ejemplo: 'archivo (1).zip')"
        )
        self.rad_overwrite = QRadioButton(
            "⚠️ Sobrescribir siempre el archivo existente (reemplazar archivo en disco)"
        )

        self.dup_button_group = QButtonGroup(self)
        self.dup_button_group.addButton(self.rad_smart, 0)
        self.dup_button_group.addButton(self.rad_numbered, 1)
        self.dup_button_group.addButton(self.rad_overwrite, 2)

        grp_dups_layout.addWidget(self.rad_smart)
        grp_dups_layout.addWidget(self.rad_numbered)
        grp_dups_layout.addWidget(self.rad_overwrite)
        layout.addWidget(grp_dups)

        layout.addStretch()
        return widget

    # =========================================================================
    # 5. PESTAÑA: GESTOR DE CONEXIONES Y SERVIDORES
    # =========================================================================
    def _create_connections_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        grp_conn = QGroupBox("Conexiones de Red y Rendimiento")
        grp_conn_layout = QVBoxLayout(grp_conn)

        h_conn = QHBoxLayout()
        h_conn.addWidget(QLabel("Número predeterminado de conexiones por descarga (chunks):"))
        self.spin_connections = QSpinBox()
        self.spin_connections.setRange(1, 32)
        self.spin_connections.setValue(8)
        self.spin_connections.valueChanged.connect(self._on_connections_changed)
        h_conn.addWidget(self.spin_connections)
        grp_conn_layout.addLayout(h_conn)

        self.lbl_warning_conn = QLabel("⚠️ Atención: Más de 16 conexiones simultáneas a un mismo servidor pueden activar protección anti-DDoS (Error 429 / Bloqueo de IP).")
        self.lbl_warning_conn.setStyleSheet("color: #f59e0b; font-size: 11px;")
        self.lbl_warning_conn.setVisible(False)
        grp_conn_layout.addWidget(self.lbl_warning_conn)

        h_global = QHBoxLayout()
        h_global.addWidget(QLabel("Máximo total de conexiones globales simultáneas:"))
        self.spin_global_conn = QSpinBox()
        self.spin_global_conn.setRange(4, 128)
        self.spin_global_conn.setValue(32)
        h_global.addWidget(self.spin_global_conn)
        grp_conn_layout.addLayout(h_global)

        layout.addWidget(grp_conn)

        grp_domains = QGroupBox("Reglas de Conexión por Servidor / Sitio Web")
        grp_domains_layout = QVBoxLayout(grp_domains)
        grp_domains_layout.addWidget(QLabel("Sobrescribe el número de conexiones para servidores específicos (ej. hostings gratuitos):"))

        dom_h_layout = QHBoxLayout()
        self.table_domains = QTableWidget(0, 2)
        self.table_domains.setHorizontalHeaderLabels(["Servidor / Dominio", "Máx. Conexiones"])
        self.table_domains.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_domains.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        dom_h_layout.addWidget(self.table_domains, stretch=3)

        dom_btn_layout = QVBoxLayout()
        btn_add_domain = QPushButton("➕ Añadir servidor...")
        btn_del_domain = QPushButton("🗑️ Eliminar")

        btn_add_domain.clicked.connect(self._add_domain_limit)
        btn_del_domain.clicked.connect(self._delete_domain_limit)

        dom_btn_layout.addWidget(btn_add_domain)
        dom_btn_layout.addWidget(btn_del_domain)
        dom_btn_layout.addStretch()

        dom_h_layout.addLayout(dom_btn_layout)
        grp_domains_layout.addLayout(dom_h_layout)
        layout.addWidget(grp_domains)

        return widget

    def _on_connections_changed(self, value: int):
        self.lbl_warning_conn.setVisible(value > 16)

    def _add_domain_limit(self):
        domain, ok = QInputDialog.getText(self, "Añadir Regla por Servidor", "Nombre del dominio (ej. rapidgator.net):")
        if ok and domain.strip():
            conns, ok2 = QInputDialog.getInt(self, "Conexiones para " + domain.strip(), "Número máximo de conexiones:", 1, 1, 32)
            if ok2:
                row = self.table_domains.rowCount()
                self.table_domains.insertRow(row)
                self.table_domains.setItem(row, 0, QTableWidgetItem(domain.strip().lower()))
                self.table_domains.setItem(row, 1, QTableWidgetItem(str(conns)))

    def _delete_domain_limit(self):
        row = self.table_domains.currentRow()
        if row >= 0:
            self.table_domains.removeRow(row)

    # =========================================================================
    # CARGA Y GUARDADO DE VALORES
    # =========================================================================
    def _load_values(self):
        s = self._current_settings

        # 1. General e Integración
        self.chk_start_windows.setChecked(s.start_with_windows)
        self.chk_start_minimized.setChecked(s.start_minimized)
        self.chk_start_minimized.setEnabled(s.start_with_windows)
        self.chk_browser_integration.setChecked(s.browser_integration)
        self.spin_server_port.setValue(s.server_port)
        self.txt_server_token.setText(s.server_token)
        self.txt_default_folder.setText(s.default_save_path)

        # 2. Tipos y Exclusiones
        self.txt_extensions.setPlainText(" ".join(s.monitored_extensions).upper())
        self.list_excluded_sites.clear()
        for site in s.excluded_sites:
            self.list_excluded_sites.addItem(site)

        # 3. Categorías
        self._categories_in_memory = [
            CategoryRule(c.name, list(c.extensions), c.default_folder, getattr(c, "icon", "📁"))
            for c in s.categories
        ]
        self.list_categories.clear()
        for c in self._categories_in_memory:
            self.list_categories.addItem(f"{c.icon} {c.name}")
        if self._categories_in_memory:
            self.list_categories.setCurrentRow(0)

        # 4. Descargas
        self.chk_speculative.setChecked(getattr(s, "speculative_download", True))
        self.chk_notif_start.setChecked(s.notify_on_start)
        self.chk_notif_finish.setChecked(s.notify_on_finish)
        self.chk_sound_finish.setChecked(s.play_sound_on_finish)
        if s.duplicate_action == "numbered":
            self.rad_numbered.setChecked(True)
        elif s.duplicate_action == "overwrite":
            self.rad_overwrite.setChecked(True)
        else:
            self.rad_smart.setChecked(True)

        # 5. Conexiones
        self.spin_connections.setValue(s.default_connections)
        self._on_connections_changed(s.default_connections)
        self.spin_global_conn.setValue(s.max_global_connections)

        self.table_domains.setRowCount(0)
        for dom, limit in s.domain_limits.items():
            row = self.table_domains.rowCount()
            self.table_domains.insertRow(row)
            self.table_domains.setItem(row, 0, QTableWidgetItem(dom))
            self.table_domains.setItem(row, 1, QTableWidgetItem(str(limit)))

    def _on_save(self):
        s = self.settings_manager.settings

        # 1. General e Integración
        s.start_with_windows = self.chk_start_windows.isChecked()
        s.start_minimized = self.chk_start_minimized.isChecked()
        s.browser_integration = self.chk_browser_integration.isChecked()
        s.server_port = self.spin_server_port.value()
        s.server_token = self.txt_server_token.text().strip()
        s.default_save_path = self.txt_default_folder.text()

        self.settings_manager.apply_windows_startup(s.start_with_windows)

        # 2. Tipos y Exclusiones
        exts_raw = self.txt_extensions.toPlainText().replace(",", " ").split()
        s.monitored_extensions = [e.lstrip(".").lower() for e in exts_raw if e.strip()]

        s.excluded_sites = [
            self.list_excluded_sites.item(i).text()
            for i in range(self.list_excluded_sites.count())
        ]

        # 3. Categorías
        s.categories = self._categories_in_memory

        # 4. Descargas
        s.speculative_download = self.chk_speculative.isChecked()
        s.notify_on_start = self.chk_notif_start.isChecked()
        s.notify_on_finish = self.chk_notif_finish.isChecked()
        s.play_sound_on_finish = self.chk_sound_finish.isChecked()

        if self.rad_numbered.isChecked():
            s.duplicate_action = "numbered"
        elif self.rad_overwrite.isChecked():
            s.duplicate_action = "overwrite"
        else:
            s.duplicate_action = "smart"

        # 5. Conexiones
        s.default_connections = self.spin_connections.value()
        s.max_global_connections = self.spin_global_conn.value()

        domain_limits = {}
        for r in range(self.table_domains.rowCount()):
            dom_item = self.table_domains.item(r, 0)
            limit_item = self.table_domains.item(r, 1)
            if dom_item and limit_item:
                try:
                    domain_limits[dom_item.text().strip().lower()] = int(limit_item.text())
                except ValueError:
                    pass
        s.domain_limits = domain_limits

        self.settings_manager.save()
        self.settings_saved.emit()
        self.accept()
