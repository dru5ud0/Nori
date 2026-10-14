"""M5 tests: tsenta_pipeline.py — review gate + auto-submit state machine.

Covers: create_job (incl. PROFILE_INCOMPLETE gate), transitions
(queued -> review -> running -> applied|failed|paused), the review gate
(never submits without explicit confirmation), approve/reject/resume flows,
persistence roundtrip, and the jobs summary. All browser-free via FakePage.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "tools"))

import test_tsenta_apply as app_tests  # noqa: E402
from tsenta_config import default_config  # noqa: E402
from tsenta_profiles import empty_profile  # noqa: E402
from tsenta_pipeline import (  # noqa: E402
    create_job,
    job_report,
    job_status,
    jobs_summary,
    list_jobs,
    resolve_application_manually,
    set_job_archived,
    review_approve,
    review_reject,
    recover_interrupted_jobs,
    run_job,
    STATUS_APPLIED,
    STATUS_FAILED,
    STATUS_PAUSED,
    STATUS_QUEUED,
    STATUS_REVIEW,
    STATUS_RUNNING,
)


def _profile():
    profile = empty_profile()
    profile["resumeFormat"] = "pdf"
    profile["personalInformation"].update({
        "firstName": "Drupadh", "lastName": "Suresh", "email": "raven@example.com",
        "phone": "+15551234567", "address": "New York, NY, USA", "city": "New York",
        "state": "New York", "zipCode": "10001", "country": "United States",
    })
    profile["workAuthorization"] = {
        "needsSponsorship": False, "isAuthorizedToWork": True,
        "workAuthorizations": [], "citizenshipCountries": ["US"],
    }
    return profile


def _empty_profile():
    return empty_profile()


@pytest.fixture
def store(tmp_path):
    return str(tmp_path / "applications.json")


def _make_job(store):
    return json.loads(create_job("https://jobs.lever.co/company/role-123",
                                 _profile(), store_path=store))


def _reviewed_job(store):
    """Create + run a job so it lands at the review gate (dry-run, no submit)."""
    job = _make_job(store)
    run_job(job["applicationId"], _profile(), store_path=store,
            _page_provider=lambda: app_tests.FakePage(
                [app_tests.el_text_input("first_name")]))
    return job


class TestCreateJob:
    def test_creates_queued_job(self, store):
        result = _make_job(store)
        assert result["ok"] is True
        assert result["status"] == STATUS_QUEUED
        assert result["applicationId"].startswith("app_")

    def test_profile_incomplete_gate(self, store):
        result = json.loads(create_job("https://jobs.lever.co/company/role-123",
                                       _empty_profile(), store_path=store))
        assert result["ok"] is False
        assert result["error"] == "PROFILE_INCOMPLETE"
        assert isinstance(result["missingFields"], list)
        assert result["missingFields"]

    def test_invalid_profile_type(self, store):
        result = json.loads(create_job("https://x.com", None, store_path=store))
        assert result["ok"] is False
        assert result["error"] == "PROFILE_INCOMPLETE"

    def test_invalid_url(self, store):
        result = json.loads(create_job("", _profile(), store_path=store))
        assert result["ok"] is False
        assert result["error"] == "invalid-url"

    def test_never_raises(self, store):
        assert isinstance(create_job(None, None, store_path=store), str)

    def test_job_persisted(self, store):
        result = _make_job(store)
        assert os.path.exists(store)
        listing = json.loads(list_jobs(store))
        assert any(j["applicationId"] == result["applicationId"]
                   for j in listing["applications"])

    def test_company_branding_persisted(self, store):
        result = json.loads(create_job(
            "https://jobs.lever.co/acme/role-123", _profile(),
            company_name="Acme", company_domain="acme.com",
            logo_url="https://example.test/acme.png", job_title="Engineer",
            store_path=store))
        listing = json.loads(list_jobs(store))["applications"][0]
        assert listing["applicationId"] == result["applicationId"]
        assert listing["companyName"] == "Acme"
        assert listing["companyDomain"] == "acme.com"
        assert listing["logoUrl"] == "https://example.test/acme.png"


class TestRunJob:
    def test_unconfirmed_run_stops_at_review_never_submits(self, store):
        job = _make_job(store)
        result = json.loads(run_job(job["applicationId"], _profile(),
                                    store_path=store,
                                    _page_provider=lambda: app_tests.FakePage(
                                        [app_tests.el_text_input("first_name")])))
        assert result["ok"] is True
        assert result["status"] == STATUS_REVIEW
        assert result["submitted"] is False

    def test_status_history_tracks_pipeline(self, store):
        job = _make_job(store)
        run_job(job["applicationId"], _profile(), store_path=store,
                _page_provider=lambda: app_tests.FakePage(
                    [app_tests.el_text_input("first_name")]))
        status = json.loads(job_status(job["applicationId"], store))
        history = [h["status"] for h in status["statusHistory"]]
        assert history == [STATUS_QUEUED, STATUS_RUNNING, STATUS_REVIEW]

    def test_unknown_ats_fails(self, store):
        job = json.loads(create_job("https://www.google.com", _profile(),
                                    store_path=store))
        result = json.loads(run_job(job["applicationId"], _profile(),
                                    store_path=store,
                                    _page_provider=lambda: app_tests.FakePage([])))
        assert result["status"] == STATUS_REVIEW  # dry-run review, not failure
        status = json.loads(job_status(job["applicationId"], store))
        assert status["error"] == "ats-not-detected"

    def test_missing_job(self, store):
        result = json.loads(run_job("app_nope", _profile(), store_path=store))
        assert result["ok"] is False
        assert result["error"] == "job-not-found"

    def test_invalid_transition_from_applied(self, store):
        job = _make_job(store)
        result = json.loads(run_job(job["applicationId"], _profile(),
                                    store_path=store,
                                    _page_provider=lambda: app_tests.FakePage([])))
        # force the job to applied via the store
        data = json.loads(open(store, "r", encoding="utf-8").read())
        data["applications"][job["applicationId"]]["status"] = STATUS_APPLIED
        with open(store, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        result = json.loads(run_job(job["applicationId"], _profile(),
                                    store_path=store,
                                    _page_provider=lambda: app_tests.FakePage([])))
        assert result["error"] == "invalid-transition"

    def test_failed_application_can_retry_to_review(self, store):
        job = _make_job(store)
        data = json.loads(open(store, "r", encoding="utf-8").read())
        data["applications"][job["applicationId"]]["status"] = STATUS_FAILED
        data["applications"][job["applicationId"]]["error"] = "old-form-error"
        with open(store, "w", encoding="utf-8") as handle:
            json.dump(data, handle)

        result = json.loads(run_job(
            job["applicationId"], _profile(), store_path=store,
            _page_provider=lambda: app_tests.FakePage(
                [app_tests.el_text_input("first_name", required=True)]),
        ))

        assert result["ok"] is True
        assert result["status"] == STATUS_REVIEW
        report = json.loads(job_report(job["applicationId"], store))
        assert report["error"] is None
        assert [entry["status"] for entry in report["statusHistory"][-2:]] == [
            STATUS_RUNNING, STATUS_REVIEW,
        ]

    def test_confirmed_with_default_config_still_reviews(self, store):
        # autoSubmitApplication defaults False -> confirmed alone must NOT submit
        job = _make_job(store)
        result = json.loads(run_job(job["applicationId"], _profile(),
                                    confirmed=True, store_path=store,
                                    _page_provider=lambda: app_tests.FakePage(
                                        [app_tests.el_text_input("first_name")])))
        assert result["status"] == STATUS_REVIEW
        assert result["submitted"] is False


class TestReviewGate:
    def test_approve_runs_submit_and_applies(self, store):
        job = _reviewed_job(store)

        submit = app_tests.FakeElement(tag="button", attrs={"type": "submit"},
                                       visible=True)

        class PageWithConfirm(app_tests.FakePage):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.confirm_seen = False

            def wait_for_selector(self, selector, timeout=None):
                if "thank you" in selector.lower() or "submitted" in selector.lower():
                    self.confirm_seen = True
                    return True
                return super().wait_for_selector(selector, timeout)

            def query_selector(self, selector):
                if selector == ".application-confirmation":
                    self.confirm_seen = True
                    return app_tests.FakeElement(tag="div", text="Thank you for applying")
                return super().query_selector(selector)

        page = PageWithConfirm([app_tests.el_text_input("first_name"), submit])
        result = json.loads(review_approve(job["applicationId"], _profile(),
                                           store_path=store, _page_provider=lambda: page))
        assert result["ok"] is True
        assert result["status"] == STATUS_APPLIED
        assert result["submitted"] is True
        assert page.confirm_seen is True

    def test_approve_on_non_review_job_rejected(self, store):
        job = _make_job(store)
        result = json.loads(review_approve(job["applicationId"], _profile(),
                                           store_path=store))
        assert result["ok"] is False
        assert result["error"] == "invalid-transition"

    def test_reject_pauses(self, store):
        job = _reviewed_job(store)
        result = json.loads(review_reject(job["applicationId"], store))
        assert result["ok"] is True
        assert result["status"] == STATUS_PAUSED
        status = json.loads(job_status(job["applicationId"], store))
        assert status["statusHistory"][-1]["status"] == STATUS_PAUSED

    def test_reject_never_submits(self, store):
        job = _reviewed_job(store)
        review_reject(job["applicationId"], store)
        status = json.loads(job_status(job["applicationId"], store))
        assert status["submitted"] is False

    def test_approve_failure_marks_failed(self, store):
        job = json.loads(create_job("https://jobs.lever.co/company/role-123",
                                    _profile(), store_path=store))
        # drive it to review with an empty page (no fields to fill)
        run_job(job["applicationId"], _profile(), store_path=store,
                _page_provider=lambda: app_tests.FakePage([]))
        # approve with a page that has no submit control -> submit fails
        result = json.loads(review_approve(job["applicationId"], _profile(),
                                           store_path=store,
                                           _page_provider=lambda: app_tests.FakePage([])))
        assert result["ok"] is True
        assert result["status"] == STATUS_FAILED
        assert result["submitted"] is False

    def test_manual_applied_resolution_is_explicitly_a_user_confirmation(self, store):
        job = _reviewed_job(store)
        result = json.loads(resolve_application_manually(
            job["applicationId"], "applied", store))
        assert result["ok"] is True
        assert result["status"] == STATUS_APPLIED
        assert result["submitted"] is True

        report = json.loads(job_report(job["applicationId"], store))
        assert report["manualSubmissionConfirmed"] is True
        assert report["manualResolution"] == "applied"
        assert report["statusHistory"][-1]["reason"] == "user-confirmed-manual-submission"

    def test_failed_application_can_be_skipped_without_rerunning(self, store):
        job = _make_job(store)
        data = json.loads(open(store, "r", encoding="utf-8").read())
        data["applications"][job["applicationId"]]["status"] = STATUS_FAILED
        open(store, "w", encoding="utf-8").write(json.dumps(data))

        result = json.loads(resolve_application_manually(
            job["applicationId"], "skipped", store))
        assert result["ok"] is True
        assert result["status"] == STATUS_PAUSED
        assert result["submitted"] is False
        report = json.loads(job_report(job["applicationId"], store))
        assert report["statusHistory"][-1]["reason"] == "user-skipped"


class TestPersistence:
    def test_startup_recovers_interrupted_running_job_as_paused(self, store):
        job = _make_job(store)
        data = json.loads(open(store, "r", encoding="utf-8").read())
        data["applications"][job["applicationId"]]["status"] = STATUS_RUNNING
        with open(store, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        recovered = json.loads(recover_interrupted_jobs(store))
        assert recovered["ok"] is True
        assert recovered["recovered"] == 1
        status = json.loads(job_status(job["applicationId"], store))
        assert status["status"] == STATUS_PAUSED
        assert status["error"] == "interrupted-run-recovered"

    def test_list_jobs_sorted_newest_first(self, store):
        _make_job(store)
        _make_job(store)
        listing = json.loads(list_jobs(store))
        assert len(listing["applications"]) == 2
        timestamps = [j["createdAt"] for j in listing["applications"]]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_archive_is_reversible_and_excluded_from_active_counts(self, store):
        job = _make_job(store)
        archived = json.loads(set_job_archived(job["applicationId"], True, store))
        assert archived["ok"] is True
        assert archived["archived"] is True
        assert archived["archivedAt"]
        assert json.loads(list_jobs(store))["applications"] == []
        all_records = json.loads(list_jobs(store, include_archived=True))["applications"]
        assert all_records[0]["archived"] is True
        assert json.loads(jobs_summary(store))["counts"]["all"] == 0

        restored = json.loads(set_job_archived(job["applicationId"], False, store))
        assert restored["ok"] is True
        assert restored["archived"] is False
        report = json.loads(job_report(job["applicationId"], store))
        assert report["activityHistory"][-2]["event"] == "archived"
        assert report["activityHistory"][-1]["event"] == "restored"
        assert len(json.loads(list_jobs(store))["applications"]) == 1

    def test_archive_unknown_job_never_raises(self, store):
        result = json.loads(set_job_archived("missing", True, store))
        assert result["ok"] is False
        assert result["error"] == "job-not-found"

    def test_job_report_includes_trace(self, store):
        job = _reviewed_job(store)
        report = json.loads(job_report(job["applicationId"], store))
        assert report["applicationId"] == job["applicationId"]
        assert report["trace"]["meta"]["outcome"] == "dry-run"
        assert report["sources"] is not None

    def test_jobs_summary_counts(self, store):
        job1 = _reviewed_job(store)
        job2 = _make_job(store)
        summary = json.loads(jobs_summary(store))
        counts = summary["counts"]
        assert counts["all"] == 2
        assert counts["queued"] == 1
        assert counts["review"] == 1
        assert counts["submitted"] == 0
        assert counts["needs"] == 1
        assert counts["in_flight"] == 1  # queued, not running
        assert counts["applied"] == 0
        assert job2["applicationId"]

    def test_reload_roundtrip(self, store):
        job = _reviewed_job(store)
        data = json.loads(open(store, "r", encoding="utf-8").read())
        assert data["applications"][job["applicationId"]]["status"] == STATUS_REVIEW

    def test_run_generates_documents_on_job_record(self, store):
        job = _reviewed_job(store)
        report = json.loads(job_report(job["applicationId"], store))
        documents = report["documents"]
        assert documents["resume"]["status"] == "COMPLETED"
        assert documents["coverLetter"]["status"] == "COMPLETED"
        assert "Drupadh" in documents["coverLetter"]["coverLetterText"]
        assert "Drupadh" in documents["resume"]["resumeText"]

    def test_never_raises(self, store):
        assert isinstance(job_status("nope", store), str)
        assert isinstance(job_report("nope", store), str)
        assert isinstance(list_jobs(store), str)
        assert isinstance(jobs_summary(store), str)
        assert isinstance(review_reject("nope", store), str)
        assert isinstance(review_approve("nope", _profile(), store_path=store), str)


class TestStoreLock:
    def test_concurrent_create_job_loses_no_records(self, store):
        # Threads racing to create jobs: with the store lock every record
        # survives (read-modify-write is serialized).
        import threading

        results = []

        def worker():
            for _ in range(8):
                results.append(json.loads(create_job(
                    "https://jobs.lever.co/company/role-123",
                    _profile(), store_path=store))["applicationId"])

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(results) == 32
        assert len(json.loads(list_jobs(store))["applications"]) == 32

    def test_lock_blocks_second_holder(self, store):
        # While the lock is held, a second acquire must wait, then succeed
        # after release (mutual exclusion).
        import threading
        import time

        import tsenta_pipeline as pipe

        events = []

        def holder():
            with pipe._store_lock(store):
                events.append("acquired-1")
                time.sleep(0.2)
                events.append("released-1")

        def waiter():
            time.sleep(0.05)  # let the holder win first
            with pipe._store_lock(store):
                events.append("acquired-2")

        t1 = threading.Thread(target=holder)
        t2 = threading.Thread(target=waiter)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert events == ["acquired-1", "released-1", "acquired-2"]

    def test_lock_times_out(self, store):
        import threading
        import time

        import tsenta_pipeline as pipe

        got = {}
        locked = threading.Event()

        def holder():
            with pipe._store_lock(store):
                locked.set()
                time.sleep(0.3)

        def impatient():
            try:
                with pipe._store_lock(store, timeout_ms=50):
                    got["outcome"] = "acquired"
            except OSError as exc:
                got["outcome"] = str(exc)

        t1 = threading.Thread(target=holder)
        t2 = threading.Thread(target=impatient)
        t1.start()
        assert locked.wait(2)
        t2.start()
        t1.join()
        t2.join()
        assert got["outcome"] == "store-lock-timeout"
