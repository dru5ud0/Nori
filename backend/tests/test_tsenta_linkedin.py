"""Unit tests for tsenta_linkedin — LinkedIn apply-URL resolution engine."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tools.tsenta_linkedin import (
    linkedin_decode_safety_go,
    linkedin_extract_job_id,
    linkedin_parse_flight,
    linkedin_resolve_apply_url,
    linkedin_resolve_from_url,
)

import json


class TestDecodeSafetyGo:
    def test_plain_company_url(self):
        url = "https://jobs.lever.co/acme/123"
        assert linkedin_decode_safety_go(url) == url

    def test_escaped_unicode_safety_go(self):
        url = (
            "https://www.linkedin.com/safety/go/"
            "?url=https\\u00253A\\u00252F\\u00252Fjobs.lever.co\\u00252Facme"
        )
        assert linkedin_decode_safety_go(url) == "https://jobs.lever.co/acme"

    def test_encoded_safety_go(self):
        url = (
            "https://www.linkedin.com/safety/go/"
            "?url=https%3A%2F%2Fboards.greenhouse.io%2Facme%2Fjobs%2F123"
        )
        assert linkedin_decode_safety_go(url) == (
            "https://boards.greenhouse.io/acme/jobs/123"
        )

    def test_nested_safety_go(self):
        inner = "https://www.linkedin.com/safety/go/?url=" + (
            "https%3A%2F%2Fjobs.smartrecruiters.com%2Facme%2Fjob%2F123"
        )
        outer = "https://www.linkedin.com/safety/go/?url=" + (
            "https%3A%2F%2Fwww.linkedin.com%2Fsafety%2Fgo%2F%3Furl%3D"
            + "https%253A%252F%252Fjobs.smartrecruiters.com%252Facme%252Fjob%252F123"
        )
        assert linkedin_decode_safety_go(outer) == "https://jobs.smartrecruiters.com/acme/job/123"
        assert linkedin_decode_safety_go(inner) == "https://jobs.smartrecruiters.com/acme/job/123"

    def test_internal_linkedin_target_is_none(self):
        url = "https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fwww.linkedin.com%2Fjobs%2Fview%2F123"
        assert linkedin_decode_safety_go(url) is None

    def test_plain_linkedin_url_is_none(self):
        assert linkedin_decode_safety_go("https://www.linkedin.com/jobs/view/123/") is None

    def test_malformed_input_returns_none(self):
        assert linkedin_decode_safety_go("") is None
        assert linkedin_decode_safety_go("not a url at all") is None

    def test_html_entities(self):
        url = (
            "https://www.linkedin.com/safety/go/"
            "?url=https%3A%2F%2Fjobs.workday.com%2Facme%2Fjob%2F123&amp;e=1"
        )
        assert linkedin_decode_safety_go(url) == "https://jobs.workday.com/acme/job/123"


class TestExtractJobId:
    def test_view_url(self):
        assert linkedin_extract_job_id("https://www.linkedin.com/jobs/view/1234567890/") == "1234567890"

    def test_slugged_view_url(self):
        assert (
            linkedin_extract_job_id(
                "https://in.linkedin.com/jobs/view/cyber-security-analyst-l3-at-wipro-4469719825"
            )
            == "4469719825"
        )

    def test_feed_url_current_job_id(self):
        url = "https://www.linkedin.com/jobs/search?currentJobId=98765&position=1"
        assert linkedin_extract_job_id(url) == "98765"

    def test_job_id_param(self):
        assert linkedin_extract_job_id("https://www.linkedin.com/jobs?jobId=555") == "555"

    def test_no_job_id(self):
        assert linkedin_extract_job_id("https://www.linkedin.com/feed/") == ""
        assert linkedin_extract_job_id("") == ""

    def test_non_numeric(self):
        assert linkedin_extract_job_id("https://www.linkedin.com/jobs/view/abc/") == ""


FLIGHT_TEMPLATE = (
    '{"data":{{"e":"JobCardFrameworkImplState_%s",'
    '"x":{"title":{"text":"%s"},"applyMethod":{"applyUrl":"%s"}}}}'
)


class TestParseFlight:
    def test_returns_single_entry(self):
        payload = FLIGHT_TEMPLATE % (
            "4100000001",
            "Senior Python Engineer",
            "https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fjobs.lever.co%2Facme%2Fdev%2Fxyz",
        )
        entries = linkedin_parse_flight(payload)
        assert len(entries) == 1
        assert entries[0]["jobId"] == "4100000001"
        assert entries[0]["url"] == "https://jobs.lever.co/acme/dev/xyz"
        assert entries[0]["title"] == "Senior Python Engineer"

    def test_nearest_marker_wins(self):
        payload = (
            FLIGHT_TEMPLATE % ("1000000001", "First Job",
                               "https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fa.example.com")
            + FLIGHT_TEMPLATE % ("1000000002", "Second Job",
                                 "https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fb.example.com")
        )
        entries = linkedin_parse_flight(payload)
        urls = [e["url"] for e in entries]
        assert urls == ["https://a.example.com", "https://b.example.com"]
        assert entries[1]["jobId"] == "1000000002"

    def test_internal_links_skipped(self):
        payload = FLIGHT_TEMPLATE % (
            "123",
            "Internal Role",
            "https://www.linkedin.com/jobs/view/123",
        )
        assert linkedin_parse_flight(payload) == []

    def test_too_short_text(self):
        assert linkedin_parse_flight("<html>hi</html>") == []
        assert linkedin_parse_flight("") == []

    def test_no_safety_go_marker(self):
        assert linkedin_parse_flight("x" * 500) == []

    def test_title_heuristic_rejects_garbage(self):
        payload = FLIGHT_TEMPLATE % (
            "123",
            "viewed",
            "https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fc.example.com",
        )
        entries = linkedin_parse_flight(payload)
        assert entries[0]["title"] == ""


class TestResolveFromUrl:
    def test_invalid_url_shape(self):
        result = json.loads(linkedin_resolve_from_url("https://www.linkedin.com/feed/"))
        assert result["ok"] is False
        assert result["error"] == "no-job-id"

    def test_invalid_job_id(self):
        result = json.loads(linkedin_resolve_apply_url("not-a-number"))
        assert result["ok"] is False
        assert result["error"] == "invalid-job-id"

    def test_network_failure_returns_error_json(self):
        result = json.loads(linkedin_resolve_apply_url("999999999999", timeout=2))
        assert result["ok"] is False
        assert result["url"] == ""
        assert result["error"]
