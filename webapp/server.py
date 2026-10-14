"""
Nori AI Webapp — FastAPI backend wrapping the standalone tsenta_* engine.

Serves the React frontend in production and proxies API calls during
development. All endpoints return JSON and catch exceptions internally.

Usage:
    python webapp/server.py                    # dev mode (CORS open, reload)
    python webapp/server.py --prod             # production (serves static)
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import html
import csv
import io
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Tool imports
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "src"))
sys.path.insert(0, str(ROOT / "backend" / "src" / "tools"))

from tsenta_ats import ats_detect, ats_display_name, ats_normalize_hint
from tsenta_capabilities import (
    ats_capability, ats_capabilities, ats_can_prepare, ats_can_unattended_submit,
)
from tsenta_pipeline import (
    create_job, default_store_path, job_report, job_status, jobs_summary,
    list_jobs, review_approve, review_reject, run_job, save_answer_overrides,
    update_tracker_stage, create_tracker_entry, recover_interrupted_jobs,
    resolve_application_manually, set_job_archived,
)
from tsenta_feed import company_identity, fetch_feed, load_feed, save_feed, new_feed_jobs, jobs_to_urls
from tsenta_hiringcafe import rank_hiringcafe_jobs, search_hiringcafe
from nori_monitor import (
    append_monitor_alerts, append_monitor_run, default_monitor_path, load_monitor_settings,
    monitor_preview, save_monitor_settings,
    keep_system_awake, send_telegram_jobs,
    _telegram_commands, _telegram_request, _telegram_status, _job_key,
    match_quality_threshold, lane_match_threshold, roll_daily_application_budget,
)
from tsenta_hiringcafe import job_matches_standing_instructions
from nori_gmail import (
    gmail_begin_authorization, gmail_complete_authorization,
    gmail_connection_status, gmail_disconnect, gmail_load_inbox,
    gmail_sync_messages,
)
from tsenta_profiles import profile_from_json, empty_profile, validate_profile
from tsenta_resume import resume_import, resume_import_to_file
from tsenta_linkedin import (
    linkedin_guest_search, linkedin_guest_detail, linkedin_resolve_apply_url,
)
from tsenta_networking import (
    default_network_store_path, network_delete_contact, network_draft_outreach, network_get_contact,
    network_list_contacts, network_update_contact, network_upsert_contact,
)
from tsenta_config import default_config

STORE = default_store_path()
PROFILE_PATH = os.path.join(os.path.dirname(STORE), "profile.json")
PROFILE_PATH = os.environ.get("TSENTA_PROFILE", PROFILE_PATH)
SETTINGS_PATH = os.path.join(os.path.dirname(STORE), "settings.json")
RESUME_PATH = os.environ.get("TSENTA_RESUME", os.path.join(os.path.dirname(STORE), "resume.pdf"))
NETWORK_STORE = os.environ.get("TSENTA_NETWORK_STORE", default_network_store_path())
MONITOR_PATH = os.environ.get("NORI_MONITOR_PATH", default_monitor_path())
GMAIL_INBOX_PATH = os.environ.get(
    "NORI_GMAIL_INBOX", os.path.join(os.path.dirname(STORE), "inbox.json"))
GMAIL_SECRET_DIR = os.environ.get("NORI_GMAIL_SECRET_DIR") or None


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    recover_interrupted_jobs(STORE)
    if "pytest" not in sys.modules:
        _ensure_monitor_thread()
    yield
    _MONITOR_STOP.set()


app = FastAPI(
    title="Nori AI",
    description="Standalone job-application automation engine",
    version="0.12.0",
    lifespan=_lifespan,
)

# CORS for dev mode
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000",
                   "http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class CreateApplicationRequest(BaseModel):
    url: str
    resume_path: str | None = None
    config: dict | None = None
    company_name: str = ""
    company_domain: str = ""
    logo_url: str = ""
    job_title: str = ""


class RunRequest(BaseModel):
    resume_path: str | None = None
    confirmed: bool = False


class FeedRequest(BaseModel):
    source: str = ""
    query: str = ""
    location: str = ""
    remote_only: bool = False
    limit: int = 100
    preferences: dict | None = None


class AIProviderRequest(BaseModel):
    baseUrl: str = ''
    model: str = ''
    apiKey: str = ''
    transport: str = 'api'


@app.get('/api/ai/provider')
def ai_provider_status():
    """Return provider identity and last error without any credentials."""
    from backend.src.tools import tsenta_llm
    cfg = tsenta_llm.llm_config()
    chatgpt = cfg.get('transport') == 'chatgpt'
    login = {}
    if chatgpt:
        from backend.src.tools.nori_chatgpt import chatgpt_login_status
        login = json.loads(chatgpt_login_status())
    return {'baseUrl': cfg['base_url'], 'model': cfg['model'],
            'transport': cfg.get('transport', 'api'), 'login': login,
            'configured': bool(login.get('signedIn')) if chatgpt else bool(cfg.get('api_key')),
            'lastError': tsenta_llm._LAST_PROVIDER_ERROR}


@app.put('/api/ai/provider')
def update_ai_provider(body: AIProviderRequest):
    """Save a user-selected provider with a Windows-encrypted credential."""
    from backend.src.tools.nori_ai_settings import save_ai_provider
    result = json.loads(save_ai_provider(body.baseUrl, body.model, body.apiKey, body.transport))
    if not result.get('ok'):
        raise HTTPException(400, result.get('error'))
    return ai_provider_status()


@app.post('/api/ai/test')
def test_ai_provider():
    """Make one small connection test with no personal profile data."""
    from backend.src.tools import tsenta_llm
    answer = tsenta_llm.chat_completion([{'role': 'user', 'content': 'Reply with OK.'}],
                                       tsenta_llm.llm_config(max_tokens=1000, timeout=30))
    return {'ok': bool(answer), **ai_provider_status()}


class LinkedInHarvestRequest(BaseModel):
    entries: list[dict] = []


class NetworkingContactRequest(BaseModel):
    contact: dict


class NetworkingContactUpdate(BaseModel):
    updates: dict


class ProfileUpdate(BaseModel):
    profile: dict


class SettingsUpdate(BaseModel):
    settings: dict


class AnswerOverridesRequest(BaseModel):
    answers: dict


class MonitorSettingsUpdate(BaseModel):
    settings: dict


class TrackerStageUpdate(BaseModel):
    stage: str


class ManualResolutionRequest(BaseModel):
    resolution: str


class ArchiveApplicationRequest(BaseModel):
    archived: bool = True


class TrackerEntryRequest(BaseModel):
    company_name: str = ""
    job_title: str = ""
    url: str = ""
    stage: str = "applied"


class GmailConnectRequest(BaseModel):
    client_id: str
    redirect_uri: str
    client_secret: str = ""


class GmailSyncRequest(BaseModel):
    max_messages: int = 50


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_profile() -> dict:
    try:
        with open(PROFILE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return empty_profile()


def _save_profile(profile: dict) -> None:
    os.makedirs(os.path.dirname(PROFILE_PATH), exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as fh:
        json.dump(profile, fh, indent=2, default=str)


def _is_test_profile(profile: dict) -> bool:
    personal = profile.get("personalInformation", {}) if isinstance(profile, dict) else {}
    email = str(personal.get("email") or "").lower()
    return email.endswith("@example.com") or (
        str(personal.get("firstName") or "").lower() == "jane"
        and str(personal.get("lastName") or "").lower() == "doe"
    )


def _work_authorization_attested(profile: dict) -> bool:
    """Return whether the candidate explicitly reviewed eligibility answers."""
    try:
        auth = profile.get("workAuthorization", {})
        return (
            isinstance(auth.get("isAuthorizedToWork"), bool)
            and isinstance(auth.get("needsSponsorship"), bool)
            and bool(str(auth.get("reviewedAt") or "").strip())
        )
    except Exception:
        return False


def _load_settings() -> dict:
    settings = default_config()
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
        if isinstance(saved, dict):
            settings.update(saved)
    except Exception:
        pass
    return settings


def _save_settings(settings: dict) -> None:
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2, default=str)


def _merge_meaningful(current: dict, extracted: dict) -> dict:
    merged = dict(current or {})
    for key, value in (extracted or {}).items():
        if value not in (None, "", [], {}):
            merged[key] = value
    return merged


def _pipeline_summary() -> dict:
    result = json.loads(jobs_summary(STORE))
    return result.get("counts", {}) if result.get("ok") else {}


def _job_to_dict(job: dict) -> dict:
    normalized = dict(job)
    receipt = job.get("submissionReceipt") or {}
    submitted = bool(job.get("submitted"))
    if bool(receipt.get("confirmed")):
        evidence = {
            "kind": "ats-confirmed",
            "confirmed": True,
            "automated": True,
            "label": "ATS receipt confirmed",
            "detail": "Nori captured employer-site confirmation evidence after submission.",
        }
    elif submitted and (job.get("manualSubmissionConfirmed") or
                        job.get("manualTrackerEntry")):
        evidence = {
            "kind": "user-confirmed",
            "confirmed": True,
            "automated": False,
            "label": "Manually confirmed",
            "detail": "You recorded this as submitted outside Nori; no automated ATS receipt is claimed.",
        }
    elif submitted or job.get("status") == "applied":
        evidence = {
            "kind": "legacy-unverified",
            "confirmed": False,
            "automated": False,
            "label": "Legacy status — unverified",
            "detail": "This older record says applied, but Nori has no ATS receipt or manual confirmation for it.",
        }
    else:
        evidence = {
            "kind": "not-submitted",
            "confirmed": False,
            "automated": False,
            "label": "Not submitted",
            "detail": "No submission is recorded.",
        }
    identity = company_identity(job.get("company") or job.get("companyName") or "",
                                url=job.get("url") or "")
    normalized.update({
        "id": job.get("id") or job.get("applicationId"),
        "url": job.get("url"),
        "title": job.get("title") or job.get("jobTitle") or "",
        "company": identity["companyName"],
        "companyDomain": job.get("companyDomain") or identity["companyDomain"],
        "logoUrl": job.get("logoUrl") or identity["logoUrl"],
        "status": job.get("status", "queued"),
        "ats": job.get("ats") or job.get("atsType") or "",
        "submitted": submitted,
        "submissionEvidence": evidence,
        "createdAt": job.get("createdAt", ""),
        "updatedAt": job.get("updatedAt", ""),
        "error": job.get("error"),
        "trace": job.get("trace", {}),
    })
    return normalized


def _tracked_urls() -> set[str]:
    result = json.loads(list_jobs(STORE))
    if not result.get("ok"):
        return set()
    return {str(item.get("url") or "").rstrip("/") for item in result.get("applications", [])}


def _feed_job_for_url(url: str) -> dict:
    """Return the exact saved feed row for a URL, or an empty dictionary."""
    try:
        target = str(url or "").rstrip("/")
        return next((job for job in load_feed()
                     if str(job.get("url") or "").rstrip("/") == target), {})
    except Exception:
        return {}


def _detection_with_feed_hint(url: str) -> tuple[dict, dict]:
    """Detect a URL, falling back only to its exact saved HiringCafe row."""
    detection = ats_detect(url)
    feed_job = _feed_job_for_url(url)
    if detection.get("ats_id") == "unknown" and feed_job:
        hint = ats_normalize_hint(feed_job.get("atsType") or "")
        if hint != "unknown":
            detection = {
                "ats_id": hint,
                "confidence": 0.75,
                "rule": "exact saved HiringCafe ATS metadata",
            }
    return detection, feed_job


def _feed_request(body: FeedRequest) -> dict:
    query = str(body.query or "").strip()
    if not query and str(body.source or "").startswith("hiringcafe:"):
        query = str(body.source).split(":", 1)[1].strip()
    if query:
        return search_hiringcafe(query, _load_profile(), limit=body.limit,
                                 location=body.location,
                                 remote_only=body.remote_only,
                                 preferences=body.preferences or load_monitor_settings(MONITOR_PATH))
    jobs = fetch_feed(body.source, limit=body.limit)
    jobs = rank_hiringcafe_jobs(jobs, _load_profile(), "", body.location,
                                body.remote_only)
    return {"ok": True, "count": len(jobs), "jobs": jobs, "error": ""}


_MONITOR_LOCK = threading.Lock()
_MONITOR_THREAD: threading.Thread | None = None
_MONITOR_STOP = threading.Event()


def _application_ready(report: dict) -> bool:
    """Require real answers and successful fills/documents before unattended submit."""
    summary = report.get('answersSummary') or {}
    answers = (report.get('trace') or {}).get('answers') or []
    documents = report.get('documents') or {}
    return bool(not report.get('error')
        and any(a.get('source') not in ('skip', 'fallback') for a in answers)
        and not summary.get('submission_blockers')
        and not summary.get('field_failures') and not summary.get('missing_uploads')
        and all(a.get('source') not in ('fallback', 'skip') for a in answers
                if a.get('required') and 'conditional-hidden' not in str(a.get('reason') or ''))
        and all(not d.get('qualityIssues') for d in documents.values() if isinstance(d, dict)))


def _run_telegram_commands(settings: dict) -> None:
    """Process private-chat job buttons serially with the overnight application worker."""
    if not _MONITOR_LOCK.acquire(blocking=False):
        return
    try:
        polled = _telegram_commands(settings)
        if polled.get('error'):
            save_monitor_settings({'lastError': polled['error']}, MONITOR_PATH)
            return
        for command in polled['commands']:
            # Persist receipt before acting. Repeated clicks also meet pipeline status guards.
            if not json.loads(save_monitor_settings({'telegramUpdateOffset': command['_nextOffset']}, MONITOR_PATH)).get('ok'):
                return
            _telegram_request(settings['telegramBotToken'], 'answerCallbackQuery',
                {'callback_query_id': command['id'], 'text': 'Nori is checking this application.'})
            parts = str(command.get('data') or '').split(':', 2)
            if len(parts) != 3:
                continue
            profile = _load_profile()
            if not validate_profile(profile).get('valid') or _is_test_profile(profile):
                _telegram_status(settings, 'Complete your real profile in Nori before preparing applications.')
                continue
            if not _work_authorization_attested(profile):
                _telegram_status(settings, 'Review and confirm your work-authorization answers in Nori first.')
                continue
            operation, key = parts[1:]
            if operation == 'prepare':
                candidate = next((job for job in load_feed() if _job_key(job.get('url', '')) == key), None)
                if not candidate:
                    _telegram_status(settings, 'This alert has expired. Refresh the HiringCafe search in Nori.')
                    continue
                tracked = json.loads(list_jobs(STORE)).get('applications') or []
                existing = next((job for job in tracked if _job_key(job.get('url', '')) == key), None)
                if existing:
                    app_id = existing['applicationId']
                    if existing.get('status') != 'review':
                        _telegram_status(settings, f'This job is already tracked ({existing.get("status")}). Open Nori for details.')
                        continue
                else:
                    config = {**_load_settings(), 'autoSubmitApplication': False, 'reviewBeforeSubmit': True,
                              'source': 'nori-telegram', 'jobDescription': candidate.get('description', ''),
                              'jobLocation': candidate.get('location', '')}
                    created = json.loads(create_job(candidate['url'], profile, config,
                        company_name=candidate.get('companyName', ''), job_title=candidate.get('title', ''), store_path=STORE))
                    if not created.get('ok'):
                        _telegram_status(settings, 'Could not prepare this job: ' + str(created.get('error')))
                        continue
                    app_id = created['applicationId']
                    _telegram_status(settings, f'Preparing {candidate.get("title", "application")} at {candidate.get("companyName", "employer")}.')
                    run_job(app_id, profile, resume_path=profile.get('resumePath') or RESUME_PATH, store_path=STORE)
                report = json.loads(job_report(app_id, STORE))
                ready = report.get('status') == 'review' and _application_ready(report)
                message = (f'{report.get("jobTitle", "Application")} at {report.get("companyName", "employer")}: '
                           + ('draft checks passed. Tap Submit to authorize this application, or edit answers/documents in Nori first.'
                              if ready else 'needs your review in Nori. ' + str(report.get('error') or 'Unresolved answers, uploads, or document checks.')))
                _telegram_status(settings, message, app_id if ready else '')
            elif operation == 'apply':
                report = json.loads(job_report(key, STORE))
                if report.get('status') != 'review' or not _application_ready(report):
                    _telegram_status(settings, 'This application is not ready or has already been processed. Open it in Nori.')
                    continue
                outcome = json.loads(review_approve(key, profile,
                    resume_path=profile.get('resumePath') or RESUME_PATH, store_path=STORE))
                _telegram_status(settings, f'{report.get("jobTitle", "Application")}: ' + (
                    'submission confirmed.' if outcome.get('submitted') else
                    'not confirmed. Review in Nori: ' + str(outcome.get('error') or outcome.get('status'))))
        save_monitor_settings({'telegramUpdateOffset': polled['offset']}, MONITOR_PATH)
    except Exception as exc:
        save_monitor_settings({'lastError': str(exc).replace(settings.get('telegramBotToken', ''), '[redacted]')}, MONITOR_PATH)
    finally:
        _MONITOR_LOCK.release()


def _run_monitor_cycle() -> dict:
    if not _MONITOR_LOCK.acquire(blocking=False):
        return {"ok": False, "error": "monitor-run-already-in-progress"}
    cycle_started = datetime.now(timezone.utc)
    try:
        settings = load_monitor_settings(MONITOR_PATH, include_secrets=True)
        roll_daily_application_budget(settings)
        if not settings.get("query") and not settings.get("lanes"):
            blocked = {"ok": False, "error": "monitor-query-required"}
            append_monitor_run(settings, blocked, cycle_started, status="blocked")
            save_monitor_settings(settings, MONITOR_PATH)
            return blocked
        lanes = [lane for lane in (settings.get('lanes') or [])
                 if isinstance(lane, dict) and lane.get('enabled', True)
                 and str(lane.get('query') or settings.get('query') or '').strip()]
        if not lanes:
            lanes = [{
                'id': 'primary', 'name': 'Primary', 'query': settings.get('query', ''),
                'location': settings.get('location', ''),
                'remoteOnly': settings.get('remoteOnly', False),
                'minScore': settings.get('minScore', 0),
                'minMatchQuality': settings.get('minMatchQuality', 'stretch'),
            }]
        profile = _load_profile()
        merged_by_url = {}
        lane_thresholds = {}
        lane_errors = []
        successful_lanes = 0
        for lane in lanes:
            lane_result = search_hiringcafe(
                str(lane.get('query') or settings.get('query') or ''), profile,
                limit=settings.get('limit', 50),
                location=str(lane.get('location') or settings.get('location') or ''),
                remote_only=bool(lane.get('remoteOnly', settings.get('remoteOnly'))),
                page_limit=2, preferences={**settings, **lane},
            )
            if not lane_result.get('ok'):
                lane_errors.append(str(lane_result.get('error') or 'hiringcafe-search-failed'))
                continue
            successful_lanes += 1
            threshold = lane_match_threshold(lane, settings.get('minScore', 0))
            for item in lane_result.get('jobs') or []:
                url_key = str(item.get('url') or '').rstrip('/')
                if not url_key:
                    continue
                merged_by_url[url_key] = item
                lane_thresholds[url_key] = min(threshold, lane_thresholds.get(url_key, threshold))
        result = {
            'ok': successful_lanes > 0,
            'jobs': list(merged_by_url.values()),
            'error': '; '.join(dict.fromkeys(lane_errors)),
        }
        now = datetime.now(timezone.utc)
        settings["lastRunAt"] = now.isoformat()
        settings["nextRunAt"] = (now + timedelta(
            minutes=int(settings.get("intervalMinutes") or 30)
        )).isoformat()
        if not result.get("ok"):
            settings["lastError"] = result.get("error") or "hiringcafe-search-failed"
            failed = {"ok": False, "count": 0, "newCount": 0,
                      "notified": 0, "prepared": 0, "applied": 0,
                      "needsReview": 0, "error": settings["lastError"]}
            append_monitor_run(settings, failed, cycle_started, status="failed")
            save_monitor_settings(settings, MONITOR_PATH)
            return failed

        fresh_jobs = result.get("jobs") or []
        existing = load_feed()
        merged = {}
        for item in list(existing) + list(fresh_jobs):
            if isinstance(item, dict) and item.get("url"):
                merged[str(item["url"]).rstrip("/")] = item
        merged_jobs = sorted(merged.values(),
                             key=lambda item: (item.get("matchScore", 0),
                                               item.get("updated_at", "")),
                             reverse=True)[:500]
        save_feed(merged_jobs)

        seen = {str(url).rstrip("/") for url in settings.get("seenUrls", [])}
        threshold = max(int(settings.get("minScore") or 0),
                        match_quality_threshold(settings.get("minMatchQuality")))
        new_jobs = [item for item in fresh_jobs
                    if str(item.get("url") or "").rstrip("/") not in seen
                    and int(item.get("matchScore") or 0) >= lane_thresholds.get(
                        str(item.get("url") or "").rstrip("/"), threshold)]
        notify = {"ok": True, "sent": 0, "error": ""}
        if new_jobs and settings.get("telegramBotToken") and settings.get("telegramChatId"):
            notify = json.loads(send_telegram_jobs(
                settings["telegramBotToken"], settings["telegramChatId"], new_jobs,
            ))
        telegram_configured = bool(
            settings.get("telegramBotToken") and settings.get("telegramChatId"))
        sent_urls = {
            str(url or "").rstrip("/") for url in notify.get("sentUrls", [])
        }
        append_monitor_alerts(settings, new_jobs, now, sent_urls)
        seen_additions = (
            list(sent_urls)
            if telegram_configured else
            [str(job.get('url') or '').rstrip('/') for job in new_jobs]
        )
        settings["seenUrls"] = [url for url in dict.fromkeys(
            seen_additions + list(settings.get("seenUrls", []))
        ) if url][:3000]
        settings["lastFoundCount"] = len(fresh_jobs)
        settings["lastNewCount"] = len(new_jobs)
        settings['lastPreparedCount'] = 0
        settings['lastAppliedCount'] = 0
        settings['lastNeedsReviewCount'] = 0
        mode = settings.get('applicationMode', 'notify')
        if mode in ('prepare', 'apply'):
            profile = _load_profile()
            if not validate_profile(profile).get('valid') or _is_test_profile(profile):
                settings['lastError'] = 'Complete your real profile before enabling application preparation.'
                blocked = {"ok": False, "count": len(fresh_jobs),
                           "newCount": len(new_jobs), "notified": int(notify.get("sent") or 0),
                           "prepared": 0, "applied": 0, "needsReview": 0,
                           "error": settings['lastError']}
                append_monitor_run(settings, blocked, cycle_started, status="blocked")
                save_monitor_settings(settings, MONITOR_PATH)
                return blocked
            if not _work_authorization_attested(profile):
                settings['lastError'] = 'Review and confirm your work-authorization answers before application preparation.'
                blocked = {"ok": False, "count": len(fresh_jobs),
                           "newCount": len(new_jobs), "notified": int(notify.get("sent") or 0),
                           "prepared": 0, "applied": 0, "needsReview": 0,
                           "error": settings['lastError']}
                append_monitor_run(settings, blocked, cycle_started, status="blocked")
                save_monitor_settings(settings, MONITOR_PATH)
                return blocked
            tracked = _tracked_urls()
            candidates = [job for job in fresh_jobs
                          if int(job.get('matchScore') or 0) >= lane_thresholds.get(
                              str(job.get('url') or '').rstrip('/'), threshold)
                          and job_matches_standing_instructions(
                              job, settings.get('standingInstructions', ''))
                          and str(job.get('url') or '').rstrip('/') not in tracked
                          and ats_can_prepare(ats_detect(job.get('url', '')).get('ats_id'))]
            daily_remaining = int(settings.get('dailyApplicationsRemaining') or 0)
            cycle_limit = min(int(settings.get('maxApplicationsPerCycle') or 3), daily_remaining)
            for candidate in candidates[:cycle_limit]:
                config = {**_load_settings(), 'autoSubmitApplication': False,
                          'reviewBeforeSubmit': True, 'source': 'nori-monitor',
                          'jobDescription': candidate.get('description', ''),
                          'jobLocation': candidate.get('location', '')}
                created = json.loads(create_job(candidate['url'], profile, config,
                    company_name=candidate.get('companyName', ''),
                    job_title=candidate.get('title', ''), store_path=STORE))
                if not created.get('ok'):
                    continue
                app_id = created['applicationId']
                settings['dailyApplicationsUsed'] = int(settings.get('dailyApplicationsUsed') or 0) + 1
                settings['dailyApplicationsRemaining'] = max(
                    0, int(settings.get('dailyApplicationCap') or 10)
                    - settings['dailyApplicationsUsed'])
                prepared = json.loads(run_job(app_id, profile,
                    resume_path=profile.get('resumePath') or RESUME_PATH, store_path=STORE))
                report = json.loads(job_report(app_id, STORE))
                settings['lastPreparedCount'] += 1
                ready = prepared.get('ok') and not prepared.get('error') and _application_ready(report)
                candidate_ats = ats_detect(candidate.get('url', '')).get('ats_id', 'unknown')
                unattended_ok = ats_can_unattended_submit(candidate_ats)
                if (mode == 'apply' and ready and unattended_ok
                        and load_monitor_settings(MONITOR_PATH).get('applicationMode') == 'apply'):
                    outcome = json.loads(review_approve(app_id, profile,
                        resume_path=profile.get('resumePath') or RESUME_PATH, store_path=STORE))
                    settings['lastAppliedCount'] += int(bool(outcome.get('submitted')))
                    settings['lastNeedsReviewCount'] += int(not outcome.get('submitted'))
                    if settings.get('telegramBotToken') and settings.get('telegramChatId'):
                        _telegram_status(settings, f'{candidate.get("title", "Application")}: ' + (
                            'submission confirmed.' if outcome.get('submitted') else 'submission not confirmed; review in Nori.'))
                else:
                    settings['lastNeedsReviewCount'] += 1
                    if settings.get('telegramBotToken') and settings.get('telegramChatId'):
                        _telegram_status(settings, f'{candidate.get("title", "Application")}: ' + (
                            ('draft checks passed. Submit now or review in Nori.' if mode != 'apply' else
                             'draft checks passed, but unattended submit is not certified for this ATS. Review in Nori.') if ready else
                            'needs review in Nori: ' + str(report.get('error') or 'Answer or document checks.')),
                            app_id if ready else '')
        settings["notificationsSent"] = int(settings.get("notificationsSent") or 0) + int(
            notify.get("sent") or 0
        )
        settings["lastError"] = (
            notify.get("error") if not notify.get("ok") else result.get("error", "")
        )
        cycle_result = {"ok": True, "count": len(fresh_jobs),
                        "newCount": len(new_jobs),
                        "notified": int(notify.get("sent") or 0),
                        "jobs": fresh_jobs,
                        'prepared': settings['lastPreparedCount'],
                        'applied': settings['lastAppliedCount'],
                        'needsReview': settings['lastNeedsReviewCount'],
                        'dailyApplicationsRemaining': settings.get(
                            'dailyApplicationsRemaining', 0),
                        "error": settings["lastError"]}
        append_monitor_run(settings, cycle_result, cycle_started)
        runtime = {key: value for key, value in settings.items()
                   if key.startswith('last') or key in (
                       'nextRunAt', 'seenUrls', 'notificationsSent',
                       'dailyApplicationCap', 'dailyApplicationsUsed',
                       'dailyUsageDate', 'dailyApplicationsRemaining', 'lanes',
                       'runHistory', 'recentAlerts')}
        save_monitor_settings(runtime, MONITOR_PATH)
        return cycle_result
    except Exception as exc:
        failed = {"ok": False, "count": 0, "newCount": 0,
                  "notified": 0, "prepared": 0, "applied": 0,
                  "needsReview": 0,
                  "error": str(exc) or "monitor-run-failed"}
        try:
            settings = load_monitor_settings(MONITOR_PATH, include_secrets=True)
            settings["lastError"] = failed["error"]
            append_monitor_run(settings, failed, cycle_started, status="failed")
            save_monitor_settings(settings, MONITOR_PATH)
        except Exception:
            pass
        return failed
    finally:
        _MONITOR_LOCK.release()


def _monitor_loop() -> None:
    awake = False
    try:
        while not _MONITOR_STOP.wait(15):
            settings = load_monitor_settings(MONITOR_PATH, include_secrets=True)
            if settings.get('telegramBotToken') and settings.get('telegramChatId'):
                _run_telegram_commands(settings)
            enabled = bool(settings.get("enabled"))
            if enabled != awake:
                keep_system_awake(enabled)
                awake = enabled
            if not enabled:
                continue
            next_value = str(settings.get("nextRunAt") or "")
            due = True
            if next_value:
                try:
                    due = datetime.fromisoformat(next_value) <= datetime.now(timezone.utc)
                except Exception:
                    due = True
            if due:
                _run_monitor_cycle()
    except Exception:
        pass
    finally:
        if awake:
            keep_system_awake(False)


def _ensure_monitor_thread() -> None:
    global _MONITOR_THREAD
    if _MONITOR_THREAD and _MONITOR_THREAD.is_alive():
        return
    _MONITOR_STOP.clear()
    _MONITOR_THREAD = threading.Thread(target=_monitor_loop, name="nori-monitor", daemon=True)
    _MONITOR_THREAD.start()


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.get("/api/dashboard/bootstrap")
def dashboard_bootstrap():
    """Aggregate dashboard data: profile, counts, recent jobs."""
    try:
        profile = _load_profile()
        readiness = validate_profile(profile)
        summary = _pipeline_summary()
        data = json.loads(list_jobs(STORE))
        apps = data.get("applications", []) if data.get("ok") else []
        recent = apps[-10:] if len(apps) > 10 else apps
        return {
            "profile": {
                "firstName": profile.get("personalInformation", {}).get("firstName", ""),
                "lastName": profile.get("personalInformation", {}).get("lastName", ""),
                "email": profile.get("personalInformation", {}).get("email", ""),
                "hasResume": bool(profile.get("resumeFormat")),
                "ready": bool(readiness.get("valid")),
                "testProfile": _is_test_profile(profile),
                "missingFields": readiness.get("missing", []),
            },
            "counts": {
                "total": summary.get("all", 0),
                "queued": summary.get("queued", 0),
                "review": summary.get("review", 0),
                "running": summary.get("running", 0),
                "applied": summary.get("applied", 0),
                "failed": summary.get("failed", 0),
                "paused": summary.get("paused", 0),
            },
            "recent": [_job_to_dict(j) for j in recent],
        }
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/preflight")
def application_preflight(url: str):
    """Validate and explain a job URL before creating an application."""
    try:
        from urllib.parse import urlsplit

        value = str(url or "").strip()
        parts = urlsplit(value)
        valid_url = parts.scheme in ("http", "https") and bool(parts.hostname)
        detection, _feed_job = _detection_with_feed_hint(value) if valid_url else ({
            "ats_id": "unknown", "confidence": 0.0, "rule": "invalid-url"
        }, {})
        profile_check = validate_profile(_load_profile())
        test_profile = _is_test_profile(_load_profile())
        ats_id = detection.get("ats_id", "unknown")
        linkedin_only = bool(parts.hostname and parts.hostname.lower().endswith("linkedin.com"))
        duplicate = value.rstrip("/") in _tracked_urls() if valid_url else False
        capability = ats_capability(ats_id)
        supported = bool(capability.get("prepare")) and not linkedin_only
        blockers = []
        if not valid_url:
            blockers.append("invalid-url")
        if linkedin_only:
            blockers.append("linkedin-apply-url-unresolved")
        elif valid_url and not supported:
            blockers.append("unsupported-ats")
        if duplicate:
            blockers.append("duplicate-application")
        if not profile_check.get("valid"):
            blockers.append("profile-incomplete")
        if test_profile:
            blockers.append("test-profile-active")
        return {
            "ok": True,
            "url": value,
            "validUrl": valid_url,
            "ats": ats_id,
            "atsName": ats_display_name(ats_id),
            "confidence": detection.get("confidence", 0.0),
            "rule": detection.get("rule", ""),
            "supported": supported,
            "capabilityLevel": capability.get("level", "detect-only"),
            "capabilities": capability,
            "warnings": capability.get("warnings", []),
            "duplicate": duplicate,
            "linkedinOnly": linkedin_only,
            "profileReady": bool(profile_check.get("valid")),
            "testProfile": test_profile,
            "missingFields": profile_check.get("missing", []),
            "settings": _load_settings(),
            "mode": "prepare-and-review",
            "canQueue": not blockers,
            "blockers": blockers,
        }
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
@app.get("/api/applications")
def list_applications(filter: str = "all", limit: int = 100, page: int = 1,
                      q: str = ""):
    """List applications with status and full-text filters.

    ``q`` intentionally searches the local record only (title, company, ATS,
    URL, and tracker stage), so the Applications page can behave like Tsenta's
    tracker search without sending profile data anywhere.
    """
    try:
        show_archived = str(filter or "").strip().lower() == "archived"
        data = json.loads(list_jobs(STORE, include_archived=show_archived))
        apps = data.get("applications", []) if data.get("ok") else []
        if show_archived:
            apps = [job for job in apps if job.get("archived")]
        total = len(apps)
        query = str(q or "").strip().lower()
        if query:
            def matches(job: dict) -> bool:
                haystack = " ".join(str(job.get(key) or "") for key in (
                    "jobTitle", "title", "companyName", "company", "atsType",
                    "ats", "url", "trackerStage", "status"))
                return query in haystack.lower()
            apps = [job for job in apps if matches(job)]
        if filter and filter not in ("all", "archived"):
            aliases = {
                "submitted": {"applied"},
                "in-flight": {"running", "queued"},
                "needs": {"review"},
                "needs-you": {"review"},
                "skipped": {"paused"},
            }
            accepted = aliases.get(filter, {filter})
            apps = [j for j in apps if j.get("status") in accepted]
        filtered = len(apps)
        start = (page - 1) * limit
        page_jobs = apps[start:start + limit]
        return {
            "total": total,
            "filtered": filtered,
            "page": page,
            "limit": limit,
            "query": q or "",
            "applications": [_job_to_dict(j) for j in page_jobs],
        }
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/applications/list/counts")
def application_counts():
    """Pipeline counts: queued, review, running, applied, failed, paused."""
    try:
        return _pipeline_summary()
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/applications/{app_id}")
def application_detail(app_id: str):
    """Full application detail including trace."""
    try:
        report = json.loads(job_report(app_id, STORE))
        if report.get("ok") is False:
            raise HTTPException(404, report.get("error", "not-found"))
        return _job_to_dict(report)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/applications/{app_id}/trace")
def application_trace(app_id: str):
    """Per-question execution trace."""
    try:
        report = json.loads(job_report(app_id, STORE))
        if report.get("ok") is False:
            raise HTTPException(404, report.get("error", "not-found"))
        return report.get("trace", {})
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.put("/api/applications/{app_id}/answers")
def update_application_answers(app_id: str, body: AnswerOverridesRequest):
    """Save reviewed answer overrides before the final application run."""
    try:
        result = json.loads(save_answer_overrides(app_id, body.answers, STORE))
        if not result.get("ok"):
            status = 404 if result.get("error") == "job-not-found" else 409
            raise HTTPException(status, result.get("error") or "answer-save-failed")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/applications/{app_id}/documents/{kind}")
def application_document(app_id: str, kind: str):
    """Download a verified generated resume or cover-letter PDF artifact."""
    try:
        key = {"resume": "resume", "cover-letter": "coverLetter",
               "cover_letter": "coverLetter"}.get(kind)
        if not key:
            raise HTTPException(404, "document-kind-not-found")
        report = json.loads(job_report(app_id, STORE))
        if report.get("ok") is False:
            raise HTTPException(404, report.get("error", "not-found"))
        document = (report.get("documents") or {}).get(key) or {}
        path_value = document.get("pdfPath") or ""
        if not document.get("pdfGenerated") or not path_value:
            raise HTTPException(404, "document-not-generated")
        path = Path(path_value).resolve()
        allowed = (Path(STORE).resolve().parent / "applications").resolve()
        if not path.is_relative_to(allowed) or path.suffix.lower() != ".pdf" or not path.is_file():
            raise HTTPException(404, "document-file-missing")
        return FileResponse(path, media_type="application/pdf",
                            filename=document.get("fileName") or path.name,
                            content_disposition_type="inline")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/applications")
def create_application(body: CreateApplicationRequest):
    """Create a new application from a URL."""
    try:
        profile = _load_profile()
        if body.url.rstrip("/") in _tracked_urls():
            raise HTTPException(409, "DUPLICATE_APPLICATION")
        detection, feed_job = _detection_with_feed_hint(body.url)
        capability = ats_capability(detection.get("ats_id", "unknown"))
        if not capability.get("prepare"):
            raise HTTPException(400, "ATS_DETECTED_BUT_NOT_EXECUTABLE")
        config = dict(body.config or _load_settings())
        config['atsHint'] = detection.get('ats_id', 'unknown')
        config.setdefault('jobDescription', feed_job.get('description', ''))
        config.setdefault('jobLocation', feed_job.get('location', ''))
        result = json.loads(
            create_job(body.url, profile, config,
                       company_name=body.company_name,
                       company_domain=body.company_domain,
                       logo_url=body.logo_url,
                       job_title=body.job_title,
                       store_path=STORE)
        )
        if not result.get('ok'):
            raise HTTPException(400, result.get('error') or 'Could not create application')
        stats = _pipeline_summary()
        return {
            "ok": result.get("ok", False),
            "applicationId": result.get("applicationId"),
            "jobId": result.get("applicationId"),
            "url": body.url,
            "status": result.get("status", "queued"),
            "ats": detection.get("ats_id", "unknown"),
            "atsHint": detection.get("ats_id", "unknown"),
            "counts": stats,
            "error": result.get("error"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/applications/{app_id}/run")
def run_application(app_id: str, body: RunRequest | None = None):
    """Run an application through the walker."""
    try:
        body = body or RunRequest()
        if body.confirmed:
            raise HTTPException(400, "USE_REVIEW_APPROVE_ENDPOINT")
        report = json.loads(job_report(app_id, STORE))
        if report.get("ok") is False:
            raise HTTPException(404, report.get("error") or "not-found")
        if report.get("manualTrackerEntry"):
            raise HTTPException(400, "MANUAL_TRACKER_ENTRY_NOT_RUNNABLE")
        profile = _load_profile()
        result = json.loads(
            run_job(app_id, profile, confirmed=False,
                    resume_path=body.resume_path or profile.get("resumePath") or RESUME_PATH,
                    store_path=STORE)
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/applications/{app_id}/approve")
def approve_application(app_id: str, body: RunRequest | None = None):
    """Approve and submit a reviewed application."""
    try:
        body = body or RunRequest()
        report = json.loads(job_report(app_id, STORE))
        if report.get("ok") is False:
            raise HTTPException(404, report.get("error") or "not-found")
        if report.get("manualTrackerEntry"):
            raise HTTPException(400, "MANUAL_TRACKER_ENTRY_NOT_RUNNABLE")
        profile = _load_profile()
        if not _work_authorization_attested(profile):
            raise HTTPException(400, "WORK_AUTHORIZATION_NOT_CONFIRMED")
        result = json.loads(
            review_approve(app_id, profile,
                           resume_path=body.resume_path or profile.get("resumePath") or RESUME_PATH,
                           store_path=STORE)
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/applications/{app_id}/reject")
def reject_application(app_id: str):
    """Reject/pause a reviewed application."""
    try:
        result = json.loads(review_reject(app_id, STORE))
        return result
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/applications/{app_id}/resolve")
def resolve_application(app_id: str, body: ManualResolutionRequest):
    """Record that a user submitted externally or chose to skip the role."""
    try:
        result = json.loads(resolve_application_manually(
            app_id, body.resolution, STORE))
        if not result.get("ok"):
            status = 404 if result.get("error") == "job-not-found" else 400
            raise HTTPException(status, result.get("error") or "manual-resolution-failed")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.patch("/api/applications/{app_id}/archive")
def archive_application(app_id: str, body: ArchiveApplicationRequest):
    """Soft-archive or restore an application while preserving its evidence."""
    try:
        result = json.loads(set_job_archived(app_id, body.archived, STORE))
        if not result.get("ok"):
            status = 404 if result.get("error") == "job-not-found" else 400
            raise HTTPException(status, result.get("error") or "archive-update-failed")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.patch("/api/applications/{app_id}/tracker")
def set_application_tracker_stage(app_id: str, body: TrackerStageUpdate):
    """Move an application in the local tracker without submitting it."""
    try:
        result = json.loads(update_tracker_stage(app_id, body.stage, STORE))
        if not result.get("ok"):
            status = 404 if result.get("error") == "job-not-found" else 400
            raise HTTPException(status, result.get("error") or "tracker-update-failed")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/tracker")
def add_tracker_entry(body: TrackerEntryRequest):
    """Add a manual/external application to the local tracker only."""
    try:
        result = json.loads(create_tracker_entry(
            body.company_name, body.job_title, body.url, body.stage, STORE))
        if not result.get("ok"):
            raise HTTPException(400, result.get("error") or "tracker-entry-failed")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/tracker/export")
def export_tracker():
    """Export the local application tracker as a portable CSV file."""
    try:
        data = json.loads(list_jobs(STORE))
        rows = data.get("applications", []) if data.get("ok") else []
        output = io.StringIO(newline="")
        fields = ["applicationId", "companyName", "jobTitle", "url", "atsType",
                  "status", "trackerStage", "submitted", "createdAt", "updatedAt",
                  "error"]
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
        body = output.getvalue().encode("utf-8-sig")
        return StreamingResponse(io.BytesIO(body), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=nori-tracker.csv"})
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
@app.get("/api/profile")
def get_profile():
    """Get the current candidate profile."""
    try:
        return _load_profile()
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.put("/api/profile")
def update_profile(body: ProfileUpdate):
    """Update the candidate profile."""
    try:
        _save_profile(body.profile)
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/settings")
def get_settings():
    """Return local apply preferences matching Tsenta's settings contract."""
    return _load_settings()


