from typing import Optional
from PySide6.QtCore import QSortFilterProxyModel, QModelIndex, Qt
from .download_item import DownloadItem, DownloadStatus, DownloadCategory
from .table_model import DownloadTableModel


class DownloadFilterProxyModel(QSortFilterProxyModel):
    """
    Filtro y ordenamiento de alta velocidad implementado a nivel C++ por Qt.
    Filtra simultáneamente por:
    - Búsqueda de texto (nombre de archivo / URL)
    - Categoría (Comprimidos, Videos, etc.)
    - Estado (Todos, Descargando, Completados, Incompletos)
    - Cola (Cola Principal, colas custom)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSortRole(DownloadTableModel.RAW_VALUE_ROLE)
        self.setDynamicSortFilter(True)

        self._search_text: str = ""
        self._status_filter: str = "ALL"        # "ALL", "DOWNLOADING", "COMPLETED", "UNFINISHED"
        self._category_filter: str = "ALL"      # "ALL" o valor de DownloadCategory
        self._queue_filter: str = "ALL"         # "ALL" o nombre de la cola específica

    def set_search_text(self, text: str):
        self._search_text = text.strip().lower()
        self.invalidateFilter()

    def set_status_filter(self, status: str):
        self._status_filter = status
        self.invalidateFilter()

    def set_category_filter(self, category: str):
        self._category_filter = category
        self.invalidateFilter()

    def set_queue_filter(self, queue_name: str):
        self._queue_filter = queue_name
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        source_model = self.sourceModel()
        if not source_model:
            return True

        index = source_model.index(source_row, 0, source_parent)
        item: Optional[DownloadItem] = source_model.data(index, DownloadTableModel.ITEM_OBJECT_ROLE)

        if not item:
            return True

        # 1. Filtro por Texto de Búsqueda
        if self._search_text:
            match_name = self._search_text in item.filename.lower()
            match_url = self._search_text in item.url.lower()
            if not (match_name or match_url):
                return False

        # 2. Filtro por Cola
        if self._queue_filter != "ALL":
            if item.queue_name != self._queue_filter:
                return False

        # 3. Filtro por Categoría de Archivo
        if self._category_filter != "ALL":
            item_cat = item.category.value if hasattr(item.category, "value") else str(item.category)
            if item_cat.lower() != self._category_filter.lower():
                return False

        # 4. Filtro por Estado
        if self._status_filter != "ALL":
            if self._status_filter == "DOWNLOADING":
                if item.status not in (DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING):
                    return False
            elif self._status_filter == "COMPLETED":
                if item.status != DownloadStatus.COMPLETED:
                    return False
            elif self._status_filter == "UNFINISHED":
                if item.status in (DownloadStatus.COMPLETED, DownloadStatus.CANCELED):
                    return False

        return True
