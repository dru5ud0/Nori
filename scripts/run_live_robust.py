"""
Execute full Tsenta Apply engine directly on the visible Chrome window at port 9222!
"""
import sys
import os
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "webapp"))

from backend.src.tools.tsenta_ats import ats_detect_chain, ats_normalize_hint
from backend.src.tools.tsenta_config import default_config
from backend.src.tools.tsenta_trace import Trace
from backend.src.tools.tsenta_llm import make_llm_answerer
from backend.src.tools.tsenta_apply import (
    _form_frame, collect_fields, answer_fields,
    _execute_actions, _dismiss_blocking_overlays, _heal_validation_errors,
    _submit, _submission_receipt
)
from server import _load_profile, PROFILE_PATH
from playwright.sync_api import sync_playwright

RESUME_PATH = r"C:\Users\Dru\Desktop\Drupadh_Suresh_Pragmatike_Go_Resume.pdf"
COVER_PATH = r"C:\Users\Dru\Desktop\Drupadh_Suresh_Pragmatike_Go_Cover_Letter.pdf"

def run_on_live_tab():
    profile = _load_profile()
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://localhost:9222")
    context = browser.contexts[0]
    page = context.pages[0]
    
    url = page.url
    print(f"Connected to page: {url}")
    ats = ats_detect_chain(url).get("ats_id", "ashby")
    print(f"ATS: {ats}")

    config = default_config()
    trace = Trace()
    answerer = make_llm_answerer(profile, config)

    frame = _form_frame(page)
    print("\nScanning fields using full Tsenta engine...")
    fields = collect_fields(frame, timeout_ms=15000)
    print(f"Found {len(fields)} fields.")

    print("\nGenerating smart answers...")
    actions = answer_fields(fields, profile, config, trace, answerer=answerer)
    for i, a in enumerate(actions, 1):
        lbl = a.get("label") or a.get("field_id")
        val = str(a.get("value"))[:40]
        src = a.get("source")
        print(f"  [{i:02d}] {lbl[:35]:<35} -> '{val}' ({src})")

    print("\nExecuting actions live in your open Chrome window...")
    summary = _execute_actions(frame, actions, RESUME_PATH, COVER_PATH)
    _dismiss_blocking_overlays(page)
    _heal_validation_errors(frame, profile, config, trace)
    page.wait_for_timeout(2000)

    print("\nField execution summary:", summary)
    page.screenshot(path="loot/reports/live_filled_ashby.png")
    print("Screenshot saved to loot/reports/live_filled_ashby.png")

    pw.stop()

if __name__ == "__main__":
    run_on_live_tab()
