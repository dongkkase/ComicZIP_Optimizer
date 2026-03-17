import os
import re
import winsound
from config import get_resource_path, get_executable_dir

def play_complete_sound():
    try:
        sound_path = get_resource_path('complete.wav')
        if not os.path.exists(sound_path):
            sound_path = os.path.join(get_executable_dir(), 'sounds', 'complete.wav')
            
        if os.path.exists(sound_path):
            winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        else:
            winsound.MessageBeep(winsound.MB_OK)
    except:
        pass

def natural_keys(text):
    # 기존 코드의 리스트 컴프리헨션 맨 끝에 'if c'를 추가하여 빈 문자열('')을 걸러냅니다.
    return [[f"{int(c):010d}" if c.isdigit() else c.lower() for c in re.split(r'(\d+)', p) if c] for p in str(text).replace('\\', '/').split('/')]