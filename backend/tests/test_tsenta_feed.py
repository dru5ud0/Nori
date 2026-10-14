"""Unit tests for tsenta_feed (M6)."""

import json
import os
from unittest.mock import patch

from backend.src.tools.tsenta_feed import (
    company_identity,
    default_feed_path,
    fetch_feed,
    fetch_greenhouse_jobs,
    fetch_lever_jobs,
    jobs_to_urls,
    load_feed,
    load_urls,
    new_feed_jobs,
    save_feed,
)


def test_company_identity():
    id1 = company_identity("Mozilla", "mozilla", "https://boards.greenhouse.io/mozilla/jobs/123")
    assert id1["companyName"] == "Mozilla"
    assert id1["companyDomain"] == "mozilla.org"
    assert "favicons" in id1["logoUrl"]

    id2 = company_identity("", "acme-corp", "")
    assert id2["companyName"] == "Acme Corp"
    assert id2["companyDomain"] == "acme-corp.com"

    id3 = company_identity("", "", "https://jobs.lever.co/stripe/abc-123")
    assert id3["companyName"] == "Stripe"
    assert id3["companyDomain"] == "stripe.com"


def test_fetch_greenhouse_jobs_mocked():
    sample_data = {
        "jobs": [
            {
                "id": 101,
                "title": "Software Engineer",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/101",
                "location": {"name": "Remote, US"},
                "updated_at": "2026-09-01T00:00:00Z",
                "company_name": "Acme Corp",
            },
            {
                "id": 102,
                "title": "Security Analyst",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/102",
                "location": {"name": "New York, NY"},
                "updated_at": "2026-09-02T00:00:00Z",
                "company_name": "Acme Corp",
            },
        ]
    }
    with patch("backend.src.tools.tsenta_feed._http_get_json", return_value=sample_data):
        jobs = fetch_greenhouse_jobs("acme", limit=1)
        assert len(jobs) == 1
        assert jobs[0]["id"] == 101
        assert jobs[0]["title"] == "Software Engineer"
        assert jobs[0]["companyName"] == "Acme Corp"


def test_fetch_lever_jobs_mocked():
    sample_data = [
        {
            "id": "lev-1",
            "text": "Frontend Developer",
            "hostedUrl": "https://jobs.lever.co/acme/lev-1",
            "categories": {"location": "San Francisco, CA"},
            "createdAt": 1787000000000,
        }
    ]
    with patch("backend.src.tools.tsenta_feed._http_get_json", return_value=sample_data):
        jobs = fetch_lever_jobs("acme")
        assert len(jobs) == 1
        assert jobs[0]["id"] == "lev-1"
        assert jobs[0]["title"] == "Frontend Developer"
        assert jobs[0]["location"] == "San Francisco, CA"


def test_fetch_feed_routing(tmp_path):
    txt_file = tmp_path / "urls.txt"
    txt_file.write_text("https://example.com/job/1\nhttps://example.com/job/2\n", encoding="utf-8")

    with patch("backend.src.tools.tsenta_feed.fetch_greenhouse_jobs", return_value=[{"id": 1}]) as mock_gh:
        res = fetch_feed("greenhouse:acme")
        assert res == [{"id": 1}]
        mock_gh.assert_called_once_with("acme", 100, 30.0)

    with patch("backend.src.tools.tsenta_feed.fetch_lever_jobs", return_value=[{"id": 2}]) as mock_lev:
        res = fetch_feed("lever:acme")
        assert res == [{"id": 2}]
        mock_lev.assert_called_once_with("acme", 100, 30.0)

    res_urls = fetch_feed(f"urls:{txt_file}")
    assert len(res_urls) == 2


def test_load_urls_text_and_json(tmp_path):
    txt_file = tmp_path / "urls.txt"
    txt_file.write_text(
        "# Comment line\n\nhttps://example.com/job/a\nhttps://example.com/job/b\n",
        encoding="utf-8",
    )
    entries_txt = load_urls(str(txt_file))
    assert len(entries_txt) == 2
    assert entries_txt[0]["url"] == "https://example.com/job/a"
    assert entries_txt[1]["url"] == "https://example.com/job/b"

    json_file = tmp_path / "urls.json"
    json_file.write_text(
        json.dumps(["https://example.com/job/1", "https://example.com/job/2"]),
        encoding="utf-8",
    )
    entries_json = load_urls(str(json_file))
    assert len(entries_json) == 2
    assert entries_json[0]["url"] == "https://example.com/job/1"


def test_jobs_to_urls():
    jobs = [
        {"url": "https://example.com/1"},
        {"url": "https://example.com/2"},
        {"url": "https://example.com/1"},
        {"url": "invalid"},
        {"foo": "bar"},
    ]
    urls = jobs_to_urls(jobs)
    assert urls == ["https://example.com/1", "https://example.com/2"]


def test_save_and_load_feed(tmp_path):
    target = str(tmp_path / "feed.json")
    data = [{"id": "j1", "title": "Dev", "url": "https://example.com/j1"}]
    res = json.loads(save_feed(data, target))
    assert res["ok"] is True
    assert res["count"] == 1

    loaded = load_feed(target)
    assert loaded == data


def test_new_feed_jobs_dedupes():
    with patch("backend.src.tools.tsenta_feed.list_jobs", return_value=json.dumps({
        "applications": [{"url": "https://example.com/already-applied"}]
    })):
        feed = [
            {"url": "https://example.com/already-applied"},
            {"url": "https://example.com/fresh-opportunity"},
        ]
        fresh = new_feed_jobs(feed)
        assert len(fresh) == 1
        assert fresh[0]["url"] == "https://example.com/fresh-opportunity"
