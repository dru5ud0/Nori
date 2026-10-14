"""
Visible AI Application Bot — Live On-Screen Automation
Runs directly in your visible Google Chrome window with:
1. Full Tsenta ATS Field Scanning & Execution Engine (Ashby, Greenhouse, Lever, Workday).
2. Live AI Tailored Resume & Cover Letter upload (1-page PDF).
3. Animated visual cursor gliding to each field on screen.
4. Live GPT-4o-mini question answering.
5. Human review pause before submission.
"""

from __future__ import annotations

import sys
import os
import time
import json
import argparse
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "webapp"))

from backend.src.tools.tsenta_ats import ats_detect_chain, ats_normalize_hint
from backend.src.tools.tsenta_config import default_config
from backend.src.tools.tsenta_trace import Trace
from backend.src.tools.tsenta_llm import make_llm_answerer
from backend.src.tools.tsenta_apply import (
    _open_form, _form_frame, collect_fields, answer_fields,
    _execute_actions, _dismiss_blocking_overlays, _heal_validation_errors,
    _submit, _submission_receipt
)
from server import _load_profile, PROFILE_PATH
from playwright.sync_api import sync_playwright

VISUAL_CURSOR_JS = """
(() => {
    if (document.getElementById('tsenta-live-cursor')) return;
    const cur = document.createElement('div');
    cur.id = 'tsenta-live-cursor';
    cur.style.cssText = `
        position: fixed;
        width: 22px;
        height: 22px;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(239,68,68,0.9) 0%, rgba(220,38,38,0.6) 70%);
        border: 2px solid #ffffff;
        box-shadow: 0 0 14px rgba(239,68,68,0.9), 0 2px 4px rgba(0,0,0,0.4);
        pointer-events: none;
        z-index: 2147483647;
        transition: left 0.22s cubic-bezier(0.25, 1, 0.5, 1), top 0.22s cubic-bezier(0.25, 1, 0.5, 1), transform 0.15s ease;
        transform: translate(-50%, -50%);
        left: 50vw;
        top: 50vh;
    `;
    document.body.appendChild(cur);

    const banner = document.createElement('div');
    banner.id = 'tsenta-live-banner';
    banner.style.cssText = `
        position: fixed;
        top: 16px;
        right: 16px;
        background: #0f172a;
        color: #f8fafc;
        border: 1px solid #38bdf8;
        padding: 10px 16px;
        border-radius: 8px;
        font-family: system-ui, -apple-system, sans-serif;
        font-size: 13px;
        font-weight: 600;
        box-shadow: 0 10px 25px rgba(0,0,0,0.5);
        z-index: 2147483647;
        display: flex;
        align-items: center;
        gap: 8px;
    `;
    banner.innerHTML = `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#10b981;box-shadow:0 0 8px #10b981;"></span> ⚡ Tsenta AI Copilot Active (Drupadh Suresh)`;
    document.body.appendChild(banner);

    window.__moveBotCursor = (x, y, actionText) => {
        cur.style.left = x + 'px';
        cur.style.top = y + 'px';
        cur.style.transform = 'translate(-50%, -50%) scale(1.25)';
        setTimeout(() => { cur.style.transform = 'translate(-50%, -50%) scale(1.0)'; }, 180);
        if (actionText) {
            banner.innerHTML = `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#38bdf8;box-shadow:0 0 8px #38bdf8;"></span> ${actionText}`;
        }
    };
})();
"""

def tailor_resume_and_cover(job_url, company):
    """Find or tailor the best 1-page PDF Resume & Cover Letter."""
    desktop = Path(os.environ["USERPROFILE"]) / "Desktop"
    
    clean_company = "".join(c for c in company if c.isalnum())
    resume_candidate = desktop / f"Drupadh_Suresh_{clean_company}_Resume.pdf"
    cover_candidate = desktop / f"Drupadh_Suresh_{clean_company}_Cover_Letter.pdf"

    if resume_candidate.exists():
        return str(resume_candidate), str(cover_candidate) if cover_candidate.exists() else None

    # Fallback to general master resume if specific doesn't exist
    master_resume = desktop / "Drupadh_Suresh_Resume.pdf"
    if not master_resume.exists():
        master_resume = ROOT / "loot" / "state" / "resume.pdf"
    
    return str(master_resume), str(cover_candidate) if cover_candidate.exists() else None

