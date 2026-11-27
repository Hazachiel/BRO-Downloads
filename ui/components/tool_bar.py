from PySide6.QtWidgets import QToolBar
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QIcon


class QuickToolBar(QToolBar):
    """
    Segunda barra de herramientas rápidas con botones de acción directa.
    """

    def __init__(self, parent=None):
        super().__init__("Barra de Acciones", parent)
        self.setMovable(False)
        self.setIconSize(QSize(24, 24))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        self._init_actions()

    def _init_actions(self):
        # Acción: Añadir URL
        self.action_add_url = QAction("➕ Añadir URL", self)
        self.action_add_url.setToolTip("Agregar una nueva descarga (Ctrl+N)")
        self.addAction(self.action_add_url)

        #self.addSeparator()

        # Acción: Reanudar
        self.action_resume = QAction("▶️ Reanudar", self)
        self.action_resume.setToolTip("Reanudar descargas seleccionadas")
        self.addAction(self.action_resume)

        # Acción: Pausar
        self.action_pause = QAction("⏸️ Pausar", self)
        self.action_pause.setToolTip("Pausar descargas seleccionadas")
        self.addAction(self.action_pause)

        # Acción: Detener
        self.action_stop = QAction("⏹️ Detener", self)
        self.action_stop.setToolTip("Detener descargas seleccionadas")
        self.addAction(self.action_stop)

        # Acción: Detener Todo
        self.action_stop_all = QAction("🛑 Detener Todo", self)
        self.action_stop_all.setToolTip("Pausar todas las descargas activas")
        self.addAction(self.action_stop_all)

        #self.addSeparator()

        # Acción: Eliminar
        self.action_delete = QAction("🗑️ Eliminar", self)
        self.action_delete.setToolTip("Eliminar descargas seleccionadas (Supr)")
        self.addAction(self.action_delete)

        #self.addSeparator()

        # Acción: Opciones
        self.action_options = QAction("⚙️ Opciones", self)
        self.action_options.setToolTip("Configurar parámetros de red y carpetas")
        self.addAction(self.action_options)

        # Acción: Programador
        self.action_scheduler = QAction("🕒 Programador", self)
        self.action_scheduler.setToolTip("Configurar horarios y límites de colas")
        self.addAction(self.action_scheduler)
