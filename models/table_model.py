from typing import List, Any
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from .download_item import DownloadItem, DownloadStatus


class DownloadTableModel(QAbstractTableModel):
    """
    Modelo de tabla de alto rendimiento basado en QAbstractTableModel.
    A diferencia de QTableWidget, este modelo no almacena widgets en memoria,
    sino que sirve datos bajo demanda solo para las celdas visibles.
    """

    COLUMNS = [
        "Nombre de archivo",
        "Tamaño",
        "Estado",
        "Progreso",
        "Velocidad",
        "Tiempo Restante",
        "Cola",
        "Fecha"
    ]

    # Roles personalizados para ordenamiento y filtrado avanzado
    RAW_VALUE_ROLE = Qt.ItemDataRole.UserRole + 1
    ITEM_OBJECT_ROLE = Qt.ItemDataRole.UserRole + 2

    def __init__(self, downloads: List[DownloadItem] = None, parent=None):
        super().__init__(parent)
        self._downloads: List[DownloadItem] = downloads or []

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._downloads)

    def columnCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._downloads)):
            return None

        item = self._downloads[index.row()]
        col = index.column()

        # Devolver el objeto completo si se solicita
        if role == self.ITEM_OBJECT_ROLE:
            return item

        # Devolver valor crudo para ordenamiento numérico correcto (ej. ordenar por tamaño real en bytes)
        if role == self.RAW_VALUE_ROLE:
            if col == 0:
                return item.filename.lower()
            elif col == 1:
                return item.total_size
            elif col == 2:
                return item.status.value
            elif col == 3:
                return item.progress_percentage
            elif col == 4:
                return item.speed
            elif col == 5:
                return item.eta_seconds
            elif col == 6:
                return item.queue_name
            elif col == 7:
                return item.date_added.timestamp()

        # Representación en texto para mostrar en pantalla
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return item.filename
            elif col == 1:
                return item.formatted_total_size
            elif col == 2:
                return item.status.value
            elif col == 3:
                return f"{item.progress_percentage:.1f}%"
            elif col == 4:
                return item.formatted_speed
            elif col == 5:
                return item.formatted_eta
            elif col == 6:
                return item.queue_name
            elif col == 7:
                return item.date_added.strftime("%d/%m/%Y %H:%M")

        # Alineación de texto en celdas
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (1, 3, 4, 5):
                # Centrado o a la derecha para números y progreso
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        return None

    def add_download(self, item: DownloadItem):
        """Agrega un nuevo elemento al modelo notificando a la vista."""
        row_pos = len(self._downloads)
        self.beginInsertRows(QModelIndex(), row_pos, row_pos)
        self._downloads.append(item)
        self.endInsertRows()

    def remove_download(self, row: int):
        """Elimina un elemento del modelo."""
        if 0 <= row < len(self._downloads):
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._downloads[row]
            self.endRemoveRows()

    def update_download(self, download_id: str):
        """Notifica a la vista que una fila ha cambiado sin reconstruir la tabla."""
        for row, item in enumerate(self._downloads):
            if item.id == download_id:
                top_left = self.index(row, 0)
                bottom_right = self.index(row, len(self.COLUMNS) - 1)
                self.dataChanged.emit(top_left, bottom_right)
                break

    def get_item(self, row: int) -> DownloadItem:
        return self._downloads[row]

    def get_all_items(self) -> List[DownloadItem]:
        return self._downloads
