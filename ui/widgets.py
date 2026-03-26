import os
from PyQt6.QtWidgets import QTreeWidget, QTableWidget, QLabel, QGraphicsOpacityEffect
from PyQt6.QtCore import pyqtSignal, Qt, QTimer, QPropertyAnimation, QEasingCurve

class OrgTreeWidget(QTreeWidget):
    delete_pressed = pyqtSignal()
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete: self.delete_pressed.emit()
        super().keyPressEvent(event)

class ArchiveTableWidget(QTableWidget):
    delete_pressed = pyqtSignal()
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete: self.delete_pressed.emit()
        super().keyPressEvent(event)


class _ToastWidget(QLabel):
    def __init__(self, parent, message):
        super().__init__(parent)
        self.setText(message)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 🌟 [수정] 오렌지색 배경 적용 및 폰트 사이즈(15px) 2포인트 증가
        self.setStyleSheet("""
            QLabel {
                background-color: rgba(187, 121, 15, 240);
                color: #ffffff;
                padding: 12px 24px;
                border-radius: 8px;
                font-weight: bold;
                font-size: 15px; 
                border: 1px solid #E67E22;
            }
        """)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.adjustSize()
        
        if parent:
            x = (parent.width() - self.width()) // 2
            y = parent.height() - self.height() - 90
            self.move(x, y)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0) 

    def show_animation(self, duration):
        self.show()
        self.raise_() 
        
        self.anim_in = QPropertyAnimation(self.opacity_effect, b"opacity", self)
        self.anim_in.setDuration(300) 
        self.anim_in.setStartValue(0.0) 
        self.anim_in.setEndValue(1.0) 
        self.anim_in.setEasingCurve(QEasingCurve.Type.OutQuad)
        
        self.anim_out = QPropertyAnimation(self.opacity_effect, b"opacity", self)
        self.anim_out.setDuration(400) 
        self.anim_out.setStartValue(1.0) 
        self.anim_out.setEndValue(0.0) 
        self.anim_out.setEasingCurve(QEasingCurve.Type.InQuad)
        
        self.anim_out.finished.connect(self.deleteLater)
        
        self.anim_in.start()
        
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.anim_out.start)
        self.timer.start(duration)


class Toast:
    @staticmethod
    def show(parent, message, duration=2500):
        if parent is None:
            return
            
        try:
            if hasattr(parent, '_current_toast') and parent._current_toast is not None:
                parent._current_toast.hide()
                parent._current_toast.deleteLater()
        except RuntimeError:
            pass 
            
        toast = _ToastWidget(parent, message)
        parent._current_toast = toast 
        toast.show_animation(duration)