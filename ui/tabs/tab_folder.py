import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeView, QListView, 
    QTableView, QLabel, QPushButton, QSlider, QFrame, QToolBar, QMenu, QFileSystemModel
)
from PyQt6.QtCore import Qt, QDir
import qtawesome as qta

class TabFolder(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # 메인 스플리터 (좌측: 탐색기, 우측: 파일 리스트 및 정보)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # ==========================================
        # 1. 좌측 패널 (탐색기)
        # ==========================================
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # 탐색기 툴바
        left_toolbar = QHBoxLayout()
        self.btn_subfolders = QPushButton("Subfolders")
        self.btn_subfolders.setCheckable(True)
        self.btn_refresh_tree = QPushButton()
        self.btn_refresh_tree.setIcon(qta.icon('fa5s.sync-alt', color='white'))
        left_toolbar.addWidget(self.btn_subfolders)
        left_toolbar.addStretch()
        left_toolbar.addWidget(self.btn_refresh_tree)
        left_layout.addLayout(left_toolbar)

        # 탐색기 트리
        self.dir_model = QFileSystemModel()
        self.dir_model.setFilter(QDir.Filter.NoDotAndDotDot | QDir.Filter.AllDirs)
        self.dir_model.setRootPath(QDir.rootPath())
        
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.dir_model)
        self.tree_view.setHeaderHidden(True)
        for i in range(1, 4):
            self.tree_view.hideColumn(i) # 이름 컬럼만 표시
            
        left_layout.addWidget(self.tree_view)

        # 하단 상태 텍스트
        self.lbl_tree_status = QLabel("Ready")
        self.lbl_tree_status.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        left_layout.addWidget(self.lbl_tree_status)

        # ==========================================
        # 2. 우측 패널 (리스트 + 책 정보)
        # ==========================================
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 2-1. 우측 상단 (파일 리스트)
        right_top_panel = QWidget()
        right_top_layout = QVBoxLayout(right_top_panel)
        right_top_layout.setContentsMargins(0, 0, 0, 0)

        # 리스트 툴바
        list_toolbar = QHBoxLayout()
        self.btn_sidebar = QPushButton("Sidebar")
        self.btn_sidebar.setCheckable(True)
        self.btn_sidebar.setChecked(True)
        self.btn_views = QPushButton("Views")
        self.btn_grouped = QPushButton("Grouped")
        self.btn_sorted = QPushButton("Sorted")
        self.btn_layouts = QPushButton("Manage List Layouts")
        self.btn_refresh_list = QPushButton()
        self.btn_refresh_list.setIcon(qta.icon('fa5s.sync-alt', color='white'))
        
        list_toolbar.addWidget(self.btn_sidebar)
        list_toolbar.addWidget(self.btn_views)
        list_toolbar.addWidget(self.btn_grouped)
        list_toolbar.addWidget(self.btn_sorted)
        list_toolbar.addWidget(self.btn_layouts)
        list_toolbar.addStretch()
        list_toolbar.addWidget(self.btn_refresh_list)
        right_top_layout.addLayout(list_toolbar)

        # 리스트 뷰 (추후 모델 연동 예정)
        self.file_view = QTableView()
        self.file_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.file_view.setAlternatingRowColors(True)
        right_top_layout.addWidget(self.file_view)

        # 2-2. 우측 하단 (책 정보 및 슬라이더)
        right_bottom_panel = QWidget()
        right_bottom_layout = QHBoxLayout(right_bottom_panel)
        right_bottom_layout.setContentsMargins(0, 0, 0, 0)

        # 커버 이미지
        self.lbl_cover = QLabel("Cover Image")
        self.lbl_cover.setFixedSize(150, 200)
        self.lbl_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cover.setStyleSheet("border: 1px solid #444; background-color: #1a1a1a;")
        right_bottom_layout.addWidget(self.lbl_cover)

        # 메타데이터 정보 텍스트
        self.lbl_info = QLabel("comicinfo.xml metadata will be displayed here.")
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        right_bottom_layout.addWidget(self.lbl_info, 1)

        # 스플리터 조립
        right_splitter.addWidget(right_top_panel)
        right_splitter.addWidget(right_bottom_panel)
        right_splitter.setSizes([500, 200])

        self.main_splitter.addWidget(left_panel)
        self.main_splitter.addWidget(right_splitter)
        self.main_splitter.setSizes([250, 800])

        main_layout.addWidget(self.main_splitter)

        # 하단 슬라이더
        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()
        self.slider_item_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_item_size.setRange(50, 300)
        self.slider_item_size.setValue(100)
        self.slider_item_size.setFixedWidth(200)
        bottom_bar.addWidget(QLabel("Item Size:"))
        bottom_bar.addWidget(self.slider_item_size)
        main_layout.addLayout(bottom_bar)
        
        # 시그널 연결
        self.btn_sidebar.toggled.connect(self.toggle_sidebar)

    def toggle_sidebar(self, checked):
        # 좌측 패널 보이기/숨기기
        sizes = self.main_splitter.sizes()
        if checked:
            self.main_splitter.setSizes([250, sizes[1] if sizes[1] > 0 else 800])
        else:
            self.main_splitter.setSizes([0, sizes[0] + sizes[1]])