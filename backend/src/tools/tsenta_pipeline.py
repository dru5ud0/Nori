"""tsenta_pipeline — review gate + auto-submit state machine (M5).

Recovered status pipeline: queued → review → running → applied | failed | paused.
Jobs are persisted as JSON in a local store (atomic writes). The review gate
mirrors the recovered product gates:

- autoSubmitApplication (default False): when False (or reviewBeforeSubmit
  True), an automated run stops at "review" after walking + answering the form
  WITHOUT submitting. The user must call review_approve() to submit.
- review_approve(): the explicit user confirmation — always runs the real
  submit path (dry_run=False, confirmed=True).
- review_reject(): review → paused.
- resume_job(): paused → running (re-walk; gates apply again).

create_job() enforces the recovered PROFILE_INCOMPLETE gate (400 contract with
missingFields) via tsenta_profiles.validate_profile.

Store layout: {"applications": {<id>: {...}}} — each job record keeps
statusHistory[{status,timestamp}], the apply result, and the full trace.

All public functions return strings (JSON) or dicts and catch exceptions
internally; the store is never left half-written.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager

try:
    import msvcrt
except ImportError:  # non-Windows: fall back to an unlocked store
    msvcrt = None

try:
    from backend.src.tools.tsenta_config import default_config
    from backend.src.tools.tsenta_profiles import validate_profile
    from backend.src.tools.tsenta_ats import ats_detect, ats_normalize_hint
    from backend.src.tools.tsenta_capabilities import (
        ats_can_prepare, ats_can_unattended_submit,
    )
except ImportError:
    from tsenta_config import default_config
    from tsenta_profiles import validate_profile
    from tsenta_ats import ats_detect, ats_normalize_hint
    from tsenta_capabilities import ats_can_prepare, ats_can_unattended_submit

# Recovered status pipeline.
STATUS_QUEUED = "queued"
STATUS_REVIEW = "review"
STATUS_RUNNING = "running"
STATUS_APPLIED = "applied"
STATUS_FAILED = "failed"
STATUS_PAUSED = "paused"
ALL_STATUSES = (STATUS_QUEUED, STATUS_REVIEW, STATUS_RUNNING,
                STATUS_APPLIED, STATUS_FAILED, STATUS_PAUSED)
TRACKER_STAGES = ("applied", "interviewing", "offer", "rejected")

# Allowed transitions. Applied is terminal; failed applications remain
# retryable after a form/adapter fix or a user profile correction.
_TRANSITIONS = {
    STATUS_QUEUED: (STATUS_RUNNING,),
    STATUS_RUNNING: (STATUS_REVIEW, STATUS_APPLIED, STATUS_FAILED, STATUS_PAUSED),
    STATUS_REVIEW: (STATUS_RUNNING, STATUS_PAUSED),
    STATUS_PAUSED: (STATUS_RUNNING,),
    STATUS_APPLIED: (),
    STATUS_FAILED: (STATUS_RUNNING,),
}

_DEFAULT_STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "..", "..", "..", "loot", "state", "applications.json")


def default_store_path() -> str:
    """Resolve the default jobs store path (loot/state/applications.json).

    Returns:
        str: absolute path; the parent directory is created on demand by
        _load_store(). Never raises.
    """
    return os.path.abspath(_DEFAULT_STORE)


def _load_store(store_path: str) -> dict:
    """Read the store file; returns the store dict (empty on any failure)."""
    try:
        with open(store_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict) and isinstance(data.get("applications"), dict):
            return data
    except Exception:
        pass
    return {"applications": {}}


def _save_store(store: dict, store_path: str) -> None:
    """Atomically persist the store (write tmp file, then rename)."""
    directory = os.path.dirname(store_path)
    try:
        os.makedirs(directory, exist_ok=True)
        tmp_path = store_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(store, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_path, store_path)
    except Exception:
        pass


@contextmanager
def _store_lock(store_path: str, timeout_ms: int = 15000):
    """Exclusive cross-process lock on the store (sidecar .lock file).

    Uses an OS byte-range lock (msvcrt, Windows); no-op on other platforms.
    Waits up to timeout_ms, then raises OSError("store-lock-timeout").

    Args:
        store_path: store file path.
        timeout_ms: how long to wait for the lock.

    Yields:
        None. The lock is always released on exit.
    """
    if msvcrt is None:
        yield
        return
    lock_path = store_path + ".lock"
    deadline = time.time() + timeout_ms / 1000.0
    handle = None
    while True:
        try:
            handle = open(lock_path, "a+")
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            break
        except OSError:
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    pass
                handle = None
            if time.time() >= deadline:
                raise OSError("store-lock-timeout")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
        try:
            handle.close()
        except Exception:
            pass


def _now_ms() -> int:
    return int(time.time() * 1000)


def _new_id() -> str:
    return f"app_{int(time.time())}_{uuid.uuid4().hex[:8]}"


def _job_record(job_id: str, url: str, profile: dict, config: dict,
                 company_name: str = "", job_title: str = "",
                 company_domain: str = "", logo_url: str = "") -> dict:
    """Build a fresh queued job record."""
    return {
        "applicationId": job_id,
        "url": url,
        "status": STATUS_QUEUED,
        "statusHistory": [{"status": STATUS_QUEUED, "timestamp": _now_ms()}],
        "atsType": ats_normalize_hint(config.get("atsHint") or ""),
        "atsHint": ats_normalize_hint(config.get("atsHint") or ""),
        "companyName": company_name,
        "companyDomain": company_domain,
        "logoUrl": logo_url,
        "jobTitle": job_title,
        "jobDescription": config.get('jobDescription', ''),
        "jobLocation": config.get('jobLocation', ''),
        "config": config,
        "createdAt": _now_ms(),
        "updatedAt": _now_ms(),
        "submitted": False,
        "dryRun": True,
        "error": None,
        "answersSummary": {},
        "answerOverrides": {},
        "sources": {},
        "trace": {},
        "submissionReceipt": {},
        "documents": {},
        "source": config.get("source", "web"),
        "saveTimestamp": config.get("saveTimestamp", ""),
    }


def create_job(url: str, profile: dict, config: dict | None = None,
               company_name: str = "", job_title: str = "",
               company_domain: str = "", logo_url: str = "",
               store_path: str | None = None) -> str:
    """Create a new application job in the queued state.

    Args:
        url: job/apply URL.
        profile: candidate profile dict.
        config: apply config dict (defaults via tsenta_config).
        company_name: optional company name for the record.
        job_title: optional job title for the record.
        company_domain: optional employer website domain used for branding.
        logo_url: optional employer logo URL.
        store_path: store file path (default loot/state/applications.json).

    Returns:
        str: JSON of {"ok": True, "applicationId", "status"} on success, or
        {"ok": False, "error": "PROFILE_INCOMPLETE", "missingFields": [...]}
        when the profile fails validation (recovered 400 contract), or
        {"ok": False, "error": ...} on any other failure. Never raises.
    """
    try:
        if not isinstance(profile, dict):
            return json.dumps({"ok": False, "error": "PROFILE_INCOMPLETE",
                               "missingFields": []})
        check = validate_profile(profile)
        if not check.get("valid"):
            return json.dumps({"ok": False, "error": "PROFILE_INCOMPLETE",
                               "missingFields": check.get("missing", [])})
        if not isinstance(url, str) or not url.strip():
            return json.dumps({"ok": False, "error": "invalid-url"})
        config = config or default_config()
        with _store_lock(store_path or default_store_path()):
            store = _load_store(store_path or default_store_path())
            job = _job_record(_new_id(), url.strip(), profile, config,
                              company_name, job_title, company_domain, logo_url)
            store["applications"][job["applicationId"]] = job
            _save_store(store, store_path or default_store_path())
        return json.dumps({"ok": True, "applicationId": job["applicationId"],
                           "status": STATUS_QUEUED})
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc) or "create-failed"})


def _get_job(store: dict, job_id: str) -> dict | None:
    return store.get("applications", {}).get(job_id)


def _transition(store: dict, job: dict, to: str, store_path: str,
                reason: str = "") -> bool:
    """Apply a validated status transition; persists on success.

    Returns:
        bool: True when the transition was valid and persisted.
    """
    allowed = _TRANSITIONS.get(job.get("status"), ())
    if to not in allowed:
        return False
    job["status"] = to
    job["updatedAt"] = _now_ms()
    job["statusHistory"].append({"status": to, "timestamp": _now_ms()})
    if reason:
        job["error"] = reason
    _save_store(store, store_path)
    return True


def recover_interrupted_jobs(store_path: str | None = None) -> str:
    """Pause jobs left running by a previous process crash or shutdown.

    The function is intended to run once at server startup, before any worker
    begins. A paused job is retryable and retains its prior trace/documents.
    """
    store_path = store_path or default_store_path()
    try:
        recovered = []
        with _store_lock(store_path):
            store = _load_store(store_path)
            for job in store.get("applications", {}).values():
                if not isinstance(job, dict) or job.get("status") != STATUS_RUNNING:
                    continue
                job["status"] = STATUS_PAUSED
                job["updatedAt"] = _now_ms()
                job["error"] = "interrupted-run-recovered"
                job.setdefault("statusHistory", []).append({
                    "status": STATUS_PAUSED,
                    "timestamp": _now_ms(),
                    "reason": "interrupted-run-recovered",
                })
                recovered.append(job.get("applicationId"))
            if recovered:
                _save_store(store, store_path)
        return json.dumps({"ok": True, "recovered": len(recovered),
                           "applicationIds": recovered})
    except Exception as exc:
        return json.dumps({"ok": False, "recovered": 0,
                           "applicationIds": [],
                           "error": str(exc) or "recovery-failed"})


def _answerer_with_documents(answerer, documents: dict) -> callable:
    """Wrap an answerer so generated cover-letter text answers CL text fields."""
    letter = (documents or {}).get("coverLetter") or {}
    text = letter.get("coverLetterText")
    use = bool(letter.get("useCoverLetter")) and bool(text)
    if not use or answerer is None:
        return answerer

    def wrapped(field: dict, profile: dict, config: dict, trace) -> dict:
        try:
            label = str(field.get("label") or "").lower()
            kind = field.get("kind")
            if kind in ("text", "textarea") and ("cover letter" in label
                                                 or "coverletter" in label
                                                 or "letter of interest" in label):
                return {"value": text, "source": "profile-direct",
                        "display": "Cover letter (auto-generated)"}
        except Exception:
            pass
        return answerer(field, profile, config, trace)

    return wrapped


def _answerer_with_overrides(answerer, overrides: dict) -> callable:
    """Wrap an answerer so reviewed user values have highest priority."""
    if answerer is None or not isinstance(overrides, dict) or not overrides:
        return answerer

    def wrapped(field: dict, profile: dict, config: dict, trace) -> dict:
        try:
            field_id = str(field.get("field_id") or "")
            if field_id in overrides:
                value = overrides[field_id]
                display = str(value)
                for option in field.get("options") or []:
                    if isinstance(option, dict) and str(option.get("value")) == str(value):
                        display = str(option.get("label") or value)
                        break
                return {"value": value, "source": "user-override", "display": display}
        except Exception:
            pass
        return answerer(field, profile, config, trace)

    return wrapped


def _run_apply(job: dict, profile: dict, config: dict, answerer=None,
               resume_path: str | None = None, headless: bool = True,
               dry_run: bool = True, confirmed: bool = False,
               timeout_ms: int = 45000, _page_provider=None,
               stealth: bool = True, artifact_dir: str | None = None) -> dict:
    """Execute apply_job and fold the result into the job record."""
    try:
        from backend.src.tools.tsenta_apply import apply_job
    except ImportError:
        from tsenta_apply import apply_job

    try:
        from backend.src.tools.tsenta_documents import (
            documents_for_application, fetch_job_context, materialize_documents,
        )
    except ImportError:
        from tsenta_documents import (
            documents_for_application, fetch_job_context, materialize_documents,
        )

    job_context = {
        "company": job.get("companyName") or "",
        "title": job.get("jobTitle") or "",
        "location": job.get("jobLocation") or "",
        "description": job.get("jobDescription") or "",
    }
    if _page_provider is None and (len(job_context.get('description', '')) < 1500
                                   or any(not job_context.get(key) for key in ('company', 'title'))):
        discovered = fetch_job_context(job.get("url") or "")
        for key in ("company", "title", "location", "description"):
            if not job_context.get(key) and discovered.get(key):
                job_context[key] = discovered[key]
        if len(discovered.get('description') or '') > len(job_context.get('description') or ''):
            job_context['description'] = discovered['description']
        job_context["source"] = discovered.get("source") or ""
    if job_context.get("company"):
        job["companyName"] = job_context["company"]
    if job_context.get("title"):
        job["jobTitle"] = job_context["title"]
    if job_context.get("location"):
        job["jobLocation"] = job_context["location"]
    if job_context.get("description"):
        job["jobDescription"] = job_context["description"]

    reuse_review = not dry_run and bool(job.get('documents'))
    documents = job['documents'] if reuse_review else documents_for_application(
        profile, config, job_context=job_context)
    if artifact_dir and _page_provider is None and not reuse_review:
        documents = materialize_documents(
            documents, job.get("applicationId") or "application", artifact_dir)
    documents["jobContext"] = job_context

    resume_document = documents.get("resume") or {}
    cover_document = documents.get("coverLetter") or {}
    if resume_document.get("useOptimizedResume"):
        effective_resume_path = (resume_document.get("pdfPath")
                                 if resume_document.get("attachmentReady") else None)
    else:
        effective_resume_path = (resume_path
                                 or profile.get("resumePath")
                                 or profile.get("resumeSource"))
        if effective_resume_path and not os.path.exists(effective_resume_path):
            alt = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "loot", "state", "resume.pdf")
            if os.path.exists(alt):
                effective_resume_path = os.path.abspath(alt)
    effective_cover_path = (cover_document.get("pdfPath")
                            if cover_document.get("attachmentReady") else None)
    resume_document["selectedForUpload"] = effective_resume_path or ""
    cover_document["selectedForUpload"] = effective_cover_path or ""
    if answerer is None:
        try:
            from backend.src.tools.tsenta_llm import make_llm_answerer
        except ImportError:
            from tsenta_llm import make_llm_answerer
        answerer = make_llm_answerer(profile, job_context=job_context)
    if not dry_run:
        answerer = _answerer_with_reviewed_values(answerer, (job.get('trace') or {}).get('answers') or [])
    answerer = _answerer_with_documents(answerer, documents)
    answerer = _answerer_with_overrides(answerer, job.get("answerOverrides") or {})

    result = json.loads(apply_job(job["url"], profile, config, dry_run=dry_run,
                                  resume_path=effective_resume_path,
                                  cover_letter_path=effective_cover_path,
                                  answerer=answerer,
                                  headless=headless, confirmed=confirmed,
                                  timeout_ms=timeout_ms,
                                  _page_provider=_page_provider,
                                  stealth=stealth,
                                  ats_hint=job.get("atsHint") or job.get("atsType") or ""))
    job["atsType"] = result.get("ats", "unknown")
    job["submitted"] = bool(result.get("submitted"))
    job["dryRun"] = bool(result.get("dry_run"))
    job["error"] = result.get("error")
    job["answersSummary"] = result.get("answers_summary", {})
    job["sources"] = result.get("sources", {})
    job["trace"] = result.get("trace", {})
    job["submissionReceipt"] = result.get("submission_receipt", {})
    job["documents"] = documents
    job["updatedAt"] = _now_ms()
    return result


def _answerer_with_reviewed_values(answerer, answers: list):
    """Keep reviewed generated answers stable; new questions use the normal answerer."""
    reviewed = {(str(a.get('fieldId')), str(a.get('label'))): a for a in answers
                if a.get('source') in ('llm', 'user-override')}
    def wrapped(field, profile, config, trace):
        previous = reviewed.get((str(field.get('field_id')), str(field.get('label'))))
        if previous:
            return {key: previous.get(key) for key in ('value', 'source', 'display')}
        return answerer(field, profile, config, trace)
    return wrapped


def run_job(job_id: str, profile: dict, config: dict | None = None,
            confirmed: bool = False, answerer=None, resume_path: str | None = None,
            headless: bool = True, timeout_ms: int = 45000,
            store_path: str | None = None, _page_provider=None,
            stealth: bool = True) -> str:
    """Run a queued, paused, or failed job through the state machine.

    Gates (recovered semantics): the real submit path runs only when
    confirmed=True AND autoSubmitApplication=True AND reviewBeforeSubmit=False.
    Otherwise the walk runs in dry-run and the job stops at "review" with
    submitted=False — review_approve() is the explicit user confirmation that
    submits.

    Args:
        job_id: application id from create_job().
        profile: candidate profile dict.
        config: apply config dict (defaults).
        confirmed: explicit user confirmation for auto-submit.
        answerer: answerer callable; defaults to the LLM answerer.
        resume_path: local resume file for file inputs.
        headless: chromium headless vs headed.
        timeout_ms: apply timeout budget.
        store_path: store file path.
        _page_provider: test hook (playwright page provider).

    Returns:
        str: JSON of {"ok", "applicationId", "status", "submitted", "error"}.
        Never raises.
    """
    store_path = store_path or default_store_path()
    try:
        with _store_lock(store_path):
            store = _load_store(store_path)
            job = _get_job(store, job_id)
            if job is None:
                return json.dumps({"ok": False, "applicationId": job_id,
                                   "status": "missing", "submitted": False,
                                   "error": "job-not-found"})
            if job.get("status") not in (STATUS_QUEUED, STATUS_PAUSED, STATUS_FAILED):
                return json.dumps({"ok": False, "applicationId": job_id,
                                   "status": job.get("status"), "submitted": False,
                                   "error": "invalid-transition"})
            config = config or job.get("config") or default_config()
            if not _transition(store, job, STATUS_RUNNING, store_path):
                return json.dumps({"ok": False, "applicationId": job_id,
                                   "status": job.get("status"), "submitted": False,
                                   "error": "invalid-transition"})

        auto_submit = bool(config.get("autoSubmitApplication")) and not bool(
            config.get("reviewBeforeSubmit"))
        ats_id = ats_detect(job.get("url") or "").get("ats_id", "unknown")
        if ats_id == "unknown":
            ats_id = ats_normalize_hint(job.get("atsHint") or job.get("atsType") or "")
        # Automated run_job submission is stricter than a user clicking the
        # review approval: the adapter must have live unattended certification.
        submit_now = bool(confirmed) and auto_submit and ats_can_unattended_submit(ats_id)
        result = _run_apply(job, profile, config, answerer=answerer,
                            resume_path=resume_path, headless=headless,
                            dry_run=not submit_now, confirmed=submit_now,
                            timeout_ms=timeout_ms, _page_provider=_page_provider,
                            stealth=stealth,
                            artifact_dir=os.path.join(os.path.dirname(store_path),
                                                      "applications", job_id))

        with _store_lock(store_path):
            store = _load_store(store_path)
            fresh = _get_job(store, job_id)
            if fresh is None:
                fresh = job
            for key in ("atsType", "submitted", "dryRun", "error",
                         "answersSummary", "sources", "trace", "documents",
                         "submissionReceipt",
                         "companyName", "jobTitle", "jobLocation",
                         "jobDescription", "updatedAt"):
                if key in job:
                    fresh[key] = job[key]
            job = fresh
            if submit_now:
                if result.get("submitted"):
                    _transition(store, job, STATUS_APPLIED, store_path)
                else:
                    _transition(store, job, STATUS_FAILED, store_path,
                                reason=result.get("error") or "submit-failed")
            else:
                _transition(store, job, STATUS_REVIEW, store_path)
        return json.dumps({"ok": True, "applicationId": job_id,
                           "status": job.get("status"),
                           "submitted": bool(job.get("submitted")),
                           "error": job.get("error")})
    except Exception as exc:
        return json.dumps({"ok": False, "applicationId": job_id,
                           "status": "failed", "submitted": False,
                           "error": str(exc) or "run-failed"})


def review_approve(job_id: str, profile: dict, answerer=None,
                   resume_path: str | None = None, headless: bool = True,
                   timeout_ms: int = 45000, store_path: str | None = None,
                   _page_provider=None, stealth: bool = True) -> str:
    """Approve a job sitting at the review gate: runs the REAL submit path.

    This is the explicit user confirmation. Equivalent to run_job with
    confirmed=True, autoSubmitApplication=True and reviewBeforeSubmit=False.

    Args:
        job_id: application id.
        profile: candidate profile dict.
        answerer: answerer callable (defaults to the LLM answerer).
        resume_path: local resume file for file inputs.
        headless: chromium headless vs headed.
        timeout_ms: apply timeout budget.
        store_path: store file path.
        _page_provider: test hook.

    Returns:
        str: JSON of {"ok", "applicationId", "status", "submitted", "error"}.
        Never raises.
    """
    store_path = store_path or default_store_path()
    try:
        with _store_lock(store_path):
            store = _load_store(store_path)
            job = _get_job(store, job_id)
            if job is None:
                return json.dumps({"ok": False, "applicationId": job_id,
                                   "status": "missing", "submitted": False,
                                   "error": "job-not-found"})
            if job.get("status") != STATUS_REVIEW:
                return json.dumps({"ok": False, "applicationId": job_id,
                                   "status": job.get("status"), "submitted": False,
                                   "error": "invalid-transition"})
            ats_id = ats_detect(job.get("url") or "").get("ats_id", "unknown")
            if ats_id == "unknown":
                ats_id = ats_normalize_hint(job.get("atsHint") or job.get("atsType") or "")
            if not ats_can_prepare(ats_id):
                return json.dumps({"ok": False, "applicationId": job_id,
                                   "status": job.get("status"), "submitted": False,
                                   "error": "ats-submit-not-supported"})
            config = job.get("config") or default_config()
            if not _transition(store, job, STATUS_RUNNING, store_path):
                return json.dumps({"ok": False, "applicationId": job_id,
                                   "status": job.get("status"), "submitted": False,
                                   "error": "invalid-transition"})
        result = _run_apply(job, profile, config, answerer=answerer,
                            resume_path=resume_path, headless=headless,
                            dry_run=False, confirmed=True,
                            timeout_ms=timeout_ms, _page_provider=_page_provider,
                            stealth=stealth,
                            artifact_dir=os.path.join(os.path.dirname(store_path),
                                                      "applications", job_id))
        with _store_lock(store_path):
            store = _load_store(store_path)
            fresh = _get_job(store, job_id)
            if fresh is None:
                fresh = job
            for key in ("atsType", "submitted", "dryRun", "error",
                         "answersSummary", "sources", "trace", "documents",
                         "submissionReceipt",
                         "companyName", "jobTitle", "jobLocation",
                         "jobDescription", "updatedAt"):
                if key in job:
                    fresh[key] = job[key]
            job = fresh
            if result.get("submitted"):
                _transition(store, job, STATUS_APPLIED, store_path)
                try:
                    from .tsenta_memory import remember_all_answers
                except ImportError:
                    try:
                        from tsenta_memory import remember_all_answers
                    except ImportError:
                        remember_all_answers = None
                if remember_all_answers is not None:
                    remember_all_answers((job.get("trace") or {}).get("answers") or [])
            else:
                _transition(store, job, STATUS_FAILED, store_path,
                            reason=result.get("error") or "submit-failed")
        return json.dumps({"ok": True, "applicationId": job_id,
                           "status": job.get("status"),
                           "submitted": bool(job.get("submitted")),
                           "error": job.get("error")})
    except Exception as exc:
        return json.dumps({"ok": False, "applicationId": job_id,
                           "status": "failed", "submitted": False,
                           "error": str(exc) or "approve-failed"})


def save_answer_overrides(job_id: str, answers: dict,
                          store_path: str | None = None) -> str:
    """Save reviewed answer values for the final application run.

    Args:
        job_id: application id currently at the review gate.
        answers: mapping of trace fieldId to reviewed JSON-safe value.
        store_path: optional application-store path.

    Returns:
        str: JSON {ok, applicationId, saved, error}. Only fields present in
        the dry-run trace can be changed, and only while status is review.
        Never raises.
    """
    store_path = store_path or default_store_path()
    try:
        if not isinstance(answers, dict):
            return json.dumps({"ok": False, "applicationId": job_id,
                               "saved": 0, "error": "answers-must-be-an-object"})
        with _store_lock(store_path):
            store = _load_store(store_path)
            job = _get_job(store, job_id)
            if job is None:
                return json.dumps({"ok": False, "applicationId": job_id,
                                   "saved": 0, "error": "job-not-found"})
            if job.get("status") != STATUS_REVIEW:
                return json.dumps({"ok": False, "applicationId": job_id,
                                   "saved": 0, "error": "answers-not-reviewable"})
            trace_answers = (job.get("trace") or {}).get("answers") or []
            known = {str(item.get("fieldId") or "") for item in trace_answers
                     if isinstance(item, dict) and item.get("fieldId")}
            sanitized = {}
            for field_id, value in answers.items():
                key = str(field_id or "")
                if key not in known:
                    continue
                if isinstance(value, str):
                    sanitized[key] = value[:20000]
                elif isinstance(value, (bool, int, float)) or value is None:
                    sanitized[key] = value
                elif isinstance(value, list):
                    sanitized[key] = [str(item)[:1000] for item in value[:100]]
            job["answerOverrides"] = sanitized
            try:
                from .tsenta_memory import remember_answer
            except ImportError:
                try:
                    from tsenta_memory import remember_answer
                except ImportError:
                    remember_answer = None

            for item in trace_answers:
                if not isinstance(item, dict):
                    continue
                field_id = str(item.get("fieldId") or "")
                if field_id in sanitized:
                    item.setdefault("originalSource", item.get("source") or "")
                    item["value"] = sanitized[field_id]
                    item["display"] = str(sanitized[field_id])
                    item["source"] = "user-override"
                    if remember_answer is not None:
                        label = str(item.get("label") or field_id)
                        remember_answer(label, sanitized[field_id], item.get("kind", "text"), item.get("options"))
            job["updatedAt"] = _now_ms()
            _save_store(store, store_path)
        return json.dumps({"ok": True, "applicationId": job_id,
                           "saved": len(sanitized), "error": None})
    except Exception as exc:
        return json.dumps({"ok": False, "applicationId": job_id,
                           "saved": 0, "error": str(exc) or "answer-save-failed"})


def update_tracker_stage(job_id: str, stage: str,
                         store_path: str | None = None) -> str:
    """Persist a user's CRM stage without changing execution status.

    Args:
        job_id: application id to update.
        stage: one of applied, interviewing, offer, or rejected.
        store_path: optional application-store path.

    Returns:
        str: JSON ``{ok, applicationId, trackerStage, error}``. This only
        updates the tracker view and never runs or submits an application.
        Never raises.
    """
    store_path = store_path or default_store_path()
    try:
        value = str(stage or "").strip().lower()
        if value not in TRACKER_STAGES:
            return json.dumps({"ok": False, "applicationId": job_id,
                               "trackerStage": "", "error": "invalid-tracker-stage"})
        with _store_lock(store_path):
            store = _load_store(store_path)
            job = _get_job(store, job_id)
            if job is None:
                return json.dumps({"ok": False, "applicationId": job_id,
                                   "trackerStage": "", "error": "job-not-found"})
            job["trackerStage"] = value
            job["updatedAt"] = _now_ms()
            _save_store(store, store_path)
        return json.dumps({"ok": True, "applicationId": job_id,
                           "trackerStage": value, "error": None})
    except Exception as exc:
        return json.dumps({"ok": False, "applicationId": job_id,
                           "trackerStage": "", "error": str(exc) or "tracker-update-failed"})


def set_job_archived(job_id: str, archived: bool = True,
                     store_path: str | None = None) -> str:
    """Archive or restore an application without deleting its audit history.

    Archiving is deliberately reversible. It removes clutter from the default
    application list and counts while retaining answers, generated documents,
    status history, and any receipt evidence.

    Args:
        job_id: Existing application id.
        archived: ``True`` to archive or ``False`` to restore.
        store_path: Optional application-store path.

    Returns:
        str: JSON ``{ok, applicationId, archived, archivedAt, error}``. Never
        raises.
    """
    store_path = store_path or default_store_path()
    try:
        target = bool(archived)
        with _store_lock(store_path):
            store = _load_store(store_path)
            job = _get_job(store, job_id)
            if job is None:
                return json.dumps({"ok": False, "applicationId": job_id,
                                   "archived": target, "archivedAt": None,
                                   "error": "job-not-found"})
            now = _now_ms()
            job["archived"] = target
            job["archivedAt"] = now if target else None
            job["updatedAt"] = now
            job.setdefault("activityHistory", []).append({
                "event": "archived" if target else "restored",
                "timestamp": now,
            })
            _save_store(store, store_path)
        return json.dumps({"ok": True, "applicationId": job_id,
                           "archived": target,
                           "archivedAt": job.get("archivedAt"), "error": None})
    except Exception as exc:
        return json.dumps({"ok": False, "applicationId": job_id,
                           "archived": bool(archived), "archivedAt": None,
                           "error": str(exc) or "archive-update-failed"})


def create_tracker_entry(company_name: str = "", job_title: str = "",
                           url: str = "", stage: str = "applied",
                           store_path: str | None = None) -> str:
    """Add an externally submitted role to the local tracker.

    This is deliberately separate from ``create_job``: imported or manually
    submitted applications do not have an ATS form to walk and must never be
    accidentally queued for browser automation.

    Args:
        company_name: employer name.
        job_title: role title.
        url: optional posting or tracker URL.
        stage: applied, interviewing, offer, or rejected.
        store_path: optional application-store path.

    Returns:
        str: JSON ``{ok, applicationId, trackerStage, error}``. Never raises.
    """
    store_path = store_path or default_store_path()
    try:
        value = str(stage or "applied").strip().lower()
        if value not in TRACKER_STAGES:
            return json.dumps({"ok": False, "applicationId": "",
                               "trackerStage": "", "error": "invalid-tracker-stage"})
        company = str(company_name or "").strip()[:300]
        title = str(job_title or "").strip()[:300]
        posting_url = str(url or "").strip()[:2000]
        if not company and not title:
            return json.dumps({"ok": False, "applicationId": "",
                               "trackerStage": "", "error": "company-or-title-required"})
        now = _now_ms()
        app_id = _new_id()
        job = {
            "applicationId": app_id,
            "url": posting_url,
            "status": STATUS_PAUSED,
            "statusHistory": [{"status": STATUS_PAUSED, "timestamp": now,
                               "reason": "manual-tracker-entry"}],
            "submitted": value in ("applied", "interviewing", "offer"),
            "atsType": "manual",
            "companyName": company,
            "jobTitle": title,
            "createdAt": now,
            "updatedAt": now,
            "error": None,
            "trackerStage": value,
            "manualTrackerEntry": True,
            "manualSubmissionConfirmed": value in ("applied", "interviewing", "offer"),
            "dryRun": True,
            "documents": {},
            "answersSummary": {},
            "trace": {},
        }
        with _store_lock(store_path):
            store = _load_store(store_path)
            store["applications"][app_id] = job
            _save_store(store, store_path)
        return json.dumps({"ok": True, "applicationId": app_id,
                           "trackerStage": value, "error": None})
    except Exception as exc:
        return json.dumps({"ok": False, "applicationId": "",
                           "trackerStage": "", "error": str(exc) or "tracker-entry-failed"})


def resolve_application_manually(job_id: str, resolution: str,
                                 store_path: str | None = None) -> str:
    """Record a user's manual resolution without running an ATS browser.

    Args:
        job_id: Existing application id.
        resolution: ``applied`` when the user confirms they submitted on the
            job site, or ``skipped`` when they choose not to continue.
        store_path: Optional application-store path.

    Returns:
        str: JSON ``{ok, applicationId, status, submitted, resolution, error}``.
        The applied state is explicitly tagged as user-confirmed rather than
        as an automated submission receipt. Never raises.
    """
    store_path = store_path or default_store_path()
    try:
        value = str(resolution or "").strip().lower()
        if value not in ("applied", "skipped"):
            return json.dumps({"ok": False, "applicationId": job_id,
                               "status": "", "submitted": False,
                               "resolution": value, "error": "invalid-resolution"})
        with _store_lock(store_path):
            store = _load_store(store_path)
            job = _get_job(store, job_id)
            if job is None:
                return json.dumps({"ok": False, "applicationId": job_id,
                                   "status": "missing", "submitted": False,
                                   "resolution": value, "error": "job-not-found"})
            now = _now_ms()
            if value == "applied":
                job["status"] = STATUS_APPLIED
                job["submitted"] = True
                job["trackerStage"] = "applied"
                job["manualSubmissionConfirmed"] = True
                reason = "user-confirmed-manual-submission"
            else:
                job["status"] = STATUS_PAUSED
                job["submitted"] = False
                job["manualSubmissionConfirmed"] = False
                reason = "user-skipped"
            job["manualResolution"] = value
            job["error"] = None
            job["updatedAt"] = now
            job.setdefault("statusHistory", []).append({
                "status": job["status"], "timestamp": now, "reason": reason,
            })
            _save_store(store, store_path)
        return json.dumps({"ok": True, "applicationId": job_id,
                           "status": job["status"],
                           "submitted": bool(job.get("submitted")),
                           "resolution": value, "error": None})
    except Exception as exc:
        return json.dumps({"ok": False, "applicationId": job_id,
                           "status": "failed", "submitted": False,
                           "resolution": str(resolution or ""),
                           "error": str(exc) or "manual-resolution-failed"})


def review_reject(job_id: str, store_path: str | None = None) -> str:
    """Reject a job at the review gate: review -> paused (never submits).

    Args:
        job_id: application id.
        store_path: store file path.

    Returns:
        str: JSON of {"ok", "applicationId", "status", "error"}. Never raises.
    """
    store_path = store_path or default_store_path()
    try:
        with _store_lock(store_path):
            store = _load_store(store_path)
            job = _get_job(store, job_id)
            if job is None:
                return json.dumps({"ok": False, "applicationId": job_id,
                                   "status": "missing", "error": "job-not-found"})
            if not _transition(store, job, STATUS_PAUSED, store_path):
                return json.dumps({"ok": False, "applicationId": job_id,
                                   "status": job.get("status"),
                                   "error": "invalid-transition"})
        return json.dumps({"ok": True, "applicationId": job_id,
                           "status": STATUS_PAUSED, "error": None})
    except Exception as exc:
        return json.dumps({"ok": False, "applicationId": job_id,
                           "status": "failed", "error": str(exc) or "reject-failed"})


def job_status(job_id: str, store_path: str | None = None) -> str:
    """Return a single job's status record.

    Args:
        job_id: application id.
        store_path: store file path.

    Returns:
        str: JSON of {"ok", "applicationId", "status", "submitted", "error",
        "atsType", "companyName", "jobTitle", "statusHistory"}; ok False +
        error job-not-found when unknown. Never raises.
    """
    store_path = store_path or default_store_path()
    try:
        store = _load_store(store_path)
        job = _get_job(store, job_id)
        if job is None:
            return json.dumps({"ok": False, "applicationId": job_id,
                               "status": "missing", "error": "job-not-found"})
        return json.dumps({"ok": True, "applicationId": job_id,
                           "status": job.get("status"),
                           "submitted": bool(job.get("submitted")),
                           "error": job.get("error"),
                           "atsType": job.get("atsType"),
                            "companyName": job.get("companyName"),
                            "companyDomain": job.get("companyDomain"),
                            "logoUrl": job.get("logoUrl"),
                            "jobTitle": job.get("jobTitle"),
                           "statusHistory": job.get("statusHistory", [])})
    except Exception as exc:
        return json.dumps({"ok": False, "applicationId": job_id,
                           "status": "failed", "error": str(exc) or "status-failed"})


def job_report(job_id: str, store_path: str | None = None) -> str:
    """Return a job's full record including trace and sources.

    Args:
        job_id: application id.
        store_path: store file path.

    Returns:
        str: JSON of the full job record; {"ok": False, "error":
        "job-not-found"} when unknown. Never raises.
    """
    store_path = store_path or default_store_path()
    try:
        store = _load_store(store_path)
        job = _get_job(store, job_id)
        if job is None:
            return json.dumps({"ok": False, "error": "job-not-found"})
        return json.dumps(job, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc) or "report-failed"})


def list_jobs(store_path: str | None = None,
              include_archived: bool = False) -> str:
    """List application jobs, newest first.

    Args:
        store_path: store file path.
        include_archived: include soft-archived records when true. The default
            remains the active application inbox only.

    Returns:
        str: JSON of {"ok": True, "applications": [{applicationId, url,
        status, submitted, atsType, companyName, jobTitle, createdAt,
        updatedAt, error}, ...]}. Never raises.
    """
    store_path = store_path or default_store_path()
    try:
        store = _load_store(store_path)
        jobs = sorted((j for j in store.get("applications", {}).values()
                       if include_archived or not j.get("archived")),
                      key=lambda j: j.get("createdAt", 0), reverse=True)
        return json.dumps({"ok": True, "applications": [
            {"applicationId": j.get("applicationId"), "url": j.get("url"),
             "status": j.get("status"), "submitted": bool(j.get("submitted")),
             "atsType": j.get("atsType"), "companyName": j.get("companyName"),
             "companyDomain": j.get("companyDomain"), "logoUrl": j.get("logoUrl"),
             "jobTitle": j.get("jobTitle"), "createdAt": j.get("createdAt"),
             "updatedAt": j.get("updatedAt"), "error": j.get("error"),
              "trackerStage": j.get("trackerStage"),
              "manualTrackerEntry": bool(j.get("manualTrackerEntry")),
              "manualSubmissionConfirmed": bool(j.get("manualSubmissionConfirmed")),
              "submissionReceipt": j.get("submissionReceipt") or {},
              "archived": bool(j.get("archived")),
              "archivedAt": j.get("archivedAt"),
              "documents": j.get("documents") or {},
             "answersSummary": j.get("answersSummary") or {}}
            for j in jobs]}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc) or "list-failed"})


def jobs_summary(store_path: str | None = None) -> str:
    """Count jobs per status (mirrors /applications/list/counts shape).

    Args:
        store_path: store file path.

    Returns:
        str: JSON of {"ok": True, "counts": {"all", "queued", "review",
        "running", "applied", "failed", "paused", "submitted", "in_flight",
        "needs"}}. Never raises.
    """
    store_path = store_path or default_store_path()
    try:
        store = _load_store(store_path)
        jobs = [j for j in store.get("applications", {}).values() if not j.get('archived')]
        counts = {status: 0 for status in ALL_STATUSES}
        submitted = 0
        for job in jobs:
            status = job.get("status")
            if status in counts:
                counts[status] += 1
            if job.get("submitted"):
                submitted += 1
        counts["all"] = len(jobs)
        counts["submitted"] = submitted
        counts["in_flight"] = counts[STATUS_RUNNING] + counts[STATUS_QUEUED]
        counts["needs"] = counts[STATUS_REVIEW]
        return json.dumps({"ok": True, "counts": counts})
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc) or "summary-failed"})


if __name__ == "__main__":
    import sys

    def _usage() -> None:
        print("usage: tsenta_pipeline <create|run|approve|reject|status|report|list|summary> ...")
        print("  create  <url> [company]        create a queued job (profile from profile.json)")
        print("  run     <id> [--confirmed]     run a job (stops at review unless confirmed)")
        print("  approve <id>                   submit a reviewed job for real")
        print("  reject  <id>                   pause a reviewed job")
        print("  status  <id> | report <id> | list | summary")

    def _load_cli_profile() -> dict:
        path = os.path.join(os.path.dirname(default_store_path()), "profile.json")
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return {}

    args = sys.argv[1:]
    if not args or args[0] not in ("create", "run", "approve", "reject",
                                   "status", "report", "list", "summary"):
        _usage()
        sys.exit(1)
    cmd = args[0]
    if cmd == "create":
        if len(args) < 2:
            _usage()
            sys.exit(1)
        print(create_job(args[1], _load_cli_profile(),
                         company_name=args[2] if len(args) > 2 else ""))
    elif cmd == "run":
        if len(args) < 2:
            _usage()
            sys.exit(1)
        profile = _load_cli_profile()
        print(run_job(args[1], profile, confirmed="--confirmed" in args))
    elif cmd == "approve":
        if len(args) < 2:
            _usage()
            sys.exit(1)
        print(review_approve(args[1], _load_cli_profile()))
    elif cmd == "reject":
        if len(args) < 2:
            _usage()
            sys.exit(1)
        print(review_reject(args[1]))
    elif cmd == "status":
        if len(args) < 2:
            _usage()
            sys.exit(1)
        print(job_status(args[1]))
    elif cmd == "report":
        if len(args) < 2:
            _usage()
            sys.exit(1)
        print(job_report(args[1]))
    elif cmd == "list":
        print(list_jobs())
    else:
        print(jobs_summary())
