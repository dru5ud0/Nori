"""Regression tests for the local FastAPI webapp contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from webapp import server  # noqa: E402


def _profile() -> dict:
    return {
        "personalInformation": {
            "firstName": "Jane",
            "lastName": "Doe",
            "email": "jane@example.com",
            "phone": "+15550100",
            "address": "123 Main St",
            "city": "San Francisco",
            "state": "CA",
            "zipCode": "94105",
            "country": "US",
        },
        "workAuthorization": {
            "isAuthorizedToWork": True,
            "needsSponsorship": False,
            "reviewedAt": "2026-09-06T00:00:00Z",
        },
        "resumeFormat": "pdf",
    }


def _job(app_id: str = "app_test") -> dict:
    return {
        "applicationId": app_id,
        "url": "https://boards.greenhouse.io/acme/jobs/123",
        "status": "review",
        "statusHistory": [{"status": "review", "timestamp": 1}],
        "submitted": False,
        "atsType": "greenhouse",
        "companyName": "Acme",
        "companyDomain": "acme.com",
        "logoUrl": "https://example.test/acme.png",
        "jobTitle": "Engineer",
        "createdAt": 1,
        "updatedAt": 2,
        "error": None,
        "trace": {
            "meta": {"ats": "greenhouse", "outcome": "dry-run"},
            "answers": [{"fieldId": "email", "label": "Email"}],
            "timeline": [],
            "derivedMissingFields": [],
        },
    }


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    store = tmp_path / "applications.json"
    profile = tmp_path / "profile.json"
    store.write_text(json.dumps({"applications": {"app_test": _job()}}), encoding="utf-8")
    profile.write_text(json.dumps(_profile()), encoding="utf-8")
    monkeypatch.setattr(server, "STORE", str(store))
    monkeypatch.setattr(server, "PROFILE_PATH", str(profile))
    monkeypatch.setattr(server, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(server, "RESUME_PATH", str(tmp_path / "resume.pdf"))
    monkeypatch.setattr(server, "NETWORK_STORE", str(tmp_path / "networking.json"))
    monkeypatch.setattr(server, "MONITOR_PATH", str(tmp_path / "nori-monitor.json"))
    monkeypatch.setattr(server, "GMAIL_INBOX_PATH", str(tmp_path / "inbox.json"))
    monkeypatch.setattr(server, "GMAIL_SECRET_DIR", str(tmp_path / "gmail-secrets"))
    monkeypatch.setattr(server, "load_feed", lambda: [])
    return TestClient(server.app)


def test_dashboard_and_application_contracts(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    bootstrap = client.get("/api/dashboard/bootstrap")
    assert bootstrap.status_code == 200
    assert bootstrap.json()["counts"]["total"] == 1
    assert bootstrap.json()["recent"][0]["id"] == "app_test"

    listing = client.get("/api/applications")
    assert listing.status_code == 200
    assert listing.json()["applications"][0]["company"] == "Acme"
    assert listing.json()["applications"][0]["companyDomain"] == "acme.com"
    assert listing.json()["applications"][0]["logoUrl"] == "https://example.test/acme.png"

    detail = client.get("/api/applications/app_test")
    assert detail.status_code == 200
    assert detail.json()["title"] == "Engineer"
    assert detail.json()["submissionEvidence"]["kind"] == "not-submitted"


def test_user_can_record_a_manual_submission_resolution(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resolved = client.post(
        "/api/applications/app_test/resolve", json={"resolution": "applied"})
    assert resolved.status_code == 200
    assert resolved.json()["submitted"] is True

    detail = client.get("/api/applications/app_test").json()
    assert detail["status"] == "applied"
    assert detail["manualSubmissionConfirmed"] is True
    assert detail["submissionEvidence"]["kind"] == "user-confirmed"
    assert detail["submissionEvidence"]["automated"] is False
    assert detail["statusHistory"][-1]["reason"] == "user-confirmed-manual-submission"

    trace = client.get("/api/applications/app_test/trace")
    assert trace.status_code == 200
    assert trace.json()["answers"][0]["fieldId"] == "email"


def test_submission_evidence_never_upgrades_legacy_status_without_proof(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    payload = json.loads(Path(server.STORE).read_text(encoding="utf-8"))
    record = payload["applications"]["app_test"]
    record["status"] = "applied"
    record["submitted"] = True
    Path(server.STORE).write_text(json.dumps(payload), encoding="utf-8")

    legacy = client.get("/api/applications/app_test").json()
    assert legacy["submissionEvidence"]["kind"] == "legacy-unverified"
    assert legacy["submissionEvidence"]["confirmed"] is False

    payload = json.loads(Path(server.STORE).read_text(encoding="utf-8"))
    payload["applications"]["app_test"]["submissionReceipt"] = {
        "confirmed": True,
        "ats": "greenhouse",
        "signals": [{"kind": "selector", "value": ".application-confirmation"}],
    }
    Path(server.STORE).write_text(json.dumps(payload), encoding="utf-8")
    confirmed = client.get("/api/applications/app_test").json()
    assert confirmed["submissionEvidence"]["kind"] == "ats-confirmed"
    assert confirmed["submissionEvidence"]["automated"] is True


def test_application_archive_and_restore_are_reversible(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    archived = client.patch(
        "/api/applications/app_test/archive", json={"archived": True})
    assert archived.status_code == 200
    assert archived.json()["archived"] is True
    assert client.get("/api/applications").json()["applications"] == []
    assert client.get("/api/applications/list/counts").json()["all"] == 0

    archived_list = client.get(
        "/api/applications", params={"filter": "archived"}).json()
    assert archived_list["filtered"] == 1
    assert archived_list["applications"][0]["archived"] is True
    assert client.get("/api/applications/app_test").json()["archived"] is True

    restored = client.patch(
        "/api/applications/app_test/archive", json={"archived": False})
    assert restored.status_code == 200
    assert restored.json()["archived"] is False
    assert client.get("/api/applications").json()["filtered"] == 1


def test_create_profile_feed_and_catalog_contracts(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    created = client.post(
        "/api/applications",
        json={"url": "https://jobs.lever.co/acme/role"},
    )
    assert created.status_code == 200
    assert created.json()["ok"] is True
    assert created.json()["applicationId"]

    duplicate = client.post(
        "/api/applications",
        json={"url": "https://jobs.lever.co/acme/role"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "DUPLICATE_APPLICATION"

    assert client.get("/api/profile").json()["personalInformation"]["firstName"] == "Jane"
    assert client.get("/api/feed/load").json() == {"ok": True, "count": 0, "jobs": []}

    catalog = client.get("/api/atses")
    assert catalog.status_code == 200
    assert any(item["id"] == "greenhouse" for item in catalog.json())


def test_settings_roundtrip(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    settings = client.get("/api/settings")
    assert settings.status_code == 200
    payload = settings.json()
    payload["reviewBeforeSubmit"] = True

    saved = client.put("/api/settings", json={"settings": payload})
    assert saved.status_code == 200
    assert saved.json()["settings"]["reviewBeforeSubmit"] is True
    assert client.get("/api/settings").json()["reviewBeforeSubmit"] is True


def test_automation_readiness_requires_explicit_authorization_review(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\nfixture")
    profile = _profile()
    profile["personalInformation"].update({
        "firstName": "Ada",
        "lastName": "Lovelace",
        "email": "ada@candidate.test",
    })
    profile["resumePath"] = str(resume)
    monkeypatch.setattr(server, "ai_provider_status", lambda: {
        "configured": True,
        "lastError": "",
    })
    saved = client.put("/api/profile", json={"profile": profile})
    assert saved.status_code == 200

    ready = client.get("/api/automation/readiness")
    assert ready.status_code == 200
    payload = ready.json()
    assert payload["readyToPrepare"] is True
    assert payload["readyToMonitor"] is True
    assert payload["readyToSubmitUnattended"] is False
    assert payload["blockers"] == []
    assert any(check["id"] == "telegram" and not check["required"]
               for check in payload["checks"])

    profile["workAuthorization"]["reviewedAt"] = ""
    assert client.put("/api/profile", json={"profile": profile}).status_code == 200
    blocked = client.get("/api/automation/readiness").json()
    assert blocked["readyToPrepare"] is False
    assert "Work authorization reviewed" in blocked["blockers"]


def test_submission_endpoint_requires_authorization_attestation(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    profile = _profile()
    profile["workAuthorization"]["reviewedAt"] = ""
    assert client.put("/api/profile", json={"profile": profile}).status_code == 200
    approvals = []
    monkeypatch.setattr(server, "review_approve", lambda *args, **kwargs: approvals.append(args) or '{}')

    response = client.post("/api/applications/app_test/approve")
    assert response.status_code == 400
    assert response.json()["detail"] == "WORK_AUTHORIZATION_NOT_CONFIRMED"
    assert approvals == []


def test_review_answers_are_editable_and_persisted(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.put(
        "/api/applications/app_test/answers",
        json={"answers": {"email": "reviewed@example.com", "unknown": "ignored"}},
    )
    assert response.status_code == 200
    assert response.json()["saved"] == 1
    trace = client.get("/api/applications/app_test/trace").json()
    assert trace["answers"][0]["value"] == "reviewed@example.com"
    assert trace["answers"][0]["source"] == "user-override"


def test_monitor_settings_mask_telegram_token(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    saved = client.put("/api/monitor", json={"settings": {
        "enabled": True,
        "query": "Cybersecurity Analyst",
        "location": "Chicago, IL",
        "intervalMinutes": 30,
        "telegramBotToken": "secret-token",
        "telegramChatId": "123",
    }})
    assert saved.status_code == 200
    public = client.get("/api/monitor").json()
    assert public["telegramConfigured"] is True
    assert public["telegramBotToken"] == ""


def test_monitor_preview_contract_is_read_only(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    saved = client.put("/api/monitor", json={"settings": {
        "query": "Cybersecurity Analyst",
        "dailyApplicationCap": 5,
        "intervalMinutes": 60,
    }})
    assert saved.status_code == 200
    preview = client.get("/api/monitor/preview?days=7")
    assert preview.status_code == 200
    payload = preview.json()
    assert payload["ok"] is True
    assert payload["days"] == 7
    assert payload["maximumPreparations"] == 35
    assert payload["currentEligibleCandidates"] == 0


def test_preflight_blocks_demo_profile_and_linkedin_guest_url(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    supported = client.get(
        "/api/preflight",
        params={"url": "https://boards.greenhouse.io/example/jobs/42"},
    )
    assert supported.status_code == 200
    assert supported.json()["ats"] == "greenhouse"
    assert supported.json()["capabilityLevel"] == "dry-run-verified"
    assert supported.json()["capabilities"]["unattendedSubmit"] is False
    assert "test-profile-active" in supported.json()["blockers"]
    assert supported.json()["canQueue"] is False

    workday = client.get(
        "/api/preflight",
        params={
            "url": "https://acme.wd1.myworkdayjobs.com/Careers/job/Austin/Role_R12345"
        },
    )
    assert workday.status_code == 200
    assert workday.json()["ats"] == "workday"
    assert workday.json()["capabilityLevel"] == "dry-run-verified"
    assert workday.json()["capabilities"]["receiptEvidence"] is True
    assert "unsupported-ats" not in workday.json()["blockers"]

    successfactors = client.get(
        "/api/preflight",
        params={"url": "https://example.successfactors.com/career?job=42"},
    )
    assert successfactors.status_code == 200
    assert successfactors.json()["ats"] == "successfactors"
    assert successfactors.json()["capabilityLevel"] == "dry-run-verified"
    assert "unsupported-ats" not in successfactors.json()["blockers"]

    linkedin = client.get(
        "/api/preflight",
        params={"url": "https://www.linkedin.com/jobs/view/123"},
    )
    assert linkedin.status_code == 200
    assert linkedin.json()["linkedinOnly"] is True
    assert "linkedin-apply-url-unresolved" in linkedin.json()["blockers"]


def test_preflight_uses_known_ats_only_for_exact_saved_feed_url(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    branded = "https://careers.example.test/jobs/20606"
    monkeypatch.setattr(server, "load_feed", lambda: [{
        "url": branded,
        "title": "Security Analyst",
        "atsType": "icims2",
    }])

    trusted = client.get("/api/preflight", params={"url": branded}).json()
    arbitrary = client.get(
        "/api/preflight", params={"url": branded + "-different"}).json()

    assert trusted["ats"] == "icims"
    assert trusted["rule"] == "exact saved HiringCafe ATS metadata"
    assert "unsupported-ats" not in trusted["blockers"]
    assert arbitrary["ats"] == "unknown"
    assert "unsupported-ats" in arbitrary["blockers"]

    created = client.post("/api/applications", json={
        "url": branded,
        "company_name": "Example",
        "job_title": "Security Analyst",
    })
    assert created.status_code == 200
    assert created.json()["ats"] == "icims"
    detail = client.get(
        f"/api/applications/{created.json()['applicationId']}").json()
    assert detail["atsType"] == "icims"


def test_resume_import_rejects_non_pdf(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post(
        "/api/resume/import",
        files={"file": ("resume.txt", b"not a pdf", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "resume-must-be-pdf"


def test_generated_resume_pdf_download_contract(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    artifact_dir = tmp_path / "applications" / "app_test"
    artifact_dir.mkdir(parents=True)
    pdf = artifact_dir / "tailored-resume.pdf"
    pdf.write_bytes(b"%PDF-1.4\n" + b"x" * 1200)
    store = json.loads((tmp_path / "applications.json").read_text(encoding="utf-8"))
    store["applications"]["app_test"]["documents"] = {
        "resume": {"pdfGenerated": True, "pdfPath": str(pdf),
                   "fileName": "tailored-resume.pdf"}
    }
    (tmp_path / "applications.json").write_text(json.dumps(store), encoding="utf-8")

    response = client.get("/api/applications/app_test/documents/resume")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert client.get("/api/applications/app_test/documents/cover-letter").status_code == 404


def test_source_resume_tracker_and_top_matches_contract(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n" + b"x" * 1200)
    response = client.get("/api/resume")
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")

    moved = client.patch("/api/applications/app_test/tracker", json={"stage": "interviewing"})
    assert moved.status_code == 200
    listing = client.get("/api/applications").json()
    assert listing["applications"][0]["trackerStage"] == "interviewing"

    top = client.get("/api/feed/top")
    assert top.status_code == 200
    assert top.json()["jobs"] == []


def test_application_filter_counts_and_disconnected_inbox(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    listing = client.get("/api/applications", params={"filter": "applied"}).json()
    assert listing["total"] == 1
    assert listing["filtered"] == 0
    assert listing["applications"] == []
    inbox = client.get("/api/inbox")
    assert inbox.status_code == 200
    assert inbox.json()["authorized"] is False
    assert inbox.json()["messages"] == []


def test_application_search_aliases_and_tracker_export(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    searched = client.get("/api/applications", params={"q": "acme"})
    assert searched.status_code == 200
    assert searched.json()["filtered"] == 1
    assert searched.json()["query"] == "acme"

    submitted = client.get("/api/applications", params={"filter": "submitted"})
    assert submitted.status_code == 200
    assert submitted.json()["filtered"] == 0

    exported = client.get("/api/tracker/export")
    assert exported.status_code == 200
    assert "text/csv" in exported.headers["content-type"]
    assert "applicationId,companyName" in exported.text
    assert "app_test,Acme" in exported.text


def test_manual_tracker_entry_never_enters_browser_queue(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    created = client.post("/api/tracker", json={
        "company_name": "Manual Co",
        "job_title": "Security Analyst",
        "url": "https://example.test/role",
        "stage": "interviewing",
    })
    assert created.status_code == 200
    app_id = created.json()["applicationId"]
    listing = client.get("/api/applications", params={"q": "Manual Co"}).json()
    assert listing["applications"][0]["id"] == app_id
    assert listing["applications"][0]["status"] == "paused"
    assert listing["applications"][0]["trackerStage"] == "interviewing"
    assert listing["applications"][0]["ats"] == "manual"
    assert listing["applications"][0]["manualTrackerEntry"] is True

    run_result = client.post(f"/api/applications/{app_id}/run", json={"confirmed": False})
    assert run_result.status_code == 400
    assert run_result.json()["detail"] == "MANUAL_TRACKER_ENTRY_NOT_RUNNABLE"

    approval_result = client.post(f"/api/applications/{app_id}/approve")
    assert approval_result.status_code == 400
    assert approval_result.json()["detail"] == "MANUAL_TRACKER_ENTRY_NOT_RUNNABLE"


def test_networking_contact_contract(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    created = client.post("/api/networking/contacts", json={"contact": {
        "name": "Chicago Recruiter",
        "linkedinUrl": "https://www.linkedin.com/in/chicago-recruiter/",
        "location": "Chicago, Illinois",
        "company": "Example Staffing",
        "about": "Direct client W2 roles; OPT EAD candidates considered.",
    }})
    assert created.status_code == 200
    contact = created.json()["contact"]
    assert contact["signals"]["chicagoRelevant"] is True

    listing = client.get("/api/networking/contacts")
    assert listing.status_code == 200
    assert listing.json()["count"] == 1

    updated = client.patch(
        f"/api/networking/contacts/{contact['id']}",
        json={"updates": {"status": "vetted", "notes": "Confirmed role-specific RTR"}},
    )
    assert updated.status_code == 200
    assert updated.json()["contact"]["status"] == "vetted"

    draft = client.post(f"/api/networking/contacts/{contact['id']}/draft")
    assert draft.status_code == 200
    assert "E-Verify" in draft.json()["draft"]
    assert "Form I-983" in draft.json()["draft"]
