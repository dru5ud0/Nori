"""Browser-level smoke test for TsentaClone's unpacked local extension."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.async_api import Route, async_playwright


ROOT = Path(__file__).resolve().parents[2]
EXTENSION = ROOT / "extension"
PROFILE = ROOT / "loot" / f".extension-smoke-profile-{os.getpid()}"
BRAVE = Path.home() / "AppData/Local/BraveSoftware/Brave-Browser/Application/brave.exe"

PROFILE_MAIN = """
<main>
  <h1>Test Recruiter</h1>
  <div>Test Recruiter · 2nd</div>
  <div>Senior Technical Recruiter — W2 and STEM OPT roles</div>
  <div>Chicago, Illinois, United States</div>
  <button>Pride RPO Private Limited</button>
  <section><h2>About</h2><p>E-Verify employer supporting I-983 training plans.</p></section>
</main>
"""

JOB_MAIN = """
<main>
  <div class="job-details-jobs-unified-top-card__job-title"><h1>Data Engineer</h1></div>
  <div class="job-details-jobs-unified-top-card__company-name"><a>United Airlines</a></div>
  <div class="job-details-jobs-unified-top-card__primary-description-container">Chicago, IL · Hybrid</div>
</main>
"""


async def main() -> None:
    PROFILE.parent.mkdir(parents=True, exist_ok=True)
    captured_contacts: list[dict] = []
    captured_applications: list[dict] = []

    async with async_playwright() as playwright:
        browser_choice = {"executable_path": str(BRAVE)} if BRAVE.exists() else {"channel": "chromium"}
        context = await playwright.chromium.launch_persistent_context(
            str(PROFILE),
            headless=True,
            args=[
                f"--disable-extensions-except={EXTENSION}",
                f"--load-extension={EXTENSION}",
            ],
            **browser_choice,
        )

        async def linkedin(route: Route) -> None:
            url = route.request.url
            if "/jobs/" in url:
                title, main_html = "Data Engineer | LinkedIn", JOB_MAIN
            elif "/in/" in url:
                title, main_html = "Test Recruiter | LinkedIn", PROFILE_MAIN
            else:
                title, main_html = "Notifications | LinkedIn", "<main><h1>Notifications</h1></main>"
            await route.fulfill(
                status=200,
                content_type="text/html",
                body=f"<!doctype html><html><head><title>{title}</title></head><body>{main_html}</body></html>",
            )

        async def local_api(route: Route) -> None:
            request = route.request
            payload = json.loads(request.post_data or "{}")
            path = urlsplit(request.url).path
            if path.endswith("/api/networking/contacts"):
                captured_contacts.append(payload)
                response = {"contact": {"score": 72}}
            elif path.endswith("/api/preflight"):
                target = parse_qs(urlsplit(request.url).query).get("url", [""])[0]
                if "duplicate" in target:
                    response = {
                        "ok": True,
                        "url": target,
                        "canQueue": False,
                        "blockers": ["duplicate-application"],
                        "warnings": [],
                    }
                else:
                    response = {
                        "ok": True,
                        "url": "https://careers.example.test/jobs/424242",
                        "canQueue": True,
                        "blockers": [],
                        "warnings": [],
                    }
            elif path.endswith("/api/applications"):
                captured_applications.append(payload)
                response = {"ok": True, "applicationId": "app_smoke", "status": "queued"}
            else:
                response = {}
            await route.fulfill(
                status=200,
                content_type="application/json",
                headers={"Access-Control-Allow-Origin": "*"},
                body=json.dumps(response),
            )

        await context.route("https://www.linkedin.com/**", linkedin)
        await context.route("http://127.0.0.1:8000/api/**", local_api)

        workers = context.service_workers
        worker = workers[0] if workers else await context.wait_for_event("serviceworker")
        entry = {
            "jobId": "424242",
            "title": "Data Engineer",
            "company": "External application",
            "url": "https://careers.example.test/jobs/424242",
            "source": "linkedin-rsc",
        }
        await worker.evaluate("entry => chrome.storage.local.set({tsenta_ln_entries: [entry]})", entry)

        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.linkedin.com/notifications/")
        await page.wait_for_timeout(1800)
        assert await page.locator("#tsenta-network-capture").count() == 0
        assert await page.locator("#tsenta-job-overlay").count() == 0

        # LinkedIn uses history navigation; controls must follow it without reload.
        await page.evaluate(
            """html => {
              history.pushState({}, '', '/in/test-recruiter');
              document.title = 'Test Recruiter | LinkedIn';
              document.body.innerHTML = html;
            }""",
            PROFILE_MAIN,
        )
        await page.wait_for_timeout(1000)
        assert await page.locator("#tsenta-network-capture button").count() == 1
        assert await page.locator("#tsenta-job-overlay").count() == 0
        recruiter_css = await page.locator("#tsenta-network-capture").evaluate("node => node.shadowRoot.textContent")
        assert "#fffdf6" in recruiter_css and "#ffd447" in recruiter_css
        await page.locator("#tsenta-network-capture button").click()
        await page.wait_for_timeout(300)
        contact = captured_contacts[-1]["contact"]
        assert contact["name"] == "Test Recruiter"
        assert contact["company"] == "Pride RPO Private Limited"
        assert "Chicago" in contact["location"]
        assert contact["connectionDegree"] == "2nd"
        profile_status = await worker.evaluate(
            """async () => {
              const tabs = await chrome.tabs.query({});
              const tab = tabs.find(item => (item.url || '').includes('linkedin.com/in/test-recruiter'));
              return chrome.tabs.sendMessage(tab.id, {type: 'TSENTA_PROFILE_STATUS'});
            }"""
        )
        assert profile_status["profilePage"] is True
        assert profile_status["controlVisible"] is True
        profile_badge = await worker.evaluate(
            """async () => {
              const tabs = await chrome.tabs.query({});
              const tab = tabs.find(item => (item.url || '').includes('linkedin.com/in/test-recruiter'));
              return chrome.action.getBadgeText({tabId: tab.id});
            }"""
        )
        assert profile_badge == "CRM"

        await page.evaluate(
            """html => {
              history.pushState({}, '', '/jobs/search/?currentJobId=424242');
              document.title = 'Data Engineer | LinkedIn';
              document.body.innerHTML = html;
            }""",
            JOB_MAIN,
        )
        await page.wait_for_timeout(1800)
        assert await page.locator("#tsenta-network-capture").count() == 0
        job_button_count = await page.locator("#tsenta-job-overlay").evaluate(
            "node => node.shadowRoot.querySelectorAll('.prepare').length"
        )
        if job_button_count != 1:
            stored = await worker.evaluate("() => chrome.storage.local.get(['tsenta_ln_entries'])")
            roots = await page.locator("[id^='tsenta-']").evaluate_all("nodes => nodes.map(node => node.id)")
            rail_state = await page.locator("#tsenta-job-overlay").evaluate(
                "node => ({hasShadow: !!node.shadowRoot, html: node.shadowRoot && node.shadowRoot.innerHTML})"
            )
            raise AssertionError(
                f"job rail missing; url={page.url!r} stored={stored!r} roots={roots!r} rail={rail_state!r}"
            )
        job_text = await page.locator("#tsenta-job-overlay").evaluate("node => node.shadowRoot.textContent")
        assert "United Airlines" in job_text
        assert "#fffdf6" in job_text and "#2864dc" in job_text and "#ffd447" in job_text
        assert not captured_applications, "A job was queued before explicit user action"
        page_status = await worker.evaluate(
            """async () => {
              const tabs = await chrome.tabs.query({});
              const tab = tabs.find(item => (item.url || '').includes('currentJobId=424242'));
              return chrome.tabs.sendMessage(tab.id, {type: 'TSENTA_PAGE_STATUS'});
            }"""
        )
        assert page_status["jobContext"] is True
        assert page_status["overlayVisible"] is True
        assert page_status["selected"]["jobId"] == "424242"
        job_badge = await worker.evaluate(
            """async () => {
              const tabs = await chrome.tabs.query({});
              const tab = tabs.find(item => (item.url || '').includes('currentJobId=424242'));
              return chrome.action.getBadgeText({tabId: tab.id});
            }"""
        )
        assert job_badge == "JOB"

        await page.locator("#tsenta-job-overlay").evaluate(
            "node => node.shadowRoot.querySelector('.prepare').click()"
        )
        await page.wait_for_timeout(400)
        assert len(captured_applications) == 1
        application = captured_applications[0]
        assert application["job_title"] == "Data Engineer"
        assert application["company_name"] == "United Airlines"
        assert application["url"] == "https://careers.example.test/jobs/424242"
        job_text = await page.locator("#tsenta-job-overlay").evaluate("node => node.shadowRoot.textContent")
        assert "Already queued" in job_text, f"unexpected queued state: {job_text!r}"

        # A duplicate preflight must never create another application.
        duplicate = {
            "jobId": "434343",
            "title": "Platform Engineer",
            "company": "Example Corp",
            "url": "https://jobs.example.test/duplicate/434343",
            "source": "linkedin-rsc",
        }
        await page.evaluate(
            """entry => {
              window.postMessage({type: 'TSENTA_LN_RSC_ENTRIES', entries: [entry]}, '*');
              history.pushState({}, '', '/jobs/search/?currentJobId=434343');
            }""",
            duplicate,
        )
        await page.wait_for_timeout(1500)
        await page.locator("#tsenta-job-overlay").evaluate(
            "node => node.shadowRoot.querySelector('.prepare').click()"
        )
        await page.wait_for_timeout(300)
        assert len(captured_applications) == 1
        duplicate_text = await page.locator("#tsenta-job-overlay").evaluate("node => node.shadowRoot.textContent")
        assert "Already queued" in duplicate_text

        extension_id = worker.url.split("/")[2]
        popup = await context.new_page()
        await popup.goto(f"chrome-extension://{extension_id}/popup.html")
        await popup.wait_for_timeout(500)
        assert await popup.locator("#server-status").text_content() == "ONLINE"
        assert await popup.locator("#version").text_content() == "v0.12.0"
        assert await popup.locator("#open-control").count() == 1
        assert await popup.locator("#open-networking").count() == 1

        browser_name = "Brave" if BRAVE.exists() else "Chromium"
        print(f"PASS ({browser_name}): content scripts, status messages, popup, explicit queue, and duplicate blocking")
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
