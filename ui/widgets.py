import os
from PyQt6.QtWidgets import (
    QTreeWidget, QTableWidget, QLabel, QGraphicsOpacityEffect, 
    QComboBox, QCompleter, QMenu, QMessageBox
)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer, QPropertyAnimation, QEasingCurve, QSortFilterProxyModel

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


class SearchableComboBox(QComboBox):
    """PyQt6 네이티브 기능을 활용한 깔끔한 검색형 콤보박스"""
    delete_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        
        # 입력된 텍스트를 기반으로 항목을 필터링하는 모델
        self.filter_model = QSortFilterProxyModel(self)
        self.filter_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.filter_model.setSourceModel(self.model())
        
        # 콤보박스 아래에 드롭다운을 띄우는 자동완성(Completer)
        self.completer_obj = QCompleter(self.filter_model, self)
        self.completer_obj.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer_obj.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setCompleter(self.completer_obj)
        
        # 타이핑할 때마다 필터링 업데이트
        self.lineEdit().textEdited.connect(self.filter_model.setFilterFixedString)
        self.completer_obj.activated.connect(self.on_completer_activated)
        
        # 우클릭 삭제 메뉴
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def on_completer_activated(self, text):
        if text:
            self.setCurrentText(text)

    def set_items(self, items):
        self.clear()
        self.addItem("")  # 기본 빈 값
        self.addItems(sorted(list(set(items))))

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        is_ko = True # 필요시 메인 앱 언어 체크 로직 추가 가능
        delete_action = menu.addAction("선택된 항목 저장목록에서 삭제" if is_ko else "Delete from saved list")
        
        action = menu.exec(self.mapToGlobal(pos))
        if action == delete_action:
            text = self.currentText().strip()
            if text:
                self.delete_requested.emit(text)
    
    def text(self):
        return self.currentText()

    def setText(self, text):
        self.setCurrentText(text)