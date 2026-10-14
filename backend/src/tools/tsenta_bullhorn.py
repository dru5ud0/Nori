"""Bullhorn Public REST job preflight and candidate-application transport.

Bullhorn's published-job integration is an API, not a browser form.  This
adapter validates the exact Bullhorn host/corp-token/job tuple, performs a
read-only published-job preflight, and exposes a guarded raw-resume POST for
the explicitly approved submit path.
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlsplit, urlunsplit


_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_RESUME_BYTES = 5 * 1024 * 1024
_RESUME_EXTENSIONS = {".doc", ".docx", ".pdf", ".rtf", ".txt"}
_JOB_FIELDS = (
    "id,title,publishedCategory(id,name),address(city,state,countryName),"
    "employmentType,dateLastPublished,publicDescription,isOpen,isPublic,isDeleted,"
    "salary,salaryUnit,willSponsor,yearsRequired"
)
_PUBLIC_PATH = re.compile(
    r"^/rest-services/(?P<token>[A-Za-z0-9_-]{2,80})/"
    r"(?:(?:search|query)/(?:JobOrder|JobBoardPost)(?:/(?P<path_id>\d+))?"
    r"|apply/(?P<apply_id>\d+)/raw)/?$",
    re.I,
)


def _host_allowed(host: str) -> bool:
    value = str(host or "").lower().rstrip(".")
    return bool(re.fullmatch(r"public-rest\d+\.bullhornstaffing\.com", value))


def bullhorn_job_identity(url: str) -> dict:
    """Parse and validate a Bullhorn Public REST job URL.

    Args:
        url: HTTPS Bullhorn published-job query/search or raw-apply URL.

    Returns:
        dict: ``{ok, host, corpToken, jobId, error}``. Only exact
        ``public-rest<cluster>.bullhornstaffing.com`` hosts are accepted;
        malformed/spoofed values return ``ok=False``. Never raises.
    """
    result = {"ok": False, "host": "", "corpToken": "", "jobId": "",
              "error": "bullhorn-job-url-invalid"}
    try:
        parts = urlsplit(str(url or "").strip())
        host = (parts.hostname or "").lower().rstrip(".")
        match = _PUBLIC_PATH.fullmatch(parts.path)
        if parts.scheme != "https" or not _host_allowed(host) or match is None:
            return result
        job_id = str(match.group("path_id") or match.group("apply_id") or "")
        query = parse_qs(parts.query, keep_blank_values=True)
        if not job_id:
            for key in ("jobId", "jobid", "id"):
                candidate = str((query.get(key) or [""])[0]).strip()
                if re.fullmatch(r"\d{1,18}", candidate):
                    job_id = candidate
                    break
        if not job_id:
            expression = " ".join(
                str(item) for key in ("where", "query")
                for item in (query.get(key) or [])
            )
            found = re.search(r"(?:^|[\s,(])id\s*[:=]\s*(\d{1,18})(?:$|[\s,)])",
                              expression, re.I)
            if found:
                job_id = found.group(1)
        if not re.fullmatch(r"\d{1,18}", job_id):
            return result
        result.update({
            "ok": True,
            "host": host,
            "corpToken": match.group("token"),
            "jobId": job_id,
            "error": "",
        })
        return result
    except Exception:
        return result


def bullhorn_job_url(url: str) -> str:
    """Return the canonical read-only URL for one Bullhorn published job.

    Args:
        url: Any URL accepted by :func:`bullhorn_job_identity`.

    Returns:
        str: HTTPS ``search/JobOrder`` URL scoped to the exact job id, or an
        empty string when the identity is invalid. Never raises.
    """
    try:
        identity = bullhorn_job_identity(url)
        if not identity.get("ok"):
            return ""
        query = urlencode({
            "query": f"(id:{identity['jobId']})",
            "fields": _JOB_FIELDS,
            "count": 1,
            "start": 0,
        })
        path = "/rest-services/{}/search/JobOrder".format(
            quote(identity["corpToken"], safe="-_"))
        return urlunsplit(("https", identity["host"], path, query, ""))
    except Exception:
        return ""


def bullhorn_apply_url(url: str) -> str:
    """Return the exact Bullhorn raw-application endpoint for a job.

    Args:
        url: Any URL accepted by :func:`bullhorn_job_identity`.

    Returns:
        str: HTTPS ``/apply/{jobId}/raw`` URL with no candidate parameters,
        or an empty string for invalid input. Never raises.
    """
    try:
        identity = bullhorn_job_identity(url)
        if not identity.get("ok"):
            return ""
        path = "/rest-services/{}/apply/{}/raw".format(
            quote(identity["corpToken"], safe="-_"), identity["jobId"])
        return urlunsplit(("https", identity["host"], path, "", ""))
    except Exception:
        return ""


def _read_json(response) -> dict:
    try:
        raw = response.read(_MAX_RESPONSE_BYTES + 1)
        if len(raw) > _MAX_RESPONSE_BYTES:
            return {}
        return json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return {}


def bullhorn_fetch_job(url: str, timeout_s: int = 15, _opener=None) -> dict:
    """Fetch and validate one currently published Bullhorn job.

    Args:
        url: Any URL accepted by :func:`bullhorn_job_identity`.
        timeout_s: Read-only HTTP timeout in seconds.
        _opener: Test hook compatible with ``urllib.request.urlopen``.

    Returns:
        dict: ``{ok, error, job, jobId, canonicalUrl, applyUrl}``. ``ok`` is
        true only when the returned id matches and the job is open, public,
        and not deleted. Never raises.
    """
    result = {"ok": False, "error": "bullhorn-job-url-invalid", "job": {},
              "jobId": "", "canonicalUrl": "", "applyUrl": ""}
    try:
        identity = bullhorn_job_identity(url)
        canonical = bullhorn_job_url(url)
        apply_url = bullhorn_apply_url(url)
        if not identity.get("ok") or not canonical or not apply_url:
            return result
        result.update({"jobId": identity["jobId"], "canonicalUrl": canonical,
                       "applyUrl": apply_url})
        request = urllib.request.Request(
            canonical,
            headers={"Accept": "application/json", "User-Agent": "Nori-AI/1.0"},
            method="GET",
        )
        opener = _opener or urllib.request.urlopen
        with opener(request, timeout=max(1, int(timeout_s))) as response:
            payload = _read_json(response)
        candidates = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(candidates, list):
            candidates = [payload] if isinstance(payload, dict) and payload.get("id") else []
        job = next((item for item in candidates if isinstance(item, dict)
                    and str(item.get("id") or "") == identity["jobId"]), None)
        if job is None:
            result["error"] = "bullhorn-job-not-found"
            return result
        result["job"] = job
        if job.get("isDeleted") is True or job.get("isOpen") in (False, 0, "0"):
            result["error"] = "bullhorn-job-closed"
            return result
        if job.get("isPublic") in (False, 0, "0"):
            result["error"] = "bullhorn-job-not-public"
            return result
        result.update({"ok": True, "error": ""})
        return result
    except urllib.error.HTTPError as exc:
        result["error"] = f"bullhorn-job-fetch-http-{int(exc.code)}"
        return result
    except Exception:
        result["error"] = "bullhorn-job-fetch-failed"
        return result


def bullhorn_submission_receipt(payload: dict, expected_job_id: str) -> dict:
    """Validate Bullhorn's structured candidate-application response.

    Args:
        payload: Parsed JSON returned by the public raw-apply endpoint.
        expected_job_id: Job id Nori explicitly approved.

    Returns:
        dict: Structured receipt with ``confirmed=True`` only when the
        submission, candidate, matching job, status, and successful resume
        parse are all present. Never raises.
    """
    receipt = {
        "confirmed": False,
        "ats": "bullhorn",
        "capturedAt": int(time.time() * 1000),
        "signals": [],
        "confirmationId": "",
        "jobId": str(expected_job_id or ""),
        "candidateId": "",
        "status": "",
        "resumeParsed": False,
        "candidateAlreadyExisted": False,
    }
    try:
        data = payload if isinstance(payload, dict) else {}
        submission = data.get("jobSubmission") if isinstance(data.get("jobSubmission"), dict) else {}
        job = data.get("jobOrder") if isinstance(data.get("jobOrder"), dict) else {}
        candidate = data.get("candidate") if isinstance(data.get("candidate"), dict) else {}
        submission_id = str(submission.get("id") or "")
        candidate_id = str(candidate.get("id") or "")
        returned_job_id = str(job.get("id") or "")
        status = str(submission.get("status") or "").strip()
        parsed = data.get("wasResumeParsedSuccessfully") is True
        receipt.update({
            "confirmationId": submission_id,
            "candidateId": candidate_id,
            "status": status,
            "resumeParsed": parsed,
            "candidateAlreadyExisted": data.get("candidateAlreadyExisted") is True,
        })
        if (submission_id.isdigit() and candidate_id.isdigit()
                and returned_job_id == str(expected_job_id or "")
                and bool(status) and parsed):
            receipt["signals"] = [
                {"kind": "jobSubmission.id", "value": submission_id},
                {"kind": "jobOrder.id", "value": returned_job_id},
                {"kind": "resumeParsed", "value": True},
            ]
            receipt["confirmed"] = True
        return receipt
    except Exception:
        return receipt


def bullhorn_submit_application(
        url: str, first_name: str, last_name: str, email: str,
        resume_path: str, phone: str = "", source: str = "Nori AI",
        timeout_s: int = 30, _opener=None) -> dict:
    """Submit an explicitly approved candidate application to Bullhorn.

    Args:
        url: Any URL accepted by :func:`bullhorn_job_identity`.
        first_name: Reviewed candidate first name.
        last_name: Reviewed candidate last name.
        email: Reviewed candidate email address.
        resume_path: Existing local PDF/DOC/DOCX/RTF/TXT resume, at most 5 MiB.
        phone: Optional reviewed phone number.
        source: Uniform integration source label; defaults to ``Nori AI``.
        timeout_s: POST timeout in seconds.
        _opener: Test hook compatible with ``urllib.request.urlopen``.

    Returns:
        dict: ``{ok, error, receipt, response}``. Success requires a strict
        structured Bullhorn receipt. Candidate data is sent only when this
        function is explicitly called by the guarded submit path. Never raises.
    """
    result = {"ok": False, "error": "bullhorn-application-invalid",
              "receipt": {}, "response": {}}
    try:
        identity = bullhorn_job_identity(url)
        endpoint = bullhorn_apply_url(url)
        values = {
            "firstName": str(first_name or "").strip(),
            "lastName": str(last_name or "").strip(),
            "email": str(email or "").strip(),
            "phone": str(phone or "").strip(),
            "source": str(source or "").strip(),
        }
        if (not identity.get("ok") or not endpoint
                or not values["firstName"] or not values["lastName"]
                or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", values["email"])):
            return result
        path = Path(str(resume_path or ""))
        extension = path.suffix.lower()
        if (not path.is_file() or extension not in _RESUME_EXTENSIONS
                or path.stat().st_size <= 0 or path.stat().st_size > _MAX_RESUME_BYTES):
            result["error"] = "bullhorn-resume-invalid"
            return result
        parameters = {
            "externalID": "Resume",
            "type": "Resume",
            "firstName": values["firstName"],
            "lastName": values["lastName"],
            "email": values["email"],
            "format": extension.lstrip("."),
        }
        if values["phone"]:
            parameters["phone"] = values["phone"]
        if values["source"]:
            parameters["source"] = values["source"]
        request_url = endpoint + "?" + urlencode(parameters)
        body = path.read_bytes()
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        request = urllib.request.Request(
            request_url,
            data=body,
            headers={"Accept": "application/json", "Content-Type": mime_type,
                     "User-Agent": "Nori-AI/1.0"},
            method="POST",
        )
        opener = _opener or urllib.request.urlopen
        with opener(request, timeout=max(1, int(timeout_s))) as response:
            payload = _read_json(response)
        receipt = bullhorn_submission_receipt(payload, identity["jobId"])
        result.update({"receipt": receipt, "response": payload})
        if receipt.get("confirmed"):
            result.update({"ok": True, "error": ""})
        else:
            result["error"] = "bullhorn-submission-not-confirmed"
        return result
    except urllib.error.HTTPError as exc:
        result["error"] = f"bullhorn-submit-http-{int(exc.code)}"
        return result
    except Exception:
        result["error"] = "bullhorn-submit-failed"
        return result