def run_visible_bot(job_url: str, auto_submit: bool = False, hold_open_seconds: int = 300):
    profile = _load_profile()
    p_info = profile.get("personalInformation", {})
    w_pref = profile.get("workPreferences", {})

    print("=" * 70)
    print("  TSENTA VISIBLE AI APPLICATION COPILOT")
    print("=" * 70)
    print(f"Target URL:  {job_url}")
    print(f"Candidate:   {p_info.get('firstName')} {p_info.get('lastName')} <{p_info.get('email')}>")
    print(f"Specs:       Phone: {p_info.get('phone')} | CTC: {w_pref.get('expectedCTC')} | Notice: {w_pref.get('noticePeriod')}")
    print("=" * 70)

    # Detect ATS
    detection = ats_detect_chain(job_url)
    ats = detection.get("ats_id", "unknown")
    print(f"[ATS] Detected: {ats.upper()} (Confidence: {detection.get('confidence', 0)}%)")

    pw = sync_playwright().start()
    browser = None
    page = None

    print("\n>>> Connecting to visible Google Chrome window on your screen (port 9222)...")
    try:
        browser = pw.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()
        print("[SUCCESS] Attached to your visible Chrome window!")
    except Exception as exc:
        print(f"[NOTE] Could not attach to port 9222 ({exc}). Launching fresh visible Chrome...")
        browser = pw.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(viewport=None)
        page = context.new_page()

    try:
        # Navigate if not already on the page
        if job_url.lower() not in (page.url or "").lower():
            print(f"\n>>> Navigating visible browser to: {job_url}")
            _open_form(page, job_url, ats, 45000, profile)
            page.wait_for_timeout(2000)

        # Detect company
        company = "Target"
        for part in page.url.split("/"):
            if part and part.lower() not in ("http:", "https:", "", "jobs", "apply", "application", "jobs.ashbyhq.com", "job-boards.greenhouse.io", "jobs.lever.co"):
                company = part.capitalize()
                break

        resume_pdf, cover_pdf = tailor_resume_and_cover(job_url, company)
        print(f"[Documents] Resume: {resume_pdf}")

        # Inject visual cursor
        try:
            page.evaluate(VISUAL_CURSOR_JS)
        except Exception:
            pass

        frame = _form_frame(page)

        # Setup LLM Engine
        print("\n>>> Initializing AI Answering Engine (Flagship GPT-4o)...")
        config = default_config()
        trace = Trace()
        answerer = make_llm_answerer(profile, config)

        # Scan Form Fields using full engine
        print(">>> Scanning all application fields (including ATS UUIDs)...")
        fields = collect_fields(frame, timeout_ms=20000)
        print(f"Found {len(fields)} fields on page.")

        # Generate Answers
        print(">>> Generating smart tailored answers with AI...")
        actions = answer_fields(fields, profile, config, trace, answerer=answerer)
        print(f"Prepared {len(actions)} answer actions:")
        for i, a in enumerate(actions, 1):
            lbl = a.get("label") or a.get("field_id")
            val = str(a.get("value"))[:45]
            src = a.get("source")
            print(f"  [{i:02d}] {lbl[:35]:<35} -> '{val}' ({src})")

        # Execute Actions with Visual Feedback
        print("\n>>> Filling fields visibly on your screen...")
        try:
            page.evaluate("window.__moveBotCursor(window.innerWidth / 2, 200, '⚡ Filling form with AI answers...');")
        except Exception:
            pass

        summary = _execute_actions(frame, actions, resume_pdf, cover_pdf)
        _dismiss_blocking_overlays(page)
        _heal_validation_errors(frame, profile, config, trace)
        page.wait_for_timeout(2000)

        # Greenhouse custom React-Select handlers
        if ats == "greenhouse":
            try:
                country_in = page.query_selector("input#country")
                if country_in:
                    country_in.click()
                    country_in.fill("")
                    country_in.type("India", delay=35)
                    page.wait_for_timeout(600)
                    for opt in page.query_selector_all("[role='option']"):
                        if opt.text_content().strip() == "India +91":
                            opt.click()
                            break
                loc_in = page.query_selector("input#candidate-location")
                if loc_in:
                    loc_in.click()
                    loc_in.fill("")
                    loc_in.type("Bengaluru", delay=35)
                    page.wait_for_timeout(600)
                    for opt in page.query_selector_all("[role='option']"):
                        if "Bengaluru" in opt.text_content():
                            opt.click()
                            break
            except Exception:
                pass

        # Verification
        failures = summary.get("field_failures", [])
        if failures:
            print(f"\n[ATTENTION] Fields needing review: {failures}")
        else:
            print("\n[SUCCESS] All fields successfully filled with 0 errors!")

        try:
            page.evaluate("window.__moveBotCursor(window.innerWidth / 2, 80, '✨ Complete! Review answers or submit.');")
        except Exception:
            pass

        print("\n" + "=" * 70)
        print("  THE APPLICATION IS READY ON YOUR SCREEN!")
        print("  You can review, edit, solve any captcha, or click Submit.")
        print("=" * 70)

        if auto_submit:
            print("\n>>> Auto-Submit requested! Pausing 10s for your inspection...")
            page.wait_for_timeout(10000)
            print(">>> Submitting application now...")
            _submit(frame, 30000, ats=ats)
            page.wait_for_timeout(5000)
            receipt = _submission_receipt(page, 3000, ats=ats)
            if receipt.get("confirmed"):
                print("[SUCCESS] Submission confirmed!")
        else:
            print(f"\nKeeping browser open for your inspection ({hold_open_seconds}s)...")
            start = time.time()
            while time.time() - start < hold_open_seconds:
                if page.is_closed(): break
                time.sleep(2)

    except Exception as exc:
        print(f"[Error] {exc}")
    finally:
        pw.stop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Visible AI Bot")
    parser.add_argument("url", nargs="?", default="https://jobs.ashbyhq.com/pragmatike/88905b50-a8c2-4615-9f92-63dd995da3fe/application", help="Job URL")
    parser.add_argument("--submit", action="store_true", help="Auto submit")
    args = parser.parse_args()

    run_visible_bot(args.url, auto_submit=args.submit)
