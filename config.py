import os
import sys
import json
import locale

def get_executable_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    elif "__compiled__" in globals():
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    else:
        return os.path.dirname(os.path.abspath(__file__))

def get_resource_path(filename):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, filename)
    if os.path.exists(path): return path
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        path = os.path.join(sys._MEIPASS, filename)
        if os.path.exists(path): return path
    return os.path.join(get_executable_dir(), filename)

CURRENT_VERSION = "1.7.1"
try:
    _ver_path = get_resource_path("version.json")
    if os.path.exists(_ver_path):
        with open(_ver_path, "r", encoding="utf-8") as _vf:
            _vdata = json.load(_vf)
            if "latest_version" in _vdata:
                CURRENT_VERSION = _vdata["latest_version"]
except:
    pass

CONFIG_FILE = os.path.join(get_executable_dir(), 'config.json')

def get_system_language():
    try:
        lang_code, _ = locale.getdefaultlocale()
        if lang_code and lang_code.startswith('ko'): return 'ko'
    except: pass
    return 'en' 

def get_safe_thread_limits():
    total_cores = os.cpu_count() or 4
    safe_max = max(1, total_cores - 1) if total_cores <= 4 else max(1, total_cores - 2)
    default_threads = max(1, int(total_cores * 0.5))
    return total_cores, safe_max, default_threads

def load_config():
    sys_lang = get_system_language()
    total_cores, safe_max, default_threads = get_safe_thread_limits()
    default_config = {
        "lang": sys_lang, "target_format": "none", "backup_on": False,
        "flatten_folders": False, "webp_conversion": False,
        "webp_quality": 100, "max_threads": default_threads,
        "play_sound": True,
        "viewer_path": ""
    }
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                default_config.update(json.load(f))
                default_config["max_threads"] = min(default_config.get("max_threads", default_threads), safe_max)
    except: pass
    return default_config

def save_config(config_data):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=4)
    except: pass