import os
import sys
import json
import time
import subprocess
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "docs", "assets")
APPS_FILE = os.path.join(ROOT, "loot", "state", "applications.json")
os.makedirs(OUT_DIR, exist_ok=True)

DEMO_APP_ID = "app_demo_review_sample"

DEMO_APP = {
    "applicationId": DEMO_APP_ID,
    "url": "https://boards.greenhouse.io/datadog/jobs/5829104",
    "status": "review",
    "statusHistory": [
        {"from": "queued", "to": "running", "at": int(time.time() * 1000) - 120000},
        {"from": "running", "to": "review", "at": int(time.time() * 1000) - 30000}
    ],
    "atsType": "greenhouse",
    "companyName": "Datadog",
    "companyDomain": "datadoghq.com",
    "logoUrl": "",
    "jobTitle": "Staff Application Security Engineer",
    "jobLocation": "New York, NY (Hybrid / Remote)",
    "jobDescription": "Securing cloud-scale infrastructure and distributed observability pipelines.",
    "createdAt": int(time.time() * 1000) - 150000,
    "updatedAt": int(time.time() * 1000) - 30000,
    "submitted": False,
    "dryRun": True,
    "error": None,
    "answersSummary": {
        "answered_count": 8,
        "questions_total": 8,
        "transport": "browser"
    },
    "sources": {
        "profile-direct": 5,
        "llm": 2,
        "user-override": 0,
        "skip": 1,
        "fallback": 1
    },
    "trace": {
        "meta": {
            "ats": "greenhouse",
            "outcome": "review",
            "startedAt": int(time.time() * 1000) - 120000,
            "durationMs": 42150
        },
        "answers": [
            {
                "fieldId": "first_name",
                "label": "First Name",
                "kind": "text",
                "source": "profile-direct",
                "value": "Alex",
                "required": True,
                "display": "Alex"
            },
            {
                "fieldId": "last_name",
                "label": "Last Name",
                "kind": "text",
                "source": "profile-direct",
                "value": "Taylor",
                "required": True,
                "display": "Taylor"
            },
            {
                "fieldId": "email",
                "label": "Email Address",
                "kind": "email",
                "source": "profile-direct",
                "value": "alex.taylor@example.com",
                "required": True,
                "display": "alex.taylor@example.com"
            },
            {
                "fieldId": "linkedin_profile",
                "label": "LinkedIn Profile URL",
                "kind": "url",
                "source": "profile-direct",
                "value": "https://linkedin.com/in/alex-taylor-cyber",
                "required": False,
                "display": "https://linkedin.com/in/alex-taylor-cyber"
            },
            {
                "fieldId": "why_datadog",
                "label": "Why are you interested in joining Datadog as an Application Security Engineer?",
                "kind": "textarea",
                "source": "llm",
                "value": "With 4+ years securing distributed cloud infrastructure, I have spearheaded automated vulnerability scanning, developed custom SAST/DAST rules, and partnered closely with product teams to shift security left. Datadog's focus on real-time observability aligns directly with my experience automating threat triage and building resilient security infrastructure.",
                "required": True,
                "display": "With 4+ years securing distributed cloud infrastructure, I have spearheaded automated vulnerability scanning..."
            },
            {
                "fieldId": "salary_expectation",
                "label": "Desired annual compensation expectation",
                "kind": "text",
                "source": "fallback",
                "value": "$165,000 - $185,000",
                "required": False,
                "display": "$165,000 - $185,000"
            },
            {
                "fieldId": "us_work_auth",
                "label": "Are you legally authorized to work in the United States?",
                "kind": "select",
                "source": "profile-direct",
                "value": "Yes",
                "required": True,
                "display": "Yes",
                "options": [{"label": "Yes", "value": "Yes"}, {"label": "No", "value": "No"}]
            },
            {
                "fieldId": "referral_employee",
                "label": "Employee Referral Code or Name",
                "kind": "text",
                "source": "skip",
                "value": "",
                "required": False,
                "display": "(none)"
            }
        ],
        "timeline": [
            {"phase": "fetch:start", "at": int(time.time() * 1000) - 120000},
            {"phase": "detect:greenhouse", "at": int(time.time() * 1000) - 118000},
            {"phase": "walk:form", "at": int(time.time() * 1000) - 100000},
            {"phase": "llm:answer_generation", "at": int(time.time() * 1000) - 60000},
            {"phase": "review_gate:ready", "at": int(time.time() * 1000) - 30000}
        ]
    },
    "documents": {
        "resume": {
            "status": "COMPLETED",
            "pdfGenerated": True,
            "useOptimizedResume": True
        },
        "coverLetter": {
            "status": "COMPLETED",
            "useCoverLetter": True,
            "pdfGenerated": True
        }
    }
}

def inject_demo_app():
    if not os.path.exists(APPS_FILE):
        return
    try:
        with open(APPS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("applications", {})[DEMO_APP_ID] = DEMO_APP
        with open(APPS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Warning: could not inject demo app: {e}")

def cleanup_demo_app():
    if not os.path.exists(APPS_FILE):
        return
    try:
        with open(APPS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if DEMO_APP_ID in data.get("applications", {}):
            del data["applications"][DEMO_APP_ID]
            with open(APPS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Warning: cleanup error: {e}")

def main():
    inject_demo_app()
    print("Starting Nori AI web server...")
    proc = subprocess.Popen(
        [os.path.join(ROOT, ".venv", "Scripts", "python.exe"), "-m", "uvicorn", "webapp.server:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    time.sleep(3)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                device_scale_factor=2,
                color_scheme="dark"
            )
            page = context.new_page()

            targets = [
                ("dashboard.png", "http://localhost:8000/", 3000, None),
                ("jobs.png", "http://localhost:8000/jobs", 3000, None),
                ("applications.png", "http://localhost:8000/applications", 2500, None),
                ("networking.png", "http://localhost:8000/networking", 2000, None),
                ("review-detail.png", f"http://localhost:8000/applications/{DEMO_APP_ID}", 2500, "review"),
            ]

            for filename, url, wait_ms, action in targets:
                print(f"Capturing {filename} from {url}...")
                try:
                    page.goto(url, wait_until="networkidle", timeout=15000)
                except Exception:
                    page.goto(url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(wait_ms)

                if action == "review":
                    # Click on Form answers tab and expand LLM question
                    tab_btn = page.locator('button:has-text("Form answers")')
                    if tab_btn.count() > 0:
                        tab_btn.first.click()
                        page.wait_for_timeout(1000)
                    why_q = page.locator('button:has-text("Why are you interested")')
                    if why_q.count() > 0:
                        why_q.first.click()
                        page.wait_for_timeout(1000)

                out_path = os.path.join(OUT_DIR, filename)
                page.screenshot(path=out_path, full_page=False)
                print(f"  -> Saved {out_path} ({os.path.getsize(out_path)} bytes)")

            browser.close()
    finally:
        print("Stopping web server...")
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
        cleanup_demo_app()
    print("Done!")

if __name__ == "__main__":
    main()
