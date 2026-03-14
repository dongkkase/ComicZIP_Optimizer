from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt

class Tab3Metadata(QWidget):
    def __init__(self, main_app):
        super().__init__()
        self.main_app = main_app
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        lbl = QLabel("🛠️ 메타데이터 관리 (멋진 새 기획안을 기다리고 있습니다!)")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: #aaaaaa; font-size: 16px; font-weight: bold;")
        layout.addStretch()
        layout.addWidget(lbl)
        layout.addStretch()

    def retranslate_ui(self, t, lang):
        pass
        
    def clear_list(self):
        pass
        
    def toggle_all_checkboxes(self):
        pass
        
    def remove_selected(self):
        pass