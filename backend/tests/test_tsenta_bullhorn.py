"""Tests for Bullhorn's API-first published-job application adapter."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

from backend.src.tools import tsenta_apply
from backend.src.tools.tsenta_apply import apply_job
from backend.src.tools.tsenta_bullhorn import (
    bullhorn_apply_url,
    bullhorn_fetch_job,
    bullhorn_job_identity,
    bullhorn_job_url,
    bullhorn_submission_receipt,
    bullhorn_submit_application,
)
from backend.src.tools.tsenta_profiles import empty_profile
from backend.src.tools import tsenta_documents


JOB_URL = (
    "https://public-rest40.bullhornstaffing.com/rest-services/R0SYP/query/"
    "JobBoardPost?fields=id,title&where=id%3D47951"
)


class _Response:
    def __init__(self, payload):
        self.raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, amount=-1):
        return self.raw if amount < 0 else self.raw[:amount]


def _profile():
    profile = empty_profile()
    profile["personalInformation"].update({
        "firstName": "Jane",
        "lastName": "Doe",
        "email": "jane.doe@example.test",
        "phone": "+15550101010",
    })
    return profile


def _open_job(job_id=47951, **overrides):
    job = {
        "id": job_id,
        "title": "Systems Administrator II / SOC Helpdesk",
        "isOpen": True,
        "isPublic": True,
        "isDeleted": False,
    }
    job.update(overrides)
    return {"data": [job], "count": 1}


def _preflight():
    return {
        "ok": True,
        "error": "",
        "jobId": "47951",
        "job": _open_job()["data"][0],
        "canonicalUrl": bullhorn_job_url(JOB_URL),
        "applyUrl": bullhorn_apply_url(JOB_URL),
    }


def test_bullhorn_identity_accepts_exact_public_rest_job_and_apply_urls():
    identity = bullhorn_job_identity(JOB_URL)
    assert identity == {
        "ok": True,
        "host": "public-rest40.bullhornstaffing.com",
        "corpToken": "R0SYP",
        "jobId": "47951",
        "error": "",
    }
    assert bullhorn_job_identity(
        "https://public-rest40.bullhornstaffing.com/rest-services/R0SYP/apply/47951/raw"
    )["jobId"] == "47951"


def test_bullhorn_identity_rejects_spoofed_insecure_or_unscoped_urls():
    assert bullhorn_job_identity(
        "https://public-rest40.bullhornstaffing.com.evil.test/"
        "rest-services/R0SYP/query/JobBoardPost?where=id%3D47951"
    )["ok"] is False
    assert bullhorn_job_identity(JOB_URL.replace("https://", "http://"))["ok"] is False
    assert bullhorn_job_identity(
        "https://public-rest40.bullhornstaffing.com/rest-services/R0SYP/search/JobOrder"
    )["ok"] is False


def test_bullhorn_urls_are_canonical_and_candidate_free():
    read_url = bullhorn_job_url(JOB_URL)
    apply_url = bullhorn_apply_url(JOB_URL)
    assert urlsplit(read_url).path.endswith("/rest-services/R0SYP/search/JobOrder")
    assert parse_qs(urlsplit(read_url).query)["query"] == ["(id:47951)"]
    assert parse_qs(urlsplit(read_url).query)["count"] == ["1"]
    assert apply_url == (
        "https://public-rest40.bullhornstaffing.com/"
        "rest-services/R0SYP/apply/47951/raw"
    )
    assert urlsplit(apply_url).query == ""


def test_bullhorn_fetch_job_is_read_only_and_validates_public_open_state():
    captured = {}

    def opener(request, timeout):
        captured.update({"method": request.get_method(), "url": request.full_url,
                         "timeout": timeout, "body": request.data})
        return _Response(_open_job())

    result = bullhorn_fetch_job(JOB_URL, _opener=opener)
    assert result["ok"] is True
    assert result["jobId"] == "47951"
    assert captured["method"] == "GET"
    assert captured["body"] is None
    assert "firstName" not in captured["url"]


def test_bullhorn_fetch_job_rejects_closed_private_and_mismatched_jobs():
    closed = bullhorn_fetch_job(
        JOB_URL, _opener=lambda *_args, **_kwargs: _Response(
            _open_job(isOpen=False)))
    private = bullhorn_fetch_job(
        JOB_URL, _opener=lambda *_args, **_kwargs: _Response(
            _open_job(isPublic=False)))
    mismatch = bullhorn_fetch_job(
        JOB_URL, _opener=lambda *_args, **_kwargs: _Response(_open_job(999)))
    assert closed["error"] == "bullhorn-job-closed"
    assert private["error"] == "bullhorn-job-not-public"
    assert mismatch["error"] == "bullhorn-job-not-found"


def test_document_context_uses_bullhorn_job_metadata(monkeypatch):
    job = _open_job()["data"][0]
    job.update({
        "address": {"city": "Chicago", "state": "IL", "countryName": "US"},
        "publicDescription": "<p>Monitor <strong>SOC</strong> alerts.</p>",
    })
    monkeypatch.setattr(
        tsenta_documents, "bullhorn_fetch_job",
        lambda *_a, **_k: {"ok": True, "job": job},
    )
    context = tsenta_documents.fetch_job_context(JOB_URL)
    assert context == {
        "title": "Systems Administrator II / SOC Helpdesk",
        "company": "",
        "location": "Chicago, IL, US",
        "description": "Monitor SOC alerts.",
        "source": "bullhorn-public-rest",
    }


def test_bullhorn_receipt_requires_matching_ids_status_candidate_and_resume_parse():
    payload = {
        "candidateAlreadyExisted": False,
        "wasResumeParsedSuccessfully": True,
        "jobSubmission": {"id": 280, "status": "New Lead"},
        "jobOrder": {"id": 47951, "title": "SOC Helpdesk"},
        "candidate": {"id": 10617, "firstName": "Jane"},
    }
    receipt = bullhorn_submission_receipt(payload, "47951")
    assert receipt["confirmed"] is True
    assert receipt["confirmationId"] == "280"
    assert bullhorn_submission_receipt(
        {**payload, "wasResumeParsedSuccessfully": False}, "47951"
    )["confirmed"] is False
    assert bullhorn_submission_receipt(payload, "999")["confirmed"] is False


def test_bullhorn_submit_uses_raw_resume_body_and_documented_parameters(tmp_path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4 synthetic-test-resume")
    captured = {}
    response = {
        "candidateAlreadyExisted": True,
        "wasResumeParsedSuccessfully": True,
        "jobSubmission": {"id": 281, "status": "New Lead"},
        "jobOrder": {"id": 47951, "title": "SOC Helpdesk"},
        "candidate": {"id": 10618, "email": "jane.doe@example.test"},
    }

    def opener(request, timeout):
        captured.update({"method": request.get_method(), "url": request.full_url,
                         "body": request.data, "timeout": timeout})
        return _Response(response)

    result = bullhorn_submit_application(
        JOB_URL, "Jane", "Doe", "jane.doe@example.test", str(resume),
        phone="+15550101010", _opener=opener)
    query = parse_qs(urlsplit(captured["url"]).query)
    assert result["ok"] is True
    assert captured["method"] == "POST"
    assert captured["body"] == resume.read_bytes()
    assert query["firstName"] == ["Jane"]
    assert query["lastName"] == ["Doe"]
    assert query["email"] == ["jane.doe@example.test"]
    assert query["phone"] == ["+15550101010"]
    assert query["source"] == ["Nori AI"]
    assert query["format"] == ["pdf"]


def test_bullhorn_submit_rejects_missing_resume_before_any_network_call():
    called = False

    def opener(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("network must not be called")

    result = bullhorn_submit_application(
        JOB_URL, "Jane", "Doe", "jane.doe@example.test", "missing.pdf",
        _opener=opener)
    assert result["error"] == "bullhorn-resume-invalid"
    assert called is False


def test_apply_job_bullhorn_dry_run_prepares_review_without_transmitting(monkeypatch,
                                                                         tmp_path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4 synthetic-test-resume")
    monkeypatch.setattr(tsenta_apply, "bullhorn_fetch_job", lambda *_a, **_k: _preflight())
    monkeypatch.setattr(
        tsenta_apply, "bullhorn_submit_application",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not submit")),
    )
    result = json.loads(apply_job(
        JOB_URL, _profile(), dry_run=True, confirmed=False, resume_path=str(resume)))
    assert result["ok"] is True
    assert result["ats"] == "bullhorn"
    assert result["submitted"] is False
    assert result["answers_summary"]["transport"] == "bullhorn-public-rest"
    assert result["answers_summary"]["uploaded"] == 0
    assert result["answers_summary"]["prepared_documents"][0]["verified"] is True
    assert result["answers_summary"]["submission_blockers"] == []
    assert result["trace"]["meta"]["outcome"] == "dry-run"
    assert result["sources"]["profile-direct"] == 5


def test_apply_job_bullhorn_unconfirmed_real_request_is_forced_to_dry_run(monkeypatch,
                                                                           tmp_path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4 synthetic-test-resume")
    monkeypatch.setattr(tsenta_apply, "bullhorn_fetch_job", lambda *_a, **_k: _preflight())
    monkeypatch.setattr(
        tsenta_apply, "bullhorn_submit_application",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not submit")),
    )
    result = json.loads(apply_job(
        JOB_URL, _profile(), dry_run=False, confirmed=False, resume_path=str(resume)))
    assert result["dry_run"] is True
    assert result["submitted"] is False


def test_apply_job_bullhorn_explicit_confirmation_uses_reviewed_values(monkeypatch,
                                                                        tmp_path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4 synthetic-test-resume")
    captured = {}
    monkeypatch.setattr(tsenta_apply, "bullhorn_fetch_job", lambda *_a, **_k: _preflight())

    def submit(_url, first_name, last_name, email, _resume_path, **kwargs):
        captured.update({"first": first_name, "last": last_name, "email": email,
                         "phone": kwargs.get("phone")})
        return {"ok": True, "error": "", "receipt": {
            "confirmed": True, "ats": "bullhorn", "confirmationId": "281",
        }}

    monkeypatch.setattr(tsenta_apply, "bullhorn_submit_application", submit)
    result = json.loads(apply_job(
        JOB_URL, _profile(), dry_run=False, confirmed=True, resume_path=str(resume),
        answerer=lambda field, *_a: ({
            "value": "Reviewed Jane" if field["field_id"] == "firstName" else
                     tsenta_apply.profile_get(_profile(),
                         "personalInformation." + field["field_id"]),
            "source": "user-override",
            "display": "reviewed",
        })))
    assert result["submitted"] is True
    assert result["submission_receipt"]["confirmationId"] == "281"
    assert captured["first"] == "Reviewed Jane"
    assert captured["last"] == "Doe"
    assert captured["email"] == "jane.doe@example.test"


def test_apply_job_bullhorn_missing_resume_is_a_review_blocker(monkeypatch):
    monkeypatch.setattr(tsenta_apply, "bullhorn_fetch_job", lambda *_a, **_k: _preflight())
    result = json.loads(apply_job(JOB_URL, _profile(), dry_run=True))
    assert result["ok"] is True
    assert result["submitted"] is False
    assert result["answers_summary"]["missing_uploads"] == ["resume"]
    assert result["answers_summary"]["submission_blockers"] == ["resume"]
