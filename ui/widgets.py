from PyQt6.QtWidgets import QTableWidget, QTreeWidget
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QPainter, QColor

class ArchiveTableWidget(QTableWidget):
    delete_pressed = pyqtSignal()
    def __init__(self, rows, cols, parent=None):
        super().__init__(rows, cols, parent)
        self.placeholder_text = ""
    def setPlaceholderText(self, text):
        self.placeholder_text = text
        self.viewport().update()
    def paintEvent(self, event):
        super().paintEvent(event)
        if self.rowCount() == 0 and self.placeholder_text:
            painter = QPainter(self.viewport())
            painter.setPen(QColor("#888888"))
            font = painter.font()
            font.setFamily('맑은 고딕')
            font.setPointSize(13)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter, self.placeholder_text)
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self.delete_pressed.emit()
        else:
            super().keyPressEvent(event)

class OrgTreeWidget(QTreeWidget):
    delete_pressed = pyqtSignal()
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self.delete_pressed.emit()
        else:
            super().keyPressEvent(event)