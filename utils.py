# utils.py 전체 교체
import os
import re
import sys
from config import get_resource_path, get_executable_dir

def play_complete_sound():
    try:
        sound_path = get_resource_path('complete.wav')
        if not os.path.exists(sound_path):
            sound_path = os.path.join(get_executable_dir(), 'sounds', 'complete.wav')

        if sys.platform == 'win32':
            import winsound
            if os.path.exists(sound_path):
                winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                winsound.MessageBeep(winsound.MB_OK)
        else:
            # macOS / Linux: afplay(Mac) 또는 aplay(Linux) 사용
            if os.path.exists(sound_path):
                if sys.platform == 'darwin':
                    os.system(f'afplay "{sound_path}" &')
                else:
                    os.system(f'aplay "{sound_path}" &')
    except Exception:
        pass

def natural_keys(text):
    return [
        [f"{int(c):010d}" if c.isdigit() else c.lower()
         for c in re.split(r'(\d+)', p) if c]
        for p in str(text).replace('\\', '/').split('/')
    ]