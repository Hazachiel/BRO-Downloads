from PySide6.QtWidgets import QMenuBar, QMenu
from PySide6.QtGui import QAction


class MainMenuBar(QMenuBar):
    """
    Barra de menú principal superior.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_menus()

    def _init_menus(self):
        # 1. Menú Tareas
        tasks_menu = self.addMenu("&Tareas")
        self.action_add_url = QAction("➕ Añadir nueva descarga...", self)
        self.action_add_url.setShortcut("Ctrl+N")
        tasks_menu.addAction(self.action_add_url)

        tasks_menu.addSeparator()
        self.action_exit = QAction("Salir", self)
        self.action_exit.setShortcut("Ctrl+Q")
        tasks_menu.addAction(self.action_exit)

        # 2. Menú Archivo / Descargas
        downloads_menu = self.addMenu("&Descargas")
        self.action_resume = QAction("▶️ Reanudar", self)
        self.action_pause = QAction("⏸️ Pausar", self)
        self.action_stop = QAction("⏹️ Detener", self)
        self.action_stop_all = QAction("🛑 Detener todo", self)
        self.action_delete = QAction("🗑️ Eliminar seleccionados", self)
        self.action_delete.setShortcut("Del")

        downloads_menu.addAction(self.action_resume)
        downloads_menu.addAction(self.action_pause)
        downloads_menu.addAction(self.action_stop)
        downloads_menu.addSeparator()
        downloads_menu.addAction(self.action_stop_all)
        downloads_menu.addSeparator()
        downloads_menu.addAction(self.action_delete)

        # 3. Menú Ver
        view_menu = self.addMenu("&Ver")
        self.action_toggle_sidebar = QAction("Panel lateral", self, checkable=True)
        self.action_toggle_sidebar.setChecked(True)
        view_menu.addAction(self.action_toggle_sidebar)

        # 4. Menú Opciones
        options_menu = self.addMenu("&Opciones")
        self.action_options = QAction("⚙️ Preferencias...", self)
        self.action_scheduler = QAction("🕒 Programador de colas...", self)
        options_menu.addAction(self.action_options)
        options_menu.addAction(self.action_scheduler)

        # 5. Menú Ayuda
        help_menu = self.addMenu("A&yuda")
        self.action_about = QAction("Acerca de BRO-Downloads", self)
        help_menu.addAction(self.action_about)
