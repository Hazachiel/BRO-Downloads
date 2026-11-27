import re
from typing import List, Optional, Any
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QInputDialog, QMessageBox, QMenu
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QFont


class SidebarWidget(QTreeWidget):
    """
    Panel lateral izquierdo tipo árbol.
    Permite filtrar por estado, por tipo de archivo (dinámico) o por colas personalizadas.
    """

    filter_requested = Signal(str, str)
    queue_created = Signal(str)
    queue_deleted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setIndentation(16)
        self.setAnimated(True)

        self._init_tree()
        self.itemClicked.connect(self._on_item_clicked)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _init_tree(self):
        font_header = QFont()
        font_header.setBold(True)

        # 1. Rama: Estado de Descargas
        self.root_status = QTreeWidgetItem(self, ["📁 Descargas"])
        self.root_status.setFont(0, font_header)

        self.item_all = QTreeWidgetItem(self.root_status, ["🌐 Todas las Descargas"])
        self.item_all.setData(0, Qt.ItemDataRole.UserRole, ("status", "ALL"))

        self.item_downloading = QTreeWidgetItem(self.root_status, ["⬇️ Descargando"])
        self.item_downloading.setData(0, Qt.ItemDataRole.UserRole, ("status", "DOWNLOADING"))

        self.item_completed = QTreeWidgetItem(self.root_status, ["✅ Completadas"])
        self.item_completed.setData(0, Qt.ItemDataRole.UserRole, ("status", "COMPLETED"))

        self.item_unfinished = QTreeWidgetItem(self.root_status, ["⏸️ Incompletas"])
        self.item_unfinished.setData(0, Qt.ItemDataRole.UserRole, ("status", "UNFINISHED"))

        # 2. Rama: Tipos de Archivo / Categorías (Dinámicas)
        self.root_categories = QTreeWidgetItem(self, ["📂 Tipos de Archivo"])
        self.root_categories.setFont(0, font_header)

        # 3. Rama: Colas de Descarga
        self.root_queues = QTreeWidgetItem(self, ["📋 Colas"])
        self.root_queues.setFont(0, font_header)

        self.item_main_queue = QTreeWidgetItem(self.root_queues, ["⚡ Cola Principal"])
        self.item_main_queue.setData(0, Qt.ItemDataRole.UserRole, ("queue", "Cola Principal"))

        self.expandAll()
        self.setCurrentItem(self.item_all)

    def update_categories(self, categories: List[Any]):
        """
        Actualiza dinámicamente la lista de categorías del sidebar según la configuración.
        Acepta objetos CategoryRule (con .name e .icon), tuplas o nombres.
        """
        # Limpiar elementos hijos de la raíz de categorías
        while self.root_categories.childCount() > 0:
            self.root_categories.removeChild(self.root_categories.child(0))

        has_other = False
        for cat in categories:
            if hasattr(cat, "name"):
                name = cat.name
                icon = getattr(cat, "icon", "📁") or "📁"
            elif isinstance(cat, (tuple, list)) and len(cat) >= 2:
                name = cat[0]
                icon = cat[1]
            else:
                name = str(cat)
                icon = "📁"

            if name.strip().lower() == "otros":
                has_other = True

            item = QTreeWidgetItem(self.root_categories, [f"{icon} {name}"])
            item.setData(0, Qt.ItemDataRole.UserRole, ("category", name))

        # Agregar siempre 'Otros' al final si no estaba definido
        if not has_other:
            item_other = QTreeWidgetItem(self.root_categories, ["📁 Otros"])
            item_other.setData(0, Qt.ItemDataRole.UserRole, ("category", "Otros"))
        self.expandItem(self.root_categories)

    def get_all_queues(self) -> List[str]:
        """Devuelve una lista con los nombres de todas las colas existentes."""
        queues = []
        for i in range(self.root_queues.childCount()):
            child = self.root_queues.child(i)
            data = child.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == "queue":
                queues.append(data[1])
        return queues

    def suggest_next_queue_name(self) -> str:
        """
        Calcula el nombre sugerido para una nueva cola: 'Cola #'
        donde # es el número más bajo disponible no utilizado.
        """
        existing_queues = self.get_all_queues()
        used_numbers = set()
        pattern = re.compile(r"^Cola\s+(\d+)$", re.IGNORECASE)

        for q in existing_queues:
            match = pattern.match(q.strip())
            if match:
                used_numbers.add(int(match.group(1)))

        next_num = 1
        while next_num in used_numbers:
            next_num += 1

        return f"Cola {next_num}"

    def has_queue(self, queue_name: str) -> bool:
        return queue_name in self.get_all_queues()

    def add_custom_queue(self, queue_name: str) -> bool:
        """Permite al usuario crear colas custom dinámicamente."""
        queue_name = queue_name.strip()
        if not queue_name or self.has_queue(queue_name):
            return False

        item = QTreeWidgetItem(self.root_queues, [f"📌 {queue_name}"])
        item.setData(0, Qt.ItemDataRole.UserRole, ("queue", queue_name))
        self.expandItem(self.root_queues)
        self.queue_created.emit(queue_name)
        return True

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            filter_type, filter_value = data
            self.filter_requested.emit(filter_type, filter_value)

    def _show_context_menu(self, pos):
        item = self.itemAt(pos)
        menu = QMenu(self)

        # Si hace clic derecho sobre la raíz de Colas o una cola
        if item == self.root_queues or (item and item.parent() == self.root_queues):
            action_new_queue = QAction("➕ Crear nueva cola...", self)
            action_new_queue.triggered.connect(self._prompt_new_queue)
            menu.addAction(action_new_queue)

            if item and item != self.item_main_queue and item.parent() == self.root_queues:
                action_delete_queue = QAction("🗑️ Eliminar cola", self)
                action_delete_queue.triggered.connect(lambda: self._delete_queue(item))
                menu.addAction(action_delete_queue)

            menu.exec(self.mapToGlobal(pos))

    def _prompt_new_queue(self):
        suggested = self.suggest_next_queue_name()
        name, ok = QInputDialog.getText(
            self,
            "Nueva Cola",
            "Nombre de la cola de descarga:",
            text=suggested
        )
        if ok and name.strip():
            self.add_custom_queue(name.strip())

    def _delete_queue(self, item: QTreeWidgetItem):
        queue_name = item.data(0, Qt.ItemDataRole.UserRole)[1]
        confirm = QMessageBox.question(
            self,
            "Eliminar Cola",
            f"¿Seguro que deseas eliminar la cola '{queue_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.root_queues.removeChild(item)
            self.queue_deleted.emit(queue_name)
            self.setCurrentItem(self.item_all)
            self.filter_requested.emit("status", "ALL")