@app.put("/api/settings")
def update_settings(body: SettingsUpdate):
    """Persist local apply preferences."""
    try:
        settings = default_config()
        settings.update(body.settings)
        _save_settings(settings)
        return {"ok": True, "settings": settings}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/resume/import")
async def import_resume(file: UploadFile = File(...)):
    """Import a resume PDF and extract profile data."""
    try:
        if not str(file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(400, "resume-must-be-pdf")
        content = await file.read()
        if not content or len(content) > 10 * 1024 * 1024:
            raise HTTPException(400, "resume-size-invalid")
        os.makedirs(os.path.dirname(RESUME_PATH), exist_ok=True)
        with open(RESUME_PATH, "wb") as handle:
            handle.write(content)
        result = json.loads(resume_import(RESUME_PATH))
        if result.get("ok"):
            profile = _load_profile()
            extracted = result.get("profile", {})
            profile["personalInformation"] = _merge_meaningful(
                profile.get("personalInformation", {}),
                extracted.get("personalInformation", {}),
            )
            profile["education"] = extracted.get("education", []) or profile.get("education", [])
            profile["workExperience"] = extracted.get("workExperience", []) or profile.get("workExperience", [])
            profile["skillCategories"] = extracted.get("skillCategories", []) or profile.get("skillCategories", [])
            profile["resumeFormat"] = "pdf"
            profile["resumePath"] = RESUME_PATH
            _save_profile(profile)
            result["resumePath"] = RESUME_PATH
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/resume")
def download_source_resume():
    """Open the current source resume PDF from Nori's local state."""
    try:
        configured = Path(str(_load_profile().get("resumePath") or RESUME_PATH)).resolve()
        allowed_default = Path(RESUME_PATH).resolve()
        allowed_state = Path(STORE).resolve().parent
        if configured.suffix.lower() != ".pdf" or not configured.is_file():
            raise HTTPException(404, "resume-file-missing")
        if configured != allowed_default and not configured.is_relative_to(allowed_state):
            raise HTTPException(404, "resume-file-outside-local-state")
        return FileResponse(configured, media_type="application/pdf",
                            filename=configured.name, content_disposition_type="inline")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ---------------------------------------------------------------------------
# Feed
# ---------------------------------------------------------------------------
@app.post("/api/feed")
def fetch_feed_endpoint(body: FeedRequest):
    """Search HiringCafe or fetch a legacy public ATS board."""
    try:
        result = _feed_request(body)
        if not result.get("ok"):
            raise HTTPException(502, result.get("error") or "job-search-failed")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/feed/save")
def save_feed_endpoint(body: FeedRequest):
    """Fetch and persist a feed."""
    try:
        result = _feed_request(body)
        if not result.get("ok"):
            raise HTTPException(502, result.get("error") or "job-search-failed")
        saved = json.loads(save_feed(result.get("jobs") or []))
        return {**saved, "jobs": result.get("jobs") or []}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/feed/load")
def load_feed_endpoint():
    """Load the persisted feed."""
    try:
        settings = load_monitor_settings(MONITOR_PATH, include_secrets=False)
        jobs = rank_hiringcafe_jobs(load_feed(), _load_profile(),
                                    settings.get("query", ""),
                                    settings.get("location", ""),
                                    bool(settings.get("remoteOnly")), preferences=settings)
        return {"ok": True, "count": len(jobs), "jobs": jobs}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/feed/top")
def top_matches_endpoint(limit: int = 6):
    """Return only meaningful saved matches for the dashboard."""
    try:
        settings = load_monitor_settings(MONITOR_PATH, include_secrets=False)
        jobs = rank_hiringcafe_jobs(load_feed(), _load_profile(),
                                    settings.get("query", ""),
                                    settings.get("location", ""),
                                    bool(settings.get("remoteOnly")), preferences=settings)
        threshold = max(1, int(settings.get("minScore") or 25))
        matches = [job for job in jobs if int(job.get("matchScore") or 0) >= threshold]
        matches = matches[:max(1, min(int(limit), 20))]
        return {"ok": True, "count": len(matches), "jobs": matches,
                "minimumScore": threshold}
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ---------------------------------------------------------------------------
# Overnight monitor
# ---------------------------------------------------------------------------
@app.get("/api/automation/readiness")
def automation_readiness():
    """Return an evidence-based preflight for safe overnight preparation."""
    try:
        profile = _load_profile()
        validation = validate_profile(profile)
        monitor = load_monitor_settings(MONITOR_PATH, include_secrets=False)
        ai = ai_provider_status()
        resume_path = str(profile.get("resumePath") or RESUME_PATH)
        resume_ready = bool(
            resume_path and os.path.isfile(resume_path) and os.path.getsize(resume_path) > 0)
        lanes = [lane for lane in (monitor.get("lanes") or [])
                 if isinstance(lane, dict) and lane.get("enabled", True)
                 and str(lane.get("query") or "").strip()]
        query_ready = bool(str(monitor.get("query") or "").strip() or lanes)
        checks = [
            {"id": "profile", "label": "Complete real profile",
             "ok": bool(validation.get("valid")) and not _is_test_profile(profile),
             "required": True},
            {"id": "resume", "label": "Readable source resume",
             "ok": resume_ready, "required": True},
            {"id": "authorization", "label": "Work authorization reviewed",
             "ok": _work_authorization_attested(profile), "required": True},
            {"id": "ai", "label": "AI provider connected",
             "ok": bool(ai.get("configured")) and not bool(ai.get("lastError")),
             "required": True},
            {"id": "search", "label": "At least one job search configured",
             "ok": query_ready, "required": True},
            {"id": "telegram", "label": "Telegram alerts connected",
             "ok": bool(monitor.get("telegramConfigured")), "required": False},
        ]
        blockers = [check["label"] for check in checks
                    if check["required"] and not check["ok"]]
        unattended = [item for item in ats_capabilities()
                      if item.get("unattendedSubmit")]
        warnings = []
        if not monitor.get("telegramConfigured"):
            warnings.append("Overnight matches remain visible in Nori, but phone alerts are not configured.")
        if not unattended:
            warnings.append("No ATS is certified for unattended submission; automation stops at review.")
        auth = profile.get("workAuthorization", {})
        return {
            "ok": True,
            "readyToPrepare": not blockers,
            "readyToMonitor": query_ready,
            "readyToSubmitUnattended": bool(unattended) and not blockers,
            "checks": checks,
            "blockers": blockers,
            "warnings": warnings,
            "workAuthorization": {
                "isAuthorizedToWork": auth.get("isAuthorizedToWork"),
                "needsSponsorship": auth.get("needsSponsorship"),
                "reviewedAt": auth.get("reviewedAt") or "",
            },
            "certifiedUnattendedAts": [item.get("id") for item in unattended],
        }
    except Exception as exc:
        return {"ok": False, "readyToPrepare": False,
                "readyToMonitor": False, "readyToSubmitUnattended": False,
                "checks": [], "blockers": [str(exc) or "readiness-check-failed"],
                "warnings": [], "certifiedUnattendedAts": []}


@app.get("/api/monitor")
def get_monitor_settings():
    """Return monitor status without exposing the Telegram bot token."""
    return load_monitor_settings(MONITOR_PATH, include_secrets=False)


@app.get("/api/monitor/preview")
def get_monitor_preview(days: int = 7):
    """Preview current candidates and the bounded automation budget."""
    settings = load_monitor_settings(MONITOR_PATH, include_secrets=False)
    return monitor_preview(settings, load_feed(), _tracked_urls(), days)


@app.put("/api/monitor")
def update_monitor_settings(body: MonitorSettingsUpdate):
    """Persist overnight discovery and Telegram settings."""
    try:
        current = load_monitor_settings(MONITOR_PATH, include_secrets=True)
        editable = {'enabled', 'query', 'location', 'remoteOnly', 'intervalMinutes',
                    'limit', 'minScore', 'telegramBotToken', 'telegramChatId',
                    'savedSearchUrl', 'excludedTitles', 'minimumSalary', 'strictLocation',
                    'applicationMode', 'maxApplicationsPerCycle', 'dailyApplicationCap',
                    'minMatchQuality', 'standingInstructions', 'lanes'}
        incoming = {key: value for key, value in body.settings.items() if key in editable}
        if not str(incoming.get("telegramBotToken") or "").strip():
            incoming.pop("telegramBotToken", None)
        current.update(incoming)
        result = json.loads(save_monitor_settings(current, MONITOR_PATH))
        if not result.get("ok"):
            raise HTTPException(400, result.get("error") or "monitor-save-failed")
        if "pytest" not in sys.modules:
            _ensure_monitor_thread()
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/monitor/run")
def run_monitor_now():
    """Run one HiringCafe monitor cycle immediately."""
    result = _run_monitor_cycle()
    if not result.get("ok"):
        raise HTTPException(502, result.get("error") or "monitor-run-failed")
    return result


@app.post("/api/monitor/test")
def test_monitor_notification():
    """Send one harmless Telegram connection test."""
    settings = load_monitor_settings(MONITOR_PATH, include_secrets=True)
    result = json.loads(send_telegram_jobs(
        settings.get("telegramBotToken", ""), settings.get("telegramChatId", ""), [{
            "title": "Telegram notifications are connected",
            "companyName": "Nori AI",
            "location": "Local monitor",
            "matchScore": 100,
            "url": "https://hiringcafe.com/",
        }],
    ))
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "telegram-test-failed")
    return result


