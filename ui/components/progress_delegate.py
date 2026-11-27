from PySide6.QtWidgets import QStyledItemDelegate
from PySide6.QtCore import Qt, QModelIndex, QRectF
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QLinearGradient
from models.download_item import DownloadItem, DownloadStatus
from models.table_model import DownloadTableModel


class ProgressBarDelegate(QStyledItemDelegate):
    """
    Dibuja una barra de progreso personalizada y adaptada al tema oscuro moderno.
    """

    def paint(self, painter: QPainter, option, index: QModelIndex):
        item: DownloadItem = index.data(DownloadTableModel.ITEM_OBJECT_ROLE)

        if not item:
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Ajustar dimensiones para dejar margen interno en la celda
        rect = QRectF(option.rect).adjusted(8, 7, -8, -7)
        radius = 4.0

        # 1. Fondo de la pista (Track)
        track_color = QColor("#22222a")
        track_border = QColor("#33333e")
        painter.setBrush(QBrush(track_color))
        painter.setPen(QPen(track_border, 1.0))
        painter.drawRoundedRect(rect, radius, radius)

        # 2. Relleno de la barra según porcentaje
        percent = max(0.0, min(100.0, item.progress_percentage))
        if percent > 0:
            fill_width = (rect.width() * percent) / 100.0
            fill_rect = QRectF(rect.x(), rect.y(), fill_width, rect.height())

            # Color según estado (Completado: verde sutil, Descargando: azul eléctrico, Pausado: naranja)
            if item.status == DownloadStatus.COMPLETED:
                grad = QLinearGradient(fill_rect.topLeft(), fill_rect.bottomLeft())
                grad.setColorAt(0.0, QColor("#10b981"))
                grad.setColorAt(1.0, QColor("#059669"))
            elif item.status == DownloadStatus.PAUSED:
                grad = QLinearGradient(fill_rect.topLeft(), fill_rect.bottomLeft())
                grad.setColorAt(0.0, QColor("#f59e0b"))
                grad.setColorAt(1.0, QColor("#d97706"))
            elif item.status == DownloadStatus.ERROR:
                grad = QLinearGradient(fill_rect.topLeft(), fill_rect.bottomLeft())
                grad.setColorAt(0.0, QColor("#ef4444"))
                grad.setColorAt(1.0, QColor("#dc2626"))
            else:
                grad = QLinearGradient(fill_rect.topLeft(), fill_rect.bottomLeft())
                grad.setColorAt(0.0, QColor("#3b82f6"))
                grad.setColorAt(1.0, QColor("#1d4ed8"))

            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(fill_rect, radius, radius)

        # 3. Texto del Porcentaje
        painter.setPen(QPen(QColor("#ffffff")))
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)

        text = f"{percent:.1f}%"
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

        painter.restore()
