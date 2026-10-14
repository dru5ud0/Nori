"""Controlled Browser Application Runner.

Opens a visible Chromium browser window on the user's desktop, navigates to the
job posting, attaches the resume, fills out all form fields with Drupadh's
smart answers and profile data, takes a review screenshot, and keeps the
browser open for live user review.

Usage:
    python scripts/controlled_browser_apply.py [url] [--submit]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

# Add root to path so backend package resolves properly
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "webapp"))

from backend.src.tools.tsenta_ats import ats_detect_chain, ats_normalize_hint
from backend.src.tools.tsenta_config import default_config
from backend.src.tools.tsenta_trace import Trace
from backend.src.tools.tsenta_llm import make_llm_answerer
from backend.src.tools.tsenta_apply import (
    _launch_page, _open_form, _form_frame, collect_fields, answer_fields,
    _execute_actions, _dismiss_blocking_overlays, _heal_validation_errors,
    _submit, _submission_receipt, default_browser_state_path
)
from server import _load_profile, PROFILE_PATH

DEFAULT_RESUME = r"C:\Users\Dru\Desktop\Drupadh_Suresh_Resume.pdf"
DEFAULT_TARGET_URL = "https://job-boards.greenhouse.io/coinbase/jobs/7449557"


def run_controlled_apply(
    url: str,
    resume_path: str = DEFAULT_RESUME,
    cover_path: str | None = None,
    auto_submit: bool = False,
    hold_open_seconds: int = 300,
) -> dict:
    """Run an interactive headed browser application."""
    print("=" * 70)
    print("  TSENTA / NORI CONTROLLED BROWSER APPLICATION")
    print("=" * 70)
    print(f"Target URL:    {url}")
    print(f"Resume Path:   {resume_path}")
    print(f"Profile Path:  {PROFILE_PATH}")
    print(f"Auto-Submit:   {auto_submit}")
    print("=" * 70)

    # 1. Load candidate profile
    profile = _load_profile()
    name = f"{profile.get('personalInformation', {}).get('firstName', '')} {profile.get('personalInformation', {}).get('lastName', '')}".strip()
    email = profile.get('personalInformation', {}).get('email', '')
    print(f"Candidate:     {name} <{email}>")

    # 2. Detect ATS
    detection = ats_detect_chain(url)
    ats = detection.get("ats_id", "unknown")
    print(f"Detected ATS:  {ats} (confidence: {detection.get('confidence', 0)}%)")

    # 3. Setup LLM answerer
    print("Connecting smart LLM answer engine (Apilio GPT-4o-mini)...")
    config = default_config()
    trace = Trace()
    answerer = make_llm_answerer(profile, config)

    # 4. Launch VISIBLE Chromium browser with OS foreground pop-to-front
    print("\n>>> Launching visible Chromium browser window on your screen...")
    from playwright.sync_api import sync_playwright
    import ctypes
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        channel="chrome",
        headless=False,
        args=[
            "--start-maximized",
            "--window-position=30,30",
            "--window-size=1300,920",
            "--focus-on-load",
        ]
    )
    context = browser.new_context(
        no_viewport=True,
        locale="en-US",
        timezone_id="America/New_York",
    )
    page = context.new_page()

    def bring_to_front():
        try:
            user32 = ctypes.windll.user32
            def enum_cb(hwnd, extra):
                if user32.IsWindowVisible(hwnd):
                    l = user32.GetWindowTextLengthW(hwnd)
                    b = ctypes.create_unicode_buffer(l + 1)
                    user32.GetWindowTextW(hwnd, b, l + 1)
                    t = b.value
                    if any(k in t.lower() for k in ("chrome", "chromium", "ashby", "greenhouse", "coinflow", "atlan")):
                        user32.ShowWindow(hwnd, 3) # SW_MAXIMIZE
                        user32.SetForegroundWindow(hwnd)
                        return False
                return True
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            user32.EnumWindows(EnumWindowsProc(enum_cb), 0)
        except Exception:
            pass

    screenshot_path = str(ROOT / "loot" / "reports" / f"live_review_{ats}_{int(time.time())}.png")
    os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)

    try:
        # 5. Navigate to application form
        print(f"\n>>> Navigating to {url} ...")
        _open_form(page, url, ats, 45000, profile)
        page.wait_for_timeout(2000)
        bring_to_front()

        # Handle any ATS redirection
        redirected = ats_detect_chain(str(getattr(page, "url", "") or ""))
        redirected_ats = str(redirected.get("ats_id") or "unknown")
        if redirected_ats != "unknown" and redirected_ats != ats:
            ats = redirected_ats
            print(f"Redirected ATS detected: {ats}")
            _open_form(page, str(getattr(page, "url", "") or url), ats, 45000, profile)
            page.wait_for_timeout(2000)

        frame = _form_frame(page)

        # 6. Collect form fields
        print("\n>>> Scanning application form fields...")
        fields = collect_fields(frame, timeout_ms=30000)
        print(f"Found {len(fields)} fields on page.")

        # 7. Generate smart answers
        print("\n>>> Generating smart answers tailored for this role...")
        actions = answer_fields(fields, profile, config, trace, answerer=answerer)
        print(f"Prepared {len(actions)} answer actions.")

        for i, a in enumerate(actions, 1):
            lbl = a.get("label") or a.get("field_id")
            val = a.get("value")
            src = a.get("source")
            val_str = str(val)[:50] + ("..." if len(str(val)) > 50 else "")
            print(f"  [{i:02d}] {lbl[:40]:<40} -> '{val_str}' ({src})")

        # 8. Execute actions live in browser
        print("\n>>> Filling fields live in the open browser window...")
        summary = _execute_actions(frame, actions, resume_path, cover_path)
        _dismiss_blocking_overlays(page)
        _heal_validation_errors(frame, profile, config, trace)
        page.wait_for_timeout(2000)

        # Lever special: ensure autocomplete location dropdown is selected
        if ats == "lever":
            try:
                loc_input = page.query_selector("input.location-input, input[name='location']")
                if loc_input and not loc_input.input_value().strip():
                    loc_input.click()
                    loc_input.type("Chicago", delay=40)
                    page.wait_for_timeout(800)
                    drop = page.query_selector(".dropdown-location")
                    if drop:
                        drop.click()
                        page.wait_for_timeout(300)
            except Exception:
                pass

        # Greenhouse special: handle React Remix combo-boxes (country and candidate-location)
        if ats == "greenhouse":
            try:
                # 1. Country dropdown
                country_input = page.query_selector("input#country")
                if country_input:
                    country_input.click()
                    country_input.fill("")
                    country_input.type("India", delay=40)
                    page.wait_for_timeout(800)
                    opts = page.query_selector_all("[role='option']")
                    for opt in opts:
                        txt = opt.text_content().strip()
                        if txt == "India +91":
                            opt.click()
                            print(f"[Greenhouse] Selected country: {txt}")
                            break
                    page.wait_for_timeout(400)

                # 2. Location (City) dropdown
                loc_input = page.query_selector("input#candidate-location")
                if loc_input:
                    loc_input.click()
                    loc_input.fill("")
                    loc_input.type("Bengaluru", delay=40)
                    page.wait_for_timeout(800)
                    opts = page.query_selector_all("[role='option']")
                    for opt in opts:
                        txt = opt.text_content().strip()
                        if "Bengaluru" in txt:
                            opt.click()
                            print(f"[Greenhouse] Selected location: {txt}")
                            break
                    page.wait_for_timeout(400)

                # 3. Ensure phone is clean 10-digits
                phone_input = page.query_selector("input#phone")
                if phone_input:
                    phone_input.fill("9980993977")

                # 4. Preferred First Name
                pref_input = page.query_selector("input#preferred_name")
                if pref_input and not pref_input.input_value().strip():
                    pref_input.fill("Drupadh")
                    print("[Greenhouse] Filled preferred name: Drupadh")

                # 5. LinkedIn Profile
                for sel in ("input#question_37337520002", "input[aria-label*='LinkedIn' i]", "input[id*='linkedin' i]"):
                    li_input = page.query_selector(sel)
                    if li_input and not li_input.input_value().strip():
                        li_input.fill("https://linkedin.com/in/drupadhsuresh")
                        print("[Greenhouse] Filled LinkedIn URL")
                        break
            except Exception as exc:
                print(f"[Greenhouse custom handler note] {exc}")

        # Take review screenshot
        try:
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"\n>>> Captured review screenshot: {screenshot_path}")
        except Exception as e:
            print(f"Screenshot note: {e}")

        failures = summary.get("field_failures", [])
        if failures:
            print(f"\n[ATTENTION] {len(failures)} fields may need attention: {failures}")
        else:
            print("\n[SUCCESS] All fields successfully filled with 0 errors!")

        print("\n" + "=" * 70)
        print("  THE BROWSER IS CURRENTLY OPEN ON YOUR SCREEN!")
        print("  You can review all the filled fields directly.")
        print("=" * 70)

        if auto_submit:
            bring_to_front()
            print("\n>>> Auto-Submit requested! Pausing 5s so you can see the filled form live...")
            page.wait_for_timeout(5000)
            print(">>> Submitting application now...")
            submitted = _submit(frame, 30000, ats=ats)
            
            print(">>> Waiting for submission confirmation or captcha challenge...")
            receipt = {"confirmed": False}
            receipt_screenshot = str(ROOT / "loot" / "reports" / f"submission_receipt_{ats}_{int(time.time())}.png")
            
            # Wait up to 120 seconds for submit or human captcha solve
            for i in range(60):
                page.wait_for_timeout(2000)
                
                # Check for ATS confirmation receipt
                receipt = _submission_receipt(page, 1500, ats=ats)
                current_url = str(getattr(page, "url", "") or "").lower()
                if receipt.get("confirmed") or any(k in current_url for k in ("thanks", "confirmation", "applied")):
                    print("\n" + "=" * 70)
                    print("  [SUCCESS] APPLICATION SUBMISSION CONFIRMED!")
                    print(f"  Confirmation URL: {page.url}")
                    print("=" * 70)
                    receipt["confirmed"] = True
                    break

                # Check if visual captcha challenge is active
                try:
                    ch_frame = page.query_selector("iframe[src*='challenge'], iframe[src*='hcaptcha'], iframe[src*='recaptcha']")
                    if ch_frame and ch_frame.is_visible():
                        if i % 3 == 0:
                            print(f"[{i*2}s] Captcha challenge active on screen! Please solve the quick puzzle/checkbox on your screen to complete submission...")
                except Exception:
                    pass

            try:
                page.screenshot(path=receipt_screenshot, full_page=True)
                print(f">>> Captured confirmation screenshot: {receipt_screenshot}")
            except Exception:
                pass
            print(">>> Keeping browser open 20s so you can see the confirmation on screen...")
            bring_to_front()
            page.wait_for_timeout(20000)
            return {"ok": True, "submitted": submitted, "receipt": receipt, "receipt_screenshot": receipt_screenshot}

        # Keep browser open for review
        print(f"\nKeeping browser open for your inspection (waiting up to {hold_open_seconds}s)...")
        print("Feel free to look at the form, scroll, or make any edits.")
        
        # Interactive loop
        start_wait = time.time()
        while time.time() - start_wait < hold_open_seconds:
            try:
                page.wait_for_timeout(2000)
                # Check if user closed the page manually
                if page.is_closed():
                    print("\nBrowser closed by user.")
                    break
            except Exception:
                break

        return {"ok": True, "submitted": False, "screenshot": screenshot_path}

    except Exception as exc:
        print(f"\n[ERROR] An exception occurred during apply: {exc}")
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": str(exc)}
    finally:
        try:
            if not page.is_closed():
                page.close()
            browser.close()
            pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live Controlled Browser Application")
    parser.add_argument("url", nargs="?", default=DEFAULT_TARGET_URL, help="Job posting URL")
    parser.add_argument("--resume", default=DEFAULT_RESUME, help="Path to resume PDF")
    parser.add_argument("--cover", default=None, help="Path to cover letter PDF")
    parser.add_argument("--submit", action="store_true", help="Auto submit after filling")
    parser.add_argument("--hold", type=int, default=300, help="Seconds to hold browser open")
    args = parser.parse_args()

    run_controlled_apply(
        url=args.url,
        resume_path=args.resume,
        cover_path=args.cover,
        auto_submit=args.submit,
        hold_open_seconds=args.hold
    )