# ---------------------------------------------------------------------------
# ATS catalog
# ---------------------------------------------------------------------------
@app.get("/api/atses")
def ats_catalog():
    """ATS catalog with honest, per-adapter execution capabilities."""
    return [{"id": item["ats"], **item} for item in ats_capabilities()]


# ---------------------------------------------------------------------------
# LinkedIn
# ---------------------------------------------------------------------------
@app.post("/api/linkedin/search")
def linkedin_search(
    keywords: str = Form(...),
    location: str = Form(""),
    pages: int = Form(1),
    detail: int = Form(0),
):
    """Guest-mode LinkedIn job search."""
    try:
        result = json.loads(linkedin_guest_search(keywords, location, pages=pages))
        if result.get("ok") and detail > 0:
            cards = result.get("cards", [])
            for i, card in enumerate(cards[:detail]):
                try:
                    d = json.loads(linkedin_guest_detail(card["jobId"]))
                    if d.get("ok"):
                        card.update(d.get("job", {}))
                except Exception:
                    pass
                cards[i] = card
        return result
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/linkedin/resolve")
def linkedin_resolve(job_id: str = Form(...), cookies: str | None = Form(None)):
    """Resolve a LinkedIn job to its external apply URL."""
    try:
        return json.loads(linkedin_resolve_apply_url(job_id, cookies=cookies))
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/linkedin/harvest")
def linkedin_harvest(body: LinkedInHarvestRequest):
    """Import harvested LinkedIn entries from the extension."""
    try:
        profile = _load_profile()
        created = 0
        skipped = 0
        tracked = _tracked_urls()
        for entry in body.entries:
            url = entry.get("url", "")
            normalized = str(url).rstrip("/")
            if not normalized or normalized in tracked:
                skipped += 1
                continue
            result = json.loads(create_job(url, profile, _load_settings(),
                                           company_name=entry.get("company") or "",
                                           job_title=entry.get("title") or "",
                                           store_path=STORE))
            if result.get("ok"):
                created += 1
                tracked.add(normalized)
            else:
                skipped += 1
        return {"ok": True, "created": created, "skipped": skipped}
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ---------------------------------------------------------------------------
# Inbox / read-only Gmail
# ---------------------------------------------------------------------------
@app.get("/api/inbox")
def inbox_messages():
    """Return cached job-message metadata and token-free Gmail status."""
    try:
        inbox = json.loads(gmail_load_inbox(GMAIL_INBOX_PATH))
        status = json.loads(gmail_connection_status(GMAIL_SECRET_DIR))
        return {**inbox, "authorized": bool(status.get("authorized")),
                "scope": status.get("scope"),
                "connectionError": status.get("error") if not status.get("ok") else ""}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/inbox/gmail/connect")
