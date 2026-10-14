"""M6 tests: tsenta_feed.py + tsenta_cli.py — job feed, sweep, quick-apply, CLI.

Feed fetching is tested with monkeypatched urllib (no network); sweep and
quick-apply run browser-free via FakePage. One live Greenhouse feed test is
gated behind LIVE=1.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import test_tsenta_apply as app_tests  # noqa: E402
from tsenta_cli import main, quick_apply, sweep_jobs  # noqa: E402
from tsenta_feed import (  # noqa: E402
    company_identity,
    fetch_feed,
    fetch_greenhouse_jobs,
    fetch_lever_jobs,
    jobs_to_urls,
    load_feed,
    load_urls,
    new_feed_jobs,
    save_feed,
)
from tsenta_profiles import empty_profile  # noqa: E402


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


def _fake_json_urlopen(monkeypatch, payload, raise_on=None):
    import urllib.request as ur

    class FakeResponse:
        def __init__(self, body):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return self._body

    calls = []

    def fake_urlopen(request, timeout=30):
        calls.append(request.full_url)
        if raise_on and raise_on in request.full_url:
            raise OSError("network error")
        return FakeResponse(json.dumps(payload).encode())

    monkeypatch.setattr(ur, "urlopen", fake_urlopen)
    return calls


class TestFeedFetch:
    def test_greenhouse_parse(self, monkeypatch):
        calls = _fake_json_urlopen(monkeypatch, {
            "jobs": [
                {"id": 8037057, "title": "Creative Producer",
                  "absolute_url": "https://boards.greenhouse.io/mozilla/jobs/8037057",
                  "company_name": "Mozilla", "location": {"name": "Europe"},
                  "updated_at": "2026-08-01T00:00:00Z"},
                {"id": 2, "title": "Engineer",
                 "absolute_url": "https://boards.greenhouse.io/mozilla/jobs/2",
                 "location": {"name": "US"}, "updated_at": ""},
            ]})
        jobs = fetch_greenhouse_jobs("mozilla")
        assert len(jobs) == 2
        assert jobs[0]["title"] == "Creative Producer"
        assert jobs[0]["url"].startswith("https://boards.greenhouse.io")
        assert jobs[0]["companyName"] == "Mozilla"
        assert jobs[0]["companyDomain"] == "mozilla.org"
        assert jobs[0]["logoUrl"].endswith("domain=mozilla.org&sz=128")
        assert any("mozilla" in c and "jobs" in c for c in calls)

    def test_greenhouse_network_error_returns_empty(self, monkeypatch):
        _fake_json_urlopen(monkeypatch, {}, raise_on="boards")
        assert fetch_greenhouse_jobs("mozilla") == []

    def test_greenhouse_garbage_returns_empty(self, monkeypatch):
        _fake_json_urlopen(monkeypatch, {"weird": True})
        assert fetch_greenhouse_jobs("mozilla") == []

    def test_lever_parse(self, monkeypatch):
        calls = _fake_json_urlopen(monkeypatch, [
            {"id": "abc", "text": "QA Engineer",
             "hostedUrl": "https://jobs.lever.co/acme/abc",
             "categories": {"location": "Remote"}, "createdAt": 1700000000000},
        ])
        jobs = fetch_lever_jobs("acme")
        assert jobs[0]["title"] == "QA Engineer"
        assert jobs[0]["location"] == "Remote"
        assert jobs[0]["companyName"] == "Acme"
        assert jobs[0]["companyDomain"] == "acme.com"
        assert any("lever.co/v0/postings" in c for c in calls)

    def test_fetch_feed_dispatch(self, monkeypatch):
        _fake_json_urlopen(monkeypatch, [{"id": "x", "text": "Role",
                                          "hostedUrl": "https://jobs.lever.co/a/x",
                                          "categories": {}, "createdAt": 0}])
        assert fetch_feed("lever:acme") != []
        assert fetch_feed("greenhouse:mo") == []  # no data -> empty payload path
        assert fetch_feed("bogus:x") == []

    def test_company_identity_recovers_ats_slug(self):
        identity = company_identity(url="https://job-boards.greenhouse.io/mozilla/jobs/1")
        assert identity["companyName"] == "Mozilla"
        assert identity["companyDomain"] == "mozilla.org"

    def test_fetch_feed_urls_source(self, tmp_path):
        path = tmp_path / "urls.txt"
        path.write_text("https://jobs.lever.co/company/role-123\n\nhttps://boards.greenhouse.io/mozilla/jobs/1\n", encoding="utf-8")
        feed = fetch_feed(f"urls:{path}")
        assert len(feed) == 2
        assert feed[0]["url"].startswith("https://jobs.lever.co")


class TestUrlLists:
    def test_load_urls_json(self, tmp_path):
        path = tmp_path / "urls.json"
        path.write_text(json.dumps(["https://a.com/1", "https://a.com/2"]), encoding="utf-8")
        urls = load_urls(str(path))
        assert len(urls) == 2

    def test_load_urls_text_with_comments(self, tmp_path):
        path = tmp_path / "urls.txt"
        path.write_text("# comment\nhttps://a.com/1\n\n", encoding="utf-8")
        urls = load_urls(str(path))
        assert len(urls) == 1
        assert urls[0]["url"] == "https://a.com/1"

    def test_jobs_to_urls_dedupes(self):
        jobs = [{"url": "https://a.com/1"}, {"url": "https://a.com/1"}, {"url": None}]
        assert jobs_to_urls(jobs) == ["https://a.com/1"]

    def test_load_urls_missing_file(self):
        assert load_urls("C:/definitely/not/here.txt") == []


class TestFeedStore:
    def test_save_load_roundtrip(self, tmp_path):
        path = str(tmp_path / "feed.json")
        result = json.loads(save_feed([{"id": 1, "title": "T", "url": "https://a.com",
                                        "location": "", "updated_at": ""}], path))
        assert result["ok"] is True
        assert result["count"] == 1
        assert load_feed(path)[0]["url"] == "https://a.com"

    def test_load_missing_returns_empty(self, tmp_path):
        assert load_feed(str(tmp_path / "nope.json")) == []

    def test_save_bad_feed(self, tmp_path):
        result = json.loads(save_feed("junk", str(tmp_path / "f.json")))
        assert result["ok"] is True
        assert result["count"] == 0


class TestNewFeedJobs:
    def test_dedupes_against_store(self, tmp_path):
        from tsenta_pipeline import create_job, run_job

        store = str(tmp_path / "apps.json")
        create_job("https://jobs.lever.co/company/role-123", _profile(),
                   store_path=store)
        feed = [
            {"id": 1, "title": "old", "url": "https://jobs.lever.co/company/role-123",
             "location": "", "updated_at": ""},
            {"id": 2, "title": "new", "url": "https://jobs.lever.co/company/role-999",
             "location": "", "updated_at": ""},
        ]
        fresh = new_feed_jobs(feed, store)
        assert [j["id"] for j in fresh] == [2]


class TestQuickApply:
    def test_unapproved_stops_at_review(self, tmp_path):
        store = str(tmp_path / "apps.json")
        result = json.loads(quick_apply(
            "https://jobs.lever.co/company/role-123", _profile(),
            store_path=store,
            _page_provider=lambda: app_tests.FakePage(
                [app_tests.el_text_input("first_name")])))
        assert result["status"] == "review"
        assert result["submitted"] is False

    def test_approved_submits(self, tmp_path):
        store = str(tmp_path / "apps.json")
        submit = app_tests.FakeElement(tag="button", attrs={"type": "submit"},
                                       visible=True)

        class PageWithConfirm(app_tests.FakePage):
            def wait_for_selector(self, selector, timeout=None):
                if "thank you" in selector.lower() or "submitted" in selector.lower():
                    return True
                return super().wait_for_selector(selector, timeout)

            def query_selector(self, selector):
                if selector == ".application-confirmation":
                    return app_tests.FakeElement(tag="div", text="Thank you for applying")
                return super().query_selector(selector)

        page = PageWithConfirm([app_tests.el_text_input("first_name"), submit])
        result = json.loads(quick_apply(
            "https://jobs.lever.co/company/role-123", _profile(),
            approve=True, store_path=store, _page_provider=lambda: page))
        assert result["status"] == "applied"
        assert result["submitted"] is True

    def test_invalid_profile_never_raises(self, tmp_path):
        store = str(tmp_path / "apps.json")
        result = json.loads(quick_apply("https://jobs.lever.co/company/role-123",
                                        {}, store_path=store))
        assert result["ok"] is False
        assert result["error"] == "PROFILE_INCOMPLETE"


class TestSweep:
    def test_sweep_skips_tracked_and_reviews_new(self, tmp_path):
        store = str(tmp_path / "apps.json")
        feed = [
            {"id": 1, "title": "a", "url": "https://jobs.lever.co/company/role-1",
             "location": "", "updated_at": ""},
            {"id": 2, "title": "b", "url": "https://jobs.lever.co/company/role-2",
             "location": "", "updated_at": ""},
        ]
        result = json.loads(sweep_jobs(feed, _profile(), store_path=store,
                                       _page_provider=lambda: app_tests.FakePage(
                                           [app_tests.el_text_input("first_name")])))
        assert result["ok"] is True
        assert result["new"] == 2
        assert result["reviewed"] == 2
        assert result["applied"] == 0

        # second sweep: both already tracked -> skipped
        result2 = json.loads(sweep_jobs(feed, _profile(), store_path=store,
                                        _page_provider=lambda: app_tests.FakePage(
                                            [app_tests.el_text_input("first_name")])))
        assert result2["new"] == 0
        assert result2["skipped"] == 2

    def test_sweep_limit(self, tmp_path):
        store = str(tmp_path / "apps.json")
        feed = [{"id": i, "title": "t", "url": f"https://jobs.lever.co/c/r{i}",
                 "location": "", "updated_at": ""} for i in range(5)]
        result = json.loads(sweep_jobs(feed, _profile(), limit=2, store_path=store,
                                       _page_provider=lambda: app_tests.FakePage(
                                           [app_tests.el_text_input("first_name")])))
        assert result["new"] == 2
        assert result["total"] == 2

    def test_sweep_from_file(self, tmp_path):
        store = str(tmp_path / "apps.json")
        feed_file = tmp_path / "feed.json"
        feed_file.write_text(json.dumps([
            {"id": 1, "title": "a", "url": "https://jobs.lever.co/company/role-1",
             "location": "", "updated_at": ""}]), encoding="utf-8")
        result = json.loads(sweep_jobs(str(feed_file), _profile(), store_path=store,
                                       _page_provider=lambda: app_tests.FakePage(
                                           [app_tests.el_text_input("first_name")])))
        assert result["new"] == 1

    def test_sweep_invalid_feed(self, tmp_path):
        result = json.loads(sweep_jobs("not-a-list", _profile(),
                                       store_path=str(tmp_path / "a.json")))
        assert result["ok"] is False
        assert result["error"] == "invalid-feed"

    def test_sweep_never_raises(self, tmp_path):
        assert isinstance(sweep_jobs(None, None, store_path=str(tmp_path / "a.json")), str)


class TestCliMain:
    def test_list_and_summary(self, tmp_path, capsys):
        store = str(tmp_path / "apps.json")
        assert main(["list", "--store", store]) == 0
        assert main(["summary", "--store", store]) == 0
        out = capsys.readouterr().out
        assert '"ok": true' in out

    def test_feed_quick_cmd_missing_profile(self, tmp_path, capsys):
        assert main(["quick", "https://jobs.lever.co/company/role-123",
                     "--profile", str(tmp_path / "nope.json")]) == 1
        out = capsys.readouterr().out
        assert "profile-not-found" in out

    def test_status_missing_job(self, tmp_path, capsys):
        assert main(["status", "app_nope", "--store", str(tmp_path / "a.json")]) == 1
        out = capsys.readouterr().out
        assert "job-not-found" in out

    def test_reject_missing_job(self, tmp_path):
        assert main(["reject", "app_nope", "--store", str(tmp_path / "a.json")]) == 1

    def test_unknown_command_fails(self):
        with pytest.raises(SystemExit):
            main(["bogus"])


@pytest.mark.live
class TestLiveFeed:
    def test_live_greenhouse_feed(self):
        if os.environ.get("LIVE") != "1":
            pytest.skip("live test: set LIVE=1")
        jobs = fetch_greenhouse_jobs("mozilla", limit=5)
        assert jobs
        assert jobs[0]["url"].startswith("https://")
        assert jobs[0]["title"]
