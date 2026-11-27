from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QComboBox, QLabel
from PySide6.QtCore import Signal


class FilterBarWidget(QWidget):
    """
    Barra de filtro rápido y búsqueda ubicada justo arriba de la tabla de descargas.
    """

    search_changed = Signal(str)
    status_filter_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 6)
        layout.setSpacing(10)

        # 1. Campo de Búsqueda
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("🔍 Buscar por nombre de archivo o URL...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.search_changed.emit)
        layout.addWidget(self.search_input, stretch=2)

        # 2. Selector de Estado Rápido
        self.status_label = QLabel("Estado:", self)
        layout.addWidget(self.status_label)

        self.status_combo = QComboBox(self)
        self.status_combo.addItems([
            "Todos los estados",
            "Descargando",
            "Completados",
            "Incompletos"
        ])
        self.status_combo.currentIndexChanged.connect(self._on_combo_changed)
        layout.addWidget(self.status_combo, stretch=1)

    def _on_combo_changed(self, index: int):
        mapping = {
            0: "ALL",
            1: "DOWNLOADING",
            2: "COMPLETED",
            3: "UNFINISHED"
        }
        self.status_filter_changed.emit(mapping.get(index, "ALL"))