def inbox_gmail_connect(body: GmailConnectRequest):
    """Start local PKCE OAuth for Gmail read-only access."""
    try:
        result = json.loads(gmail_begin_authorization(
            body.client_id, body.redirect_uri, GMAIL_SECRET_DIR,
            client_secret=body.client_secret))
        if not result.get("ok"):
            raise HTTPException(400, result.get("error") or "gmail-connect-failed")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/inbox/gmail/callback", response_class=HTMLResponse)
def inbox_gmail_callback(request: Request):
    """Complete Gmail OAuth and show a token-free local success page."""
    result = json.loads(gmail_complete_authorization(str(request.url), GMAIL_SECRET_DIR))
    ok = bool(result.get("ok"))
    title = "Gmail connected" if ok else "Gmail connection failed"
    detail = ("Return to Nori AI and click Sync inbox." if ok
              else str(result.get("error") or "Please retry from Nori AI."))
    return HTMLResponse(
        f"<!doctype html><html><head><title>{html.escape(title)}</title>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'></head>"
        "<body style='font:16px system-ui;background:#111827;color:#f9fafb;padding:48px'>"
        f"<h1>{html.escape(title)}</h1><p>{html.escape(detail)}</p></body></html>",
        status_code=200 if ok else 400,
    )


@app.post("/api/inbox/gmail/sync")
def inbox_gmail_sync(body: GmailSyncRequest):
    """Synchronize bounded Gmail metadata and snippets; never send mail."""
    try:
        result = json.loads(gmail_sync_messages(
            GMAIL_INBOX_PATH, body.max_messages, GMAIL_SECRET_DIR))
        if not result.get("ok"):
            raise HTTPException(502, result.get("error") or "gmail-sync-failed")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.delete("/api/inbox/gmail")
