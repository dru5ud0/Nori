"""Unit tests for tsenta_cli (M6)."""

import json
from unittest.mock import patch, MagicMock

import pytest

from backend.src.tools.tsenta_cli import (
    main,
    quick_apply,
    sweep_jobs,
)


@pytest.fixture
def mock_profile():
    return {
        "personalInformation": {
            "firstName": "Alex",
            "lastName": "Taylor",
            "email": "alex@example.com",
            "phone": "555-123-4567",
            "address": "123 Main St",
        },
        "workAuthorization": {
            "isAuthorizedToWork": True,
            "needsSponsorship": False,
        },
    }


def test_quick_apply_stops_at_review(mock_profile):
    with patch("backend.src.tools.tsenta_cli.create_job", return_value=json.dumps({"ok": True, "applicationId": "app-123"})):
        with patch("backend.src.tools.tsenta_cli.run_job", return_value=json.dumps({
            "ok": True, "applicationId": "app-123", "status": "review", "submitted": False
        })) as mock_run:
            res_str = quick_apply("https://example.com/job", mock_profile, approve=False)
            res = json.loads(res_str)
            assert res["ok"] is True
            assert res["status"] == "review"
            assert res["submitted"] is False
            mock_run.assert_called_once()


def test_quick_apply_approves_when_requested(mock_profile):
    with patch("backend.src.tools.tsenta_cli.create_job", return_value=json.dumps({"ok": True, "applicationId": "app-123"})):
        with patch("backend.src.tools.tsenta_cli.run_job", return_value=json.dumps({
            "ok": True, "applicationId": "app-123", "status": "review", "submitted": False
        })):
            with patch("backend.src.tools.tsenta_cli.review_approve", return_value=json.dumps({
                "ok": True, "applicationId": "app-123", "status": "applied", "submitted": True
            })) as mock_app:
                res_str = quick_apply("https://example.com/job", mock_profile, approve=True)
                res = json.loads(res_str)
                assert res["ok"] is True
                assert res["status"] == "applied"
                assert res["submitted"] is True
                mock_app.assert_called_once()


def test_quick_apply_handles_create_failure(mock_profile):
    with patch("backend.src.tools.tsenta_cli.create_job", return_value=json.dumps({"ok": False, "error": "create-failed"})):
        res_str = quick_apply("https://example.com/job", mock_profile)
        res = json.loads(res_str)
        assert res["ok"] is False
        assert res["error"] == "create-failed"


def test_sweep_jobs_counts_and_limits(mock_profile):
    feed = [
        {"url": "https://example.com/1"},
        {"url": "https://example.com/2"},
        {"url": "https://example.com/3"},
    ]
    with patch("backend.src.tools.tsenta_cli.new_feed_jobs", return_value=feed):
        with patch("backend.src.tools.tsenta_cli.quick_apply", return_value=json.dumps({
            "ok": True, "applicationId": "app-test", "status": "review", "submitted": False
        })):
            res_str = sweep_jobs(feed, mock_profile, limit=2)
            res = json.loads(res_str)
            assert res["ok"] is True
            assert res["total"] == 2
            assert res["skipped"] == 1
            assert res["reviewed"] == 2
            assert len(res["results"]) == 2


def test_cli_main_feed(capsys):
    with patch("backend.src.tools.tsenta_cli.fetch_feed", return_value=[{"id": 1, "title": "Dev"}]):
        code = main(["feed", "greenhouse:test"])
        assert code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["ok"] is True
        assert data["count"] == 1


def test_cli_main_status(capsys):
    with patch("backend.src.tools.tsenta_cli.job_status", return_value=json.dumps({"ok": True, "status": "review"})):
        code = main(["status", "app-123"])
        assert code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["ok"] is True
        assert data["status"] == "review"


def test_cli_main_list(capsys):
    with patch("backend.src.tools.tsenta_cli.list_jobs", return_value=json.dumps({"ok": True, "applications": []})):
        code = main(["list"])
        assert code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["ok"] is True


def test_cli_main_summary(capsys):
    with patch("backend.src.tools.tsenta_cli.jobs_summary", return_value=json.dumps({"ok": True, "total": 5})):
        code = main(["summary"])
        assert code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["ok"] is True
        assert data["total"] == 5
