"""Offline regression tests for Nori AI discovery, ranking, and review edits."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from backend.src.tools.nori_monitor import (
    append_monitor_alerts, append_monitor_run, load_monitor_settings, monitor_preview,
    save_monitor_settings, roll_daily_application_budget,
)
from backend.src.tools.tsenta_hiringcafe import _normalize_hit, rank_hiringcafe_jobs
from backend.src.tools.tsenta_apply import answer_fields
from backend.src.tools.tsenta_pipeline import (
    _answerer_with_overrides, save_answer_overrides, update_tracker_stage,
)
from backend.src.tools.nori_gmail import gmail_classify_message, gmail_load_inbox
from backend.src.tools.tsenta_trace import Trace


def _hit() -> dict:
    return {
        "objectID": "hc-1",
        "apply_url": "https://jobs.lever.co/acme/123?utm_source=hiringcafe",
        "source": "lever",
        "is_expired": False,
        "job_information": {"title": "Cybersecurity Analyst"},
        "v5_processed_job_data": {
            "company_name": "Acme",
            "formatted_workplace_location": "Chicago, Illinois, United States",
            "workplace_countries": ["US"],
            "workplace_type": "Hybrid",
            "yearly_min_compensation": 100000,
            "yearly_max_compensation": 125000,
            "listed_compensation_currency": "USD",
            "seniority_level": "Mid Level",
            "technical_tools": ["Splunk", "NIST"],
            "estimated_publish_date": "2026-09-05T00:00:00Z",
            "requirements_summary": "Triage security alerts in Splunk.",
        },
    }


def test_hiringcafe_job_normalizes_and_ranks_against_profile():
    job = _normalize_hit(_hit())
    assert job is not None
    assert job["atsType"] == "lever"
    assert job["url"] == "https://jobs.lever.co/acme/123"
    profile = {
        "personalInformation": {"title": "Cybersecurity Analyst", "city": "Chicago"},
        "skillCategories": [{"skills": ["Splunk", "NIST"]}],
    }
    ranked = rank_hiringcafe_jobs([job], profile, "Cybersecurity Analyst", "Chicago")
    assert ranked[0]["matchScore"] >= 60
    assert ranked[0]["matchReasons"]


def test_saved_feed_ats_is_refreshed_from_the_current_detector():
    stale = {
        "title": "SOC Analyst",
        "url": "https://myjobs.adp.com/acme/cx/job-details?reqId=500123",
        "atsType": "adprecruiting",
        "description": "Security operations",
    }

    ranked = rank_hiringcafe_jobs([stale], {}, "SOC Analyst")

    assert ranked[0]["atsType"] == "adp"


def test_answer_override_has_priority_and_persists(tmp_path):
    store = tmp_path / "applications.json"
    store.write_text(json.dumps({"applications": {"app_1": {
        "applicationId": "app_1",
        "status": "review",
        "updatedAt": 1,
        "trace": {"answers": [{"fieldId": "email", "source": "profile-direct",
                                  "value": "before@example.com"}]},
    }}}), encoding="utf-8")
    result = json.loads(save_answer_overrides(
        "app_1", {"email": "after@example.com", "missing": "ignored"}, str(store),
    ))
    assert result == {"ok": True, "applicationId": "app_1", "saved": 1, "error": None}
    wrapped = _answerer_with_overrides(
        lambda *_: {"value": "base", "source": "fallback"},
        {"email": "after@example.com"},
    )
    assert wrapped({"field_id": "email"}, {}, {}, None)["value"] == "after@example.com"
    trace = Trace("greenhouse")
    actions = answer_fields(
        [{"field_id": "email", "label": "Email", "kind": "email", "required": True}],
        {}, {}, trace, wrapped,
    )
    assert actions[0]["source"] == "user-override"
    assert trace.answers[0]["source"] == "user-override"
    saved = json.loads(store.read_text(encoding="utf-8"))["applications"]["app_1"]
    assert saved["trace"]["answers"][0]["source"] == "user-override"


def test_monitor_settings_are_local_and_secret_is_masked(tmp_path):
    path = tmp_path / "monitor.json"
    result = json.loads(save_monitor_settings({
        "enabled": True,
        "query": "GRC analyst",
        "telegramBotToken": "secret",
        "telegramChatId": "42",
    }, str(path)))
    assert result["ok"] is True
    public = load_monitor_settings(str(path))
    private = load_monitor_settings(str(path), include_secrets=True)
    assert public["telegramConfigured"] is True
    assert public["telegramBotToken"] == ""
    assert private["telegramBotToken"] == "secret"


def test_monitor_daily_budget_rolls_over_and_clamps(tmp_path):
    path = tmp_path / "monitor.json"
    save_monitor_settings({
        "dailyApplicationCap": 999,
        "dailyApplicationsUsed": 4,
        "dailyUsageDate": "2020-01-01",
    }, str(path))
    settings = load_monitor_settings(str(path), include_secrets=True)
    roll_daily_application_budget(settings)
    assert settings["dailyApplicationCap"] == 150
    assert settings["dailyApplicationsUsed"] == 0
    assert settings["dailyApplicationsRemaining"] == 150


def test_monitor_lanes_are_bounded_and_normalized(tmp_path):
    path = tmp_path / "monitor.json"
    lanes = [{"id": "security", "name": "Security", "query": "Cloud security",
              "location": "Chicago, IL", "minMatchQuality": "strong"}]
    saved = json.loads(save_monitor_settings({"lanes": lanes}, str(path)))
    assert saved["ok"] is True
    loaded = load_monitor_settings(str(path))
    assert loaded["lanes"][0]["query"] == "Cloud security"
    assert loaded["lanes"][0]["minMatchQuality"] == "strong"
    assert loaded["lanes"][0]["enabled"] is True


def test_monitor_run_history_is_bounded_normalized_and_secret_free(tmp_path):
    settings = load_monitor_settings(str(tmp_path / "missing.json"),
                                     include_secrets=True)
    settings["telegramBotToken"] = "must-not-appear"
    start = datetime(2026, 9, 6, 1, 0, tzinfo=timezone.utc)
    for index in range(55):
        append_monitor_run(settings, {
            "ok": True, "count": index, "newCount": 2,
            "notified": 1, "prepared": 1, "applied": 0,
            "needsReview": 1,
        }, start + timedelta(minutes=index),
           start + timedelta(minutes=index, seconds=4))
    assert len(settings["runHistory"]) == 50
    newest = settings["runHistory"][0]
    assert newest["found"] == 54
    assert newest["durationMs"] == 4000
    assert newest["status"] == "completed"
    assert "must-not-appear" not in json.dumps(settings["runHistory"])


def test_monitor_alerts_are_bounded_deduplicated_and_secret_free(tmp_path):
    settings = load_monitor_settings(str(tmp_path / "missing.json"),
                                     include_secrets=True)
    settings["telegramBotToken"] = "must-not-appear"
    jobs = [{
        "url": f"https://jobs.example/{index}",
        "title": f"Security Analyst {index}",
        "companyName": "Example",
        "location": "Remote",
        "matchScore": 80 + (index % 25),
        "description": "candidate profile data must not be copied",
    } for index in range(55)]
    append_monitor_alerts(
        settings, jobs,
        datetime(2026, 9, 7, 2, 0, tzinfo=timezone.utc),
        {"https://jobs.example/0"},
    )
    append_monitor_alerts(settings, [jobs[0]])

    assert len(settings["recentAlerts"]) == 50
    assert len({item["url"] for item in settings["recentAlerts"]}) == 50
    alert = next(item for item in settings["recentAlerts"]
                 if item["url"] == "https://jobs.example/0")
    assert alert["telegramNotified"] is True
    assert alert["matchScore"] == 80
    assert "description" not in alert
    assert "must-not-appear" not in json.dumps(settings["recentAlerts"])

    saved = json.loads(save_monitor_settings(settings, str(tmp_path / "monitor.json")))
    assert saved["ok"] is True
    assert len(saved["settings"]["recentAlerts"]) == 50


def test_monitor_preview_uses_saved_candidates_budget_and_measured_history():
    settings = {
        "intervalMinutes": 60,
        "dailyApplicationCap": 3,
        "minScore": 50,
        "minMatchQuality": "good",
        "lanes": [{"id": "one", "enabled": True, "query": "security",
                   "minScore": 60, "minMatchQuality": "strong"}],
        "runHistory": [
            {"status": "completed", "new": 2},
            {"status": "partial", "new": 4},
            {"status": "failed", "new": 100},
        ],
    }
    preview = monitor_preview(settings, [
        {"url": "https://jobs.example/a", "matchScore": 90},
        {"url": "https://jobs.example/b", "matchScore": 70},
        {"url": "https://jobs.example/c", "matchScore": 40},
    ], {"https://jobs.example/b"}, 7)
    assert preview["currentEligibleCandidates"] == 1
    assert preview["maximumPreparations"] == 21
    assert preview["recentRunsMeasured"] == 2
    assert preview["averageNewPerRun"] == 3
    assert preview["projectedPreparations"] == 21


def test_tracker_stage_is_persisted_without_changing_pipeline_status(tmp_path):
    store = tmp_path / "applications.json"
    store.write_text(json.dumps({"applications": {"app_1": {
        "applicationId": "app_1", "status": "applied", "updatedAt": 1,
    }}}), encoding="utf-8")
    result = json.loads(update_tracker_stage("app_1", "interviewing", str(store)))
    assert result["ok"] is True
    saved = json.loads(store.read_text(encoding="utf-8"))["applications"]["app_1"]
    assert saved["trackerStage"] == "interviewing"
    assert saved["status"] == "applied"
    assert json.loads(update_tracker_stage("app_1", "invalid", str(store)))["ok"] is False


def test_gmail_classifier_and_empty_local_inbox_are_offline(tmp_path):
    classified = json.loads(gmail_classify_message(
        "Interview availability", "Please schedule your interview", "recruiter@example.com",
    ))
    assert classified["category"] == "interview"
    inbox = json.loads(gmail_load_inbox(str(tmp_path / "inbox.json")))
    assert inbox == {"ok": True, "count": 0, "messages": [], "error": ""}