def inbox_gmail_disconnect():
    """Delete only Nori's local encrypted Gmail credentials."""
    try:
        result = json.loads(gmail_disconnect(GMAIL_SECRET_DIR))
        if not result.get("ok"):
            raise HTTPException(500, result.get("error") or "gmail-disconnect-failed")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ---------------------------------------------------------------------------
# Networking / recruiter and vendor CRM
# ---------------------------------------------------------------------------
@app.get("/api/networking/contacts")
def networking_contacts(query: str = "", status: str = "", chicago_only: bool = True):
    """List recruiter/vendor contacts with optional search and Chicago filter."""
    try:
        result = json.loads(network_list_contacts(
            NETWORK_STORE,
            query=query,
            status=status,
            chicago_only=chicago_only,
        ))
        if not result.get("ok"):
            raise HTTPException(500, result.get("error", "network-list-failed"))
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/networking/contacts")
def networking_upsert(body: NetworkingContactRequest):
    """Create or enrich a local recruiter/vendor record and rescore it."""
    try:
        result = json.loads(network_upsert_contact(body.contact, NETWORK_STORE))
        if not result.get("ok"):
            raise HTTPException(400, result.get("error", "network-upsert-failed"))
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/networking/contacts/{contact_id}")
def networking_contact(contact_id: str):
    """Return one local recruiter/vendor record with evidence and score."""
    try:
        result = json.loads(network_get_contact(contact_id, NETWORK_STORE))
        if not result.get("ok"):
            raise HTTPException(404, result.get("error", "not-found"))
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.patch("/api/networking/contacts/{contact_id}")
def networking_update(contact_id: str, body: NetworkingContactUpdate):
    """Update contact status, notes, signals, tags, risk flags, or evidence."""
    try:
        result = json.loads(network_update_contact(contact_id, body.updates, NETWORK_STORE))
        if not result.get("ok"):
            code = 404 if result.get("error") == "not-found" else 400
            raise HTTPException(code, result.get("error", "network-update-failed"))
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.delete("/api/networking/contacts/{contact_id}")
def networking_delete(contact_id: str):
    """Delete an invalid or unwanted local networking contact."""
    try:
        result = json.loads(network_delete_contact(contact_id, NETWORK_STORE))
        if not result.get("ok"):
            raise HTTPException(404, result.get("error", "not-found"))
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/networking/contacts/{contact_id}/draft")
def networking_draft(contact_id: str):
    """Generate and save a review-only STEM-OPT outreach draft; never send it."""
    try:
        result = json.loads(network_draft_outreach(contact_id, NETWORK_STORE))
        if not result.get("ok"):
            code = 404 if result.get("error") == "not-found" else 400
            raise HTTPException(code, result.get("error", "draft-failed"))
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ---------------------------------------------------------------------------
# Static frontend (production)
# ---------------------------------------------------------------------------
STATIC_DIR = ROOT / "webapp" / "frontend" / "dist"

if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str = ""):
        """Serve the React SPA for all non-API routes."""
        path = STATIC_DIR / (full_path or "index.html")
        if path.exists() and path.is_file():
            return FileResponse(path)
        return FileResponse(STATIC_DIR / "index.html")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--prod", action="store_true", help="production mode")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    print(f"TsentaClone webapp @ http://localhost:{args.port}")
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=args.port,
        reload=not args.prod,
        reload_dirs=[str(ROOT / "backend" / "src" / "tools")] if not args.prod else None,
    )
