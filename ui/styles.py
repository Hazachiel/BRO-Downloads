"""
Estilos visuales QSS con tema oscuro moderno estilo Windows 11 / Fluent Design.
Diferencia cada sección con tonalidades de gris oscuro bien delimitadas,
textos en blanco de alto contraste y estados seleccionados claramente perceptibles.
"""

MODERN_STYLE = """
/* Ventana principal y base */
QMainWindow, QDialog {
    background-color: #121214;
    color: #f4f4f5;
}

QWidget {
    color: #f4f4f5;
    font-family: "Segoe UI", "SF Pro Display", -apple-system, sans-serif;
}

/* 1. Barra de menús superior */
QMenuBar {
    background-color: #1a1a1e;
    border-bottom: 1px solid #27272a;
    font-size: 13px;
    padding: 1px 3px;
    color: #e4e4e7;
}

QMenuBar::item {
    background-color: transparent;
    padding: 5px 10px;
    border-radius: 4px;
}

QMenuBar::item:selected {
    background-color: #2e2e36;
    color: #ffffff;
}

QMenu {
    background-color: #1e1e24;
    border: 1px solid #3f3f46;
    padding: 2px;
    border-radius: 4px;
    color: #f4f4f5;
}

QMenu::item {
    padding: 5px 15px 5px 10px;
    border-radius: 4px;
    font-size: 13px;
}

QMenu::item:selected {
    background-color: #3b82f6;
    color: #ffffff;
}

QMenu::separator {
    height: 1px;
    background-color: #2e2e36;
    margin: 3px 4px;
}

/* 2. Barra de herramientas rápida */
QToolBar {
    background-color: #18181c;
    border-bottom: 1px solid #27272a;
    spacing: 5px;
    padding: 3px 6px;
}

QToolButton {
    background-color: #222228;
    border: 1px solid #2e2e36;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 13px;
    font-weight: 500;
    color: #f4f4f5;
}

QToolButton:hover {
    background-color: #2c2c34;
    border: 1px solid #3f3f46;
}

QToolButton:pressed {
    background-color: #383844;
}

/* 3. Panel lateral y Listas */
QTreeWidget, QListWidget {
    background-color: #18181c;
    border: 1px solid #27272a;
    border-radius: 8px;
    padding: 3px;
    font-size: 13px;
    color: #d4d4d8;
    outline: none;
}

QTreeWidget::item, QListWidget::item {
    padding: 3px 5px;
    border-radius: 4px;
    margin: 1px 0px;
}

QTreeWidget::item:hover, QListWidget::item:hover {
    background-color: #23232b;
    color: #ffffff;
}

QTreeWidget::item:selected, QListWidget::item:selected {
    background-color: #33333f;
    color: #ffffff;
    font-weight: 600;
    border-left: 3px solid #3b82f6;
}

/* 4. Inputs y Selectores */
QLineEdit, QPlainTextEdit, QSpinBox {
    background-color: #222228;
    border: 1px solid #33333d;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 13px;
    color: #ffffff;
}
QLineEdit {
    margin-left: 5px
}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {
    border: 1px solid #3b82f6;
    background-color: #272730;
}

QComboBox {
    background-color: #222228;
    border: 1px solid #33333d;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 13px;
    color: #ffffff;
    min-height: 22px;
}

QComboBox:hover {
    border: 1px solid #4b5563;
}

QComboBox QAbstractItemView {
    background-color: #1e1e24;
    border: 1px solid #3f3f46;
    selection-background-color: #33333f;
    selection-color: #ffffff;
    color: #f4f4f5;
    padding: 4px;
}

/* 5. Tablas */
QTableView, QTableWidget {
    background-color: #16161a;
    border: 1px solid #27272a;
    border-radius: 6px;
    gridline-color: #222228;
    font-size: 12px;
    color: #e4e4e7;
    outline: none;
}

QTableView::item, QTableWidget::item {
    padding: 4px 6px;
    border-bottom: 1px solid #1e1e24;
}

QTableView::item:selected, QTableWidget::item:selected {
    background-color: #2e3444;
    color: #ffffff;
}

QHeaderView::section {
    background-color: #1f1f26;
    color: #a1a1aa;
    font-weight: 600;
    font-size: 12px;
    border: none;
    border-right: 1px solid #27272a;
    border-bottom: 1px solid #33333d;
    padding: 5px 6px;
}

/* 6. Pestañas (QTabWidget) */
QTabWidget::pane {
    border: 1px solid #27272a;
    background-color: #18181c;
    border-radius: 6px;
    padding: 6px;
}

QTabBar::tab {
    background-color: #1e1e24;
    border: 1px solid #27272a;
    border-bottom: none;
    padding: 5px 10px;
    margin-right: 4px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    color: #a1a1aa;
    font-size: 13px;
    font-weight: 500;
}

QTabBar::tab:selected {
    background-color: #272730;
    color: #ffffff;
    font-weight: 600;
    border-top: 2px solid #3b82f6;
}

QTabBar::tab:hover:!selected {
    background-color: #23232a;
    color: #e4e4e7;
}

/* 7. GroupBox, Checkbox y RadioButton */
QGroupBox {
    border: 1px solid #2c2c34;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 6px;
    font-weight: 600;
    font-size: 13px;
    color: #60a5fa;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    background-color: #18181c;
}

QCheckBox, QRadioButton {
    spacing: 8px;
    font-size: 13px;
    color: #e4e4e7;
}

QCheckBox:hover, QRadioButton:hover {
    color: #ffffff;
}

/* 8. Botones */
QPushButton {
    background-color: #272730;
    border: 1px solid #3f3f46;
    border-radius: 6px;
    padding: 5px 10px;
    color: #f4f4f5;
    font-size: 13px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #33333e;
    border-color: #52525b;
}

QPushButton:pressed {
    background-color: #3d3d4b;
}

QPushButton:default {
    background-color: #2563eb;
    border: 1px solid #3b82f6;
    color: #ffffff;
}

QPushButton:default:hover {
    background-color: #1d4ed8;
}

/* 9. Barra de Estado y Splitter */
QStatusBar {
    background-color: #18181c;
    border-top: 1px solid #27272a;
    color: #a1a1aa;
    font-size: 12px;
    padding: 4px 12px;
}

QSplitter::handle {
    background-color: #27272a;
    width: 3px;
}

QSplitter::handle:hover {
    background-color: #3b82f6;
}
"""
