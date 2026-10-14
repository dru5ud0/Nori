import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "webapp"))

from playwright.sync_api import sync_playwright
from backend.src.tools.tsenta_apply import (
    collect_fields, answer_fields, _execute_actions, _form_frame,
    _dismiss_blocking_overlays, _heal_validation_errors
)
from backend.src.tools.tsenta_config import default_config
from backend.src.tools.tsenta_trace import Trace
from backend.src.tools.tsenta_llm import make_llm_answerer
from server import _load_profile

profile = _load_profile()
config = default_config()
trace = Trace()
answerer = make_llm_answerer(profile, config)

url = "https://jobs.ashbyhq.com/atlan/b2b880ed-63cd-4f56-8313-87f143fa9807/application"
resume_path = r"C:\Users\Dru\Desktop\Drupadh_Suresh_Resume.pdf"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, timeout=45000)
    page.wait_for_timeout(3000)
    frame = _form_frame(page)
    
    fields = collect_fields(frame, timeout_ms=10000)
    actions = answer_fields(fields, profile, config, trace, answerer=answerer)
    
    print("\nExecuting actions...")
    summary = _execute_actions(frame, actions, resume_path, None)
    _dismiss_blocking_overlays(page)
    _heal_validation_errors(frame, profile, config, trace)
    page.wait_for_timeout(2000)
    
    screenshot_path = str(ROOT / "loot" / "reports" / "test_ashby_filled.png")
    page.screenshot(path=screenshot_path, full_page=True)
    print(f"Captured test screenshot: {screenshot_path}")
    print("Execution summary:", summary)
    
    browser.close()
