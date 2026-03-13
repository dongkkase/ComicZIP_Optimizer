from PyQt6.QtCore import QObject, pyqtSignal

class WorkerSignals(QObject):
    progress = pyqtSignal(int, str)
    load_done = pyqtSignal(dict, list, list)
    rename_done = pyqtSignal(dict, dict, bool)
    org_load_done = pyqtSignal(dict, list)
    org_process_done = pyqtSignal(dict, list, bool)
    image_loaded = pyqtSignal(str, object)
    version_checked = pyqtSignal(str)
    release_notes_loaded = pyqtSignal(str)