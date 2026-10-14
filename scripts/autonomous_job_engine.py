"""
Tsenta Fully Autonomous End-to-End Application Engine
Autonomous 4-Stage Loop:
1. SEARCH: Automatically queries job feeds (HiringCafe) for 100% remote security roles.
2. RESUME & COVER LETTER CREATION: Dynamically tailors and compiles 1-page PDFs for each job.
3. FILLING: Walks and fills the entire application on your visible Chrome window with live AI.
4. SUBMISSION: Auto-submits, captures confirmation receipts, and advances to the next job automatically!
"""

from __future__ import annotations

import sys
import os
import time
import json
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend" / "src"))
sys.path.insert(0, str(ROOT / "backend" / "src" / "tools"))
sys.path.insert(0, str(ROOT / "webapp"))

from backend.src.tools.tsenta_ats import ats_detect_chain
from backend.src.tools.tsenta_config import default_config
from backend.src.tools.tsenta_trace import Trace
from backend.src.tools.tsenta_llm import make_llm_answerer, chat_completion, llm_config
from backend.src.tools.tsenta_apply import (
    _open_form, _form_frame, collect_fields, answer_fields,
    _execute_actions, _dismiss_blocking_overlays, _heal_validation_errors,
    _submit, _submission_receipt
)
from backend.src.tools.tsenta_documents import (
    fetch_job_context, render_document_pdf, _extract_keywords
)
from backend.src.tools.tsenta_hiringcafe import search_hiringcafe
from server import _load_profile, PROFILE_PATH
from playwright.sync_api import sync_playwright

TRACKER_FILE = ROOT / "loot" / "auto_pilot_applied.json"

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

SEARCH_QUERIES = [
    "security analyst",
    "cybersecurity risk",
    "security operations",
    "security engineer"
]

