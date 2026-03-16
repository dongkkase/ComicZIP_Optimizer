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
        
        self.setStyleSheet("""
            QLabel {
                background-color: rgba(40, 40, 40, 240);
                color: #ffffff;
                padding: 12px 24px;
                border-radius: 8px;
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #3498DB;
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
        
        # 애니메이션 객체들을 self에 귀속시켜 안전하게 관리
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
        
        # QTimer.singleShot 대신 위젯(self)에 종속된 타이머 사용
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.anim_out.start)
        self.timer.start(duration)


class Toast:
    @staticmethod
    def show(parent, message, duration=2500):
        if parent is None:
            return
            
        # 🌟 C++ 객체가 이미 소멸되었을 때 발생하는 RuntimeError 방지
        try:
            if hasattr(parent, '_current_toast') and parent._current_toast is not None:
                parent._current_toast.hide()
                parent._current_toast.deleteLater()
        except RuntimeError:
            pass # 이미 메모리에서 삭제된 상태라면 무시
            
        toast = _ToastWidget(parent, message)
        parent._current_toast = toast 
        toast.show_animation(duration)