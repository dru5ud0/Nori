"""Jobvite adapter tests."""

import json

from backend.src.tools.tsenta_apply import apply_job
from backend.src.tools.tsenta_jobvite import (
    jobvite_apply_url,
    jobvite_confirmation_receipt,
    jobvite_data_consent_required,
    jobvite_job_closed,
    jobvite_url_candidates,
)


class _Node:
    def __init__(self, text="", href=""):
        self.text = text
        self.href = href

    def get_attribute(self, name):
        return self.href if name == "href" else None

    def inner_text(self, timeout=None):
        return self.text

    def is_visible(self):
        return True


class _Page:
    def __init__(self, text="", *, consent=False, href="", receipt=None):
        self.url = "https://jobs.jobvite.com/ovt/job/oEazzfwG"
        self.text = text
        self.consent = consent
        self.href = href
        self.receipt = receipt

    def goto(self, url, **_kwargs):
        self.url = url
        return None

    def query_selector(self, selector):
        if "consentForm" in selector or "jv-country-select" in selector:
            return _Node() if self.consent else None
        if "href" in selector or "Apply" in selector:
            return _Node(href=self.href) if self.href else None
        if self.receipt and self.receipt in selector:
            return _Node("Your application has been submitted")
        return None

    def locator(self, selector):
        return _Node(self.text)

    def wait_for_selector(self, *_args, **_kwargs):
        raise RuntimeError("not-found")

    def wait_for_load_state(self, *_args, **_kwargs):
        return None

    def close(self):
        return None


def test_url_candidates_add_canonical_apply_route():
    url = "https://jobs.jobvite.com/ovt/job/oEazzfwG?source=feed"
    candidates = jobvite_url_candidates(url)
    assert candidates[0] == url
    assert "https://jobs.jobvite.com/ovt/job/oEazzfwG/apply" in candidates


def test_extracts_only_jobvite_owned_https_apply_url():
    page = _Page(href="/ovt/job/oEazzfwG/apply")
    assert jobvite_apply_url(page) == "https://jobs.jobvite.com/ovt/job/oEazzfwG/apply"
    page.href = "https://evil.example/apply"
    assert jobvite_apply_url(page) == ""


def test_detects_data_consent_and_closed_posting():
    assert jobvite_data_consent_required(_Page(consent=True)) is True
    assert jobvite_data_consent_required(_Page(
        "Data Consent Location of Residence and Language")) is True
    assert jobvite_job_closed(_Page("The job listing no longer exists")) is True


def test_consent_gate_is_an_explicit_dry_run_error():
    result = json.loads(apply_job(
        "https://jobs.jobvite.com/ovt/job/oEazzfwG/apply",
        {"personalInformation": {"firstName": "Fixture"}},
        dry_run=True,
        _page_provider=lambda: _Page(consent=True),
        timeout_ms=50,
    ))
    assert result["ok"] is False
    assert result["submitted"] is False
    assert result["error"] == "jobvite-data-consent-required"


def test_receipt_rejects_bare_thanks_and_accepts_specific_evidence():
    assert jobvite_confirmation_receipt(_Page("Thank you"), 50)["confirmed"] is False
    receipt = jobvite_confirmation_receipt(_Page(
        "Your application has been submitted. Confirmation ID JV-77889"), 50)
    assert receipt["confirmed"] is True
    assert receipt["confirmationId"] == "JV-77889"
