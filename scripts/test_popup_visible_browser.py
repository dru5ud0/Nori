import sys
import time
import ctypes
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright

def bring_to_front():
    try:
        user32 = ctypes.windll.user32
        def enum_windows_callback(hwnd, extra):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value
                if any(k in title.lower() for k in ("chrome", "chromium", "coinflow", "ashby")):
                    user32.ShowWindow(hwnd, 3) # SW_MAXIMIZE = 3
                    user32.SetForegroundWindow(hwnd)
                    print(f"Brought window '{title}' to front!")
                    return False
            return True

        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(EnumWindowsProc(enum_windows_callback), 0)
    except Exception as e:
        print("Note:", e)

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        args=[
            "--start-maximized",
            "--window-position=50,50",
            "--window-size=1280,900"
        ]
    )
    page = browser.new_page(no_viewport=True)
    page.goto("https://jobs.ashbyhq.com/Coinflow/5ef1599d-a828-4733-8983-58a9488aedfb/application")
    time.sleep(1)
    bring_to_front()
    print("Browser is open and brought to front! Waiting 15s...")
    time.sleep(15)
    browser.close()