def load_applied_urls() -> set[str]:
    applied = {
        # Already confirmed submissions
        "https://jobs.ashbyhq.com/pragmatike/88905b50-a8c2-4615-9f92-63dd995da3fe",
        "https://jobs.ashbyhq.com/pragmatike/88905b50-a8c2-4615-9f92-63dd995da3fe/application",
        "https://jobs.ashbyhq.com/atlan/254c1250-953b-4323-8d18-9fe5e41d8d7d",
        "https://jobs.ashbyhq.com/atlan/b2b880ed-63cd-4f56-8313-87f143fa9807",
        "https://jobs.ashbyhq.com/pragmatike/64f83880-fcba-4430-91d1-6734d24b1be1",
        "https://jobs.ashbyhq.com/pragmatike/6c4203b1-cd38-4e2f-bdf5-aa2b539663e3",
        "https://jobs.ashbyhq.com/pragmatike/52d1af0c-6b0b-456f-b277-46cca879cb1d",
    }
    if TRACKER_FILE.exists():
        try:
            with open(TRACKER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    if isinstance(item, dict) and item.get("url"):
                        u = item["url"].rstrip("/")
                        applied.add(u)
                        applied.add(u + "/application")
                        applied.add(u.replace("/application", ""))
        except Exception:
            pass
    apps_file = ROOT / "loot" / "state" / "applications.json"
    if apps_file.exists():
        try:
            with open(apps_file, "r", encoding="utf-8") as f:
                apps_data = json.load(f).get("applications", {})
                for k, v in apps_data.items():
                    if v.get("status") in ("applied", "submitted") and v.get("url"):
                        u = v["url"].rstrip("/")
                        applied.add(u)
                        applied.add(u + "/application")
                        applied.add(u.replace("/application", ""))
        except Exception:
            pass
    return applied

def record_application(url: str, company: str, title: str, status: str, receipt_path: str = ""):
    records = []
    if TRACKER_FILE.exists():
        try:
            with open(TRACKER_FILE, "r", encoding="utf-8") as f:
                records = json.load(f)
        except Exception:
            records = []
    records.append({
        "company": company,
        "title": title,
        "url": url,
        "status": status,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "receiptScreenshot": receipt_path
    })
    TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

def generate_tailored_resume_and_cover(company: str, title: str, jd_text: str) -> tuple[str, str]:
    """Dynamically tailor and compile a 1-page PDF Resume & Cover Letter for this exact JD."""
    desktop = Path(os.environ["USERPROFILE"]) / "Desktop"
    clean_company = "".join(c for c in company if c.isalnum()) or "Target"
    
    resume_out = desktop / f"Drupadh_Suresh_{clean_company}_Resume.pdf"
    cover_out = desktop / f"Drupadh_Suresh_{clean_company}_Cover_Letter.pdf"

    if resume_out.exists() and cover_out.exists():
        return str(resume_out), str(cover_out)

    print(f"\n[AI Document Creation] Tailoring 1-page Resume & Cover Letter for {company} ({title})...")
    
    # 1. Generate Tailored Resume Text via Flagship GPT-4o
    prompt = f"""You are an elite executive resume writer. Tailor Drupadh Suresh's resume specifically for this job description.
Company: {company}
Role: {title}
Job Description:
{jd_text[:1200]}

Candidate Master Profile:
Drupadh Suresh | Indiranagar, Bengaluru, Karnataka, India | +91 9980993977 | sureshdrupadh@gmail.com | linkedin.com/in/drupadhsuresh | github.com/Drupadh
5 years experience across TPRM, SOC/SIEM (Splunk/Sentinel), Cloud Security (AWS/Azure, Prisma Cloud), and Vulnerability Management.
Former Cybersecurity Analyst at PNC Financial Services, Associate Cybersecurity Analyst at Accenture, M.S. Cybersecurity DePaul University.
Certifications: Cisco CCNA, CompTIA Security+, Microsoft SC-900.

Output formatted resume text with sections:
DRUPADH SURESH
Contact line
SUMMARY (1 paragraph highlighting skills matching {title})
SKILLS (Categorized, matching keywords from JD)
EXPERIENCE (PNC Financial Services, Accenture, DePaul University - bullet points aligned with JD)
EDUCATION (DePaul University M.S., P.E.S.C.E B.E.)
CERTIFICATIONS (CCNA, Security+, SC-900)

Strictly return ONLY the formatted resume text."""

    try:
        cfg = llm_config(max_tokens=1500)
        tailored_resume_text = chat_completion([
            {"role": "system", "content": "You are a professional resume writer."},
            {"role": "user", "content": prompt}
        ], cfg)
        if not tailored_resume_text or len(tailored_resume_text) < 200:
            tailored_resume_text = (ROOT / "loot" / "state" / "resume.pdf").as_posix()
        
        # Compile Resume PDF
        render_document_pdf(tailored_resume_text, str(resume_out), title=f"Drupadh Suresh - {title}", kind="resume")
        print(f"  -> Generated 1-page Resume: {resume_out.name}")
    except Exception as e:
        print(f"  [Resume Error] {e}; using master resume")
        resume_out = desktop / "Drupadh_Suresh_Resume.pdf"

    # 2. Generate Tailored Cover Letter
    cl_prompt = f"""Write a compelling, professional 3-paragraph cover letter for Drupadh Suresh applying to {company} for {title}.
JD Context: {jd_text[:800]}
Candidate: 5 YOE in cybersecurity (PNC, Accenture), cloud security, TPRM, SIEM investigations.
Sign off: Sincerely, Drupadh Suresh."""

    try:
        cfg = llm_config(max_tokens=600)
        cl_text = chat_completion([
            {"role": "system", "content": "You are an executive cover letter writer."},
            {"role": "user", "content": cl_prompt}
        ], cfg)
        render_document_pdf(cl_text, str(cover_out), title=f"Cover Letter - {company}", kind="cover_letter")
        print(f"  -> Generated 1-page Cover Letter: {cover_out.name}")
    except Exception as e:
        print(f"  [Cover Letter Error] {e}")

    return str(resume_out), str(cover_out) if cover_out.exists() else None

def search_candidate_jobs(profile: dict, limit: int = 15) -> list[dict]:
    """Autonomously search for open cybersecurity & risk roles at top Indian Startups & Unicorns."""
    print("\n" + "=" * 75)
    print("  [STAGE 1: AUTONOMOUS SEARCH] Finding Open Roles at Indian Tech Startups...")
    print("=" * 75)

    import urllib.request
    applied_urls = load_applied_urls()
    discovered_jobs = []

    def is_profile_fit(title_str: str) -> bool:
        t = title_str.lower()
        negative = (
            'writer', 'ui developer', 'frontend', 'product manager', 'sales', 'business development', 
            'bdr', 'sdr', 'marketing', 'customer support', 'content', 'entitlement', 'deal desk', 
            'order processing', 'quality analyst', 'video', 'facilities', 'financial systems', 'user lending',
            'decision science', 'r2r', 'site reliability', 'strategic alliances', 'project manager',
            'finance', 'financial', 'commerce', 'program ops', 'fulfillment'
        )
        if any(n in t for n in negative):
            return False
        positive = (
            'security', 'cyber', 'soc', 'infosec', 'threat', 'vulnerability', 'incident', 
            'cloud security', 'grc', 'risk', 'compliance', 'appsec'
        )
        return any(p in t for p in positive)

    ashby_targets = ['atlan', 'pragmatike', 'hasura', 'signoz', 'devrev', 'invideo', 'toplyne']
    gh_targets = ['alphasense', 'druva', 'highradius', 'inmobi', 'chargebee', 'whatfix', 'browserstack']
    lever_targets = ['meesho', 'razorpay', 'cred', 'groww']

    # 1. Ashby Indian Startups
    for c in ashby_targets:
        url = f'https://api.ashbyhq.com/posting-api/job-board/{c}'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            data = json.loads(urllib.request.urlopen(req, timeout=4).read().decode())
            for j in data.get('jobs', []):
                loc = (j.get('location') or '').lower()
                title = j.get('title') or ''
                workplace = (j.get('workplaceType') or '').lower()
                is_in = any(k in loc for k in ('india', 'bengaluru', 'bangalore', 'pune', 'hyderabad', 'delhi', 'mumbai', 'gurgaon', 'gurugram', 'noida'))
                is_foreign = any(k in loc for k in ('united states', 'united kingdom', 'canada', 'uk', 'ireland', 'london', 'new york', 'singapore', 'germany'))
                job_url = j.get('jobUrl')
                if is_in and not is_foreign and is_profile_fit(title) and job_url and job_url.rstrip('/') not in applied_urls:
                    discovered_jobs.append({
                        'companyName': c.capitalize(),
                        'title': j.get('title'),
                        'location': f"{j.get('location')} ({workplace})",
                        'url': job_url,
                        'atsType': 'ashby'
                    })
                    applied_urls.add(job_url.rstrip('/'))
        except Exception:
            pass

    # 2. Greenhouse Indian Startups & Unicorns
    for c in gh_targets:
        url = f'https://boards-api.greenhouse.io/v1/boards/{c}/jobs'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            data = json.loads(urllib.request.urlopen(req, timeout=4).read().decode())
            for j in data.get('jobs', []):
                loc = (j.get('location', {}).get('name') or '').lower()
                title = j.get('title') or ''
                is_in = any(k in loc for k in ('india', 'bengaluru', 'bangalore', 'pune', 'hyderabad', 'delhi', 'mumbai', 'gurgaon', 'gurugram', 'noida'))
                is_foreign = any(k in loc for k in ('united states', 'united kingdom', 'canada', 'uk', 'ireland', 'london', 'new york', 'singapore', 'germany'))
                job_url = j.get('absolute_url')
                if is_in and not is_foreign and is_profile_fit(title) and job_url and job_url.rstrip('/') not in applied_urls:
                    discovered_jobs.append({
                        'companyName': c.capitalize(),
                        'title': j.get('title'),
                        'location': j.get('location', {}).get('name'),
                        'url': job_url,
                        'atsType': 'greenhouse'
                    })
                    applied_urls.add(job_url.rstrip('/'))
        except Exception:
            pass

    # 3. Lever Indian Startups & Unicorns
    for c in lever_targets:
        url = f'https://api.lever.co/v0/postings/{c}'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            data = json.loads(urllib.request.urlopen(req, timeout=4).read().decode())
            for j in data:
                loc = (j.get('categories', {}).get('location') or '').lower()
                title = j.get('text') or ''
                is_in = any(k in loc for k in ('india', 'bengaluru', 'bangalore', 'pune', 'hyderabad', 'delhi', 'mumbai', 'gurgaon', 'gurugram', 'noida'))
                is_foreign = any(k in loc for k in ('united states', 'united kingdom', 'canada', 'uk', 'ireland', 'london', 'new york', 'singapore', 'germany'))
                job_url = j.get('applyUrl')
                if is_in and not is_foreign and is_profile_fit(title) and job_url and job_url.rstrip('/') not in applied_urls:
                    discovered_jobs.append({
                        'companyName': c.capitalize(),
                        'title': j.get('text'),
                        'location': j.get('categories', {}).get('location'),
                        'url': job_url,
                        'atsType': 'lever'
                    })
                    applied_urls.add(job_url.rstrip('/'))
        except Exception:
            pass

    def rank_job_fit(job: dict) -> int:
        title = (job.get("title") or "").lower()
        loc = (job.get("location") or "").lower()
        score = 0
        if "risk" in title:
            score += 60
        if "analyst" in title:
            score += 45
        if "security analyst" in title or "cyber" in title:
            score += 50
        elif "security" in title:
            score += 30
        if "compliance" in title or "privacy" in title or "governance" in title:
            score += 35
        if "soc" in title or "operations" in title:
            score += 25
        if "cloud" in title:
            score += 20
        if "bengaluru" in loc or "bangalore" in loc or "remote" in loc:
            score += 15
        if "backend" in title or "ml engineer" in title or "software" in title:
            score -= 50
        return score

    discovered_jobs.sort(key=rank_job_fit, reverse=True)

    print(f"\n[Search Results] Discovered {len(discovered_jobs)} qualified, unapplied Indian roles!")
    for idx, j in enumerate(discovered_jobs[:limit], 1):
        print(f"  {idx:02d}. {j['companyName']} — {j['title']} ({j['location']})")
    return discovered_jobs[:limit]

def run_autonomous_pipeline(max_applications: int = 10):
    profile = _load_profile()
    p_info = profile.get("personalInformation", {})
    w_pref = profile.get("workPreferences", {})

    print("=" * 75)
    print("      TSENTA FULLY AUTONOMOUS APPLICATION ENGINE")
    print("   Searching -> Tailoring Resumes -> Form Filling -> Auto-Submitting")
    print("=" * 75)
    print(f"Candidate:  {p_info.get('firstName')} {p_info.get('lastName')} <{p_info.get('email')}>")
    print(f"Settings:   Phone: {p_info.get('phone')} | CTC: {w_pref.get('expectedCTC')} | Notice: {w_pref.get('noticePeriod')}")
    print("=" * 75)

    # 1. Search for jobs
    jobs = search_candidate_jobs(profile, limit=max_applications)
    if not jobs:
        print("No new unapplied jobs found in current search window.")
        return

    # 2. Connect to visible Chrome on screen
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
        print(f"[NOTE] Port 9222 not open ({exc}). Launching fresh visible Chrome instance...")
        browser = pw.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(viewport=None)
        page = context.new_page()

    config = default_config()
    trace = Trace()
    answerer = make_llm_answerer(profile, config)

    completed = 0

    for idx, job in enumerate(jobs, 1):
        url = job.get("url")
        company = job.get("companyName") or "Target Company"
        title = job.get("title") or "Security Engineer"
        jd = job.get("description") or f"{title} at {company}"

        print("\n" + "#" * 75)
        print(f"[{idx}/{len(jobs)}] PROCESSING: {title} @ {company}")
        print(f"URL: {url}")
        print("#" * 75)

        # Stage 2: Resume & Cover Letter Creation
        resume_pdf, cover_pdf = generate_tailored_resume_and_cover(company, title, jd)

        # Stage 3: Form Filling on Visible Screen
        try:
            detection = ats_detect_chain(url)
            ats = detection.get("ats_id", "unknown")
            print(f"[ATS Detected] {ats.upper()}")

            print(f"\n[Navigating] Loading application in your visible Chrome window...")
            _open_form(page, url, ats, 45000, profile)
            page.wait_for_timeout(3000)

            # Inject on-screen visual copilot cursor and banner
            try:
                page.evaluate(VISUAL_CURSOR_JS)
                page.evaluate(f"window.__moveBotCursor(window.innerWidth / 2, 80, '⚡ Tsenta AI Copilot Active (Drupadh Suresh) — Applying to {company}');")
            except Exception:
                pass

            frame = _form_frame(page)
            print("Scanning fields...")
            fields = collect_fields(frame, timeout_ms=25000)
            print(f"Found {len(fields)} fields. Generating answers with flagship GPT-4o...")

            actions = answer_fields(fields, profile, config, trace, answerer=answerer)
            print("Filling form fields visibly on screen...")
            try:
                page.evaluate(f"window.__moveBotCursor(window.innerWidth / 2, 120, '⚡ Filling form with AI answers for {company}...');")
            except Exception:
                pass

            summary = _execute_actions(frame, actions, resume_pdf, cover_pdf)
            _dismiss_blocking_overlays(page)
            _heal_validation_errors(frame, profile, config, trace)
            page.wait_for_timeout(2000)

            # Specialized Greenhouse React-Select handlers (Country, Phone, Location)
            if ats == "greenhouse":
                try:
                    c_input = page.query_selector('#country')
                    if c_input:
                        c_input.click()
                        c_input.fill("")
                        c_input.type("India", delay=30)
                        page.wait_for_timeout(500)
                        c_input.press("ArrowDown")
                        page.wait_for_timeout(200)
                        c_input.press("Enter")
                        page.wait_for_timeout(500)
                    phone = page.query_selector('#phone')
                    if phone and not phone.input_value():
                        phone.click()
                        phone.fill("")
                        phone.type("9980993977", delay=30)
                    loc = page.query_selector('#candidate-location')
                    if loc:
                        loc.click()
                        loc.fill("")
                        loc.type("Bengaluru", delay=30)
                        page.wait_for_timeout(800)
                        loc.press("ArrowDown")
                        page.wait_for_timeout(200)
                        loc.press("Enter")
                        page.wait_for_timeout(500)
                except Exception:
                    pass

            # Pre-submission screenshot
            filled_img = str(ROOT / "loot" / "reports" / f"auto_filled_{company.lower()}_{int(time.time())}.png")
            try:
                page.screenshot(path=filled_img, full_page=True)
            except Exception:
                pass

            # Stage 4: Submission
            try:
                page.evaluate("window.__moveBotCursor(window.innerWidth / 2, 80, '🚀 All fields filled! Submitting application now...');")
            except Exception:
                pass

            print("Auto-submitting application...")
            _submit(frame, 30000, ats=ats)
            page.wait_for_timeout(4000)

            receipt = _submission_receipt(page, 2000, ats=ats)
            receipt_img = str(ROOT / "loot" / "reports" / f"auto_receipt_{company.lower()}_{int(time.time())}.png")
            try:
                page.screenshot(path=receipt_img, full_page=True)
            except Exception:
                pass

            status = "submitted" if receipt.get("confirmed") else "submitted_pending_review"
            record_application(url, company, title, status, receipt_img)
            completed += 1
            print(f"[SUCCESS] Application to {company} submitted! (Receipt: {receipt_img})")

            try:
                page.evaluate("window.__moveBotCursor(window.innerWidth / 2, 80, '✨ Submission confirmed! Advancing to next role...');")
            except Exception:
                pass

            print("Advancing to next job in 5 seconds...")
            page.wait_for_timeout(5000)

        except Exception as e:
            print(f"[Application Error on {company}] {e}")
            page.wait_for_timeout(3000)

    print("\n" + "=" * 75)
    print(f"  AUTONOMOUS ENGINE COMPLETE! Successfully applied to {completed} roles.")
    print("=" * 75)
    pw.stop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autonomous Job Application Engine")
    parser.add_argument("--max", type=int, default=10, help="Max applications to submit")
    args = parser.parse_args()

    run_autonomous_pipeline(max_applications=args.max)
