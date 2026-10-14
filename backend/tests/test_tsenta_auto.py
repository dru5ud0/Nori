import os
import json
import pytest
from backend.src.tools.tsenta_auto import (
    score_job_match,
    rank_jobs,
    auto_apply_single_job,
    sweep_target_jobs,
)


def test_score_job_match_bangalore_iam():
    job = {
        "title": "Security Engineer - Identity and Access",
        "location": "Bangalore, India",
        "companyName": "Rubrik",
        "url": "https://example.com/job/1"
    }
    match = score_job_match(job)
    assert not match["disqualified"]
    assert match["region_tier"] == "bangalore"
    assert match["score"] >= 80.0
    assert any("identity" in k or "iam" in k or "access" in k for k in match["matched_keywords"])


def test_score_job_match_us_remote_analyst():
    job = {
        "title": "Security Analyst, Threat Operations",
        "location": "Remote - USA",
        "companyName": "GitLab",
        "url": "https://example.com/job/2"
    }
    match = score_job_match(job)
    assert not match["disqualified"]
    assert match["region_tier"] == "us_remote"
    assert match["score"] >= 60.0


def test_score_job_match_disqualify_director():
    job = {
        "title": "Director of Engineering, Security Factory",
        "location": "Remote - USA",
        "companyName": "GitLab",
        "url": "https://example.com/job/3"
    }
    match = score_job_match(job)
    assert match["disqualified"]
    assert "director" in match["disqualify_reason"].lower()


def test_score_job_match_disqualify_foreign_country():
    job = {
        "title": "Intermediate Security Engineer",
        "location": "Remote, Australia",
        "companyName": "GitLab",
        "url": "https://example.com/job/4"
    }
    match = score_job_match(job)
    assert match["disqualified"]
    assert "australia" in match["disqualify_reason"].lower()


def test_rank_jobs():
    jobs = [
        {
            "title": "Security Engineer - Identity and Access",
            "location": "Bangalore, India",
            "companyName": "Rubrik",
            "url": "https://example.com/job/1"
        },
        {
            "title": "Associate Operations Analyst",
            "location": "Bangalore, India",
            "companyName": "Zscaler",
            "url": "https://example.com/job/2"
        },
        {
            "title": "VP of Global Sales",
            "location": "Bangalore, India",
            "companyName": "Rubrik",
            "url": "https://example.com/job/3"
        }
    ]
    ranked = rank_jobs(jobs)
    assert len(ranked) == 2
    assert ranked[0]["title"] == "Security Engineer - Identity and Access"
    assert ranked[0]["match_score"] > ranked[1]["match_score"]


def test_sweep_target_jobs_mock(monkeypatch, tmp_path):
    store_file = str(tmp_path / "apps.json")
    
    jobs = [
        {
            "title": "Security Engineer - Identity and Access",
            "location": "Bangalore, India",
            "companyName": "Rubrik",
            "url": "https://example.com/job/1"
        }
    ]

    # Mock auto_apply_single_job to avoid real browser execution in unit test
    def mock_apply(job, store_path=None, profile_path=None, headless=True, dry_run=True, confirmed=False):
        return {
            "success": True,
            "job_id": "mock-123",
            "status": "review",
            "company": job["companyName"],
            "title": job["title"],
            "url": job["url"],
            "answered_count": 15,
            "missing_required_count": 0,
        }

    monkeypatch.setattr("backend.src.tools.tsenta_auto.auto_apply_single_job", mock_apply)

    res = sweep_target_jobs(jobs, max_applications=2, store_path=store_file)
    assert res["total_candidates"] == 1
    assert res["attempted"] == 1
    assert res["ready_for_review"] == 1
    assert res["failed"] == 0
