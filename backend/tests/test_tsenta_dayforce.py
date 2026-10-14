"""Tests for the dedicated Dayforce adapter helpers."""

from backend.src.tools.tsenta_dayforce import (
    DAYFORCE_FORM_SELECTOR,
    dayforce_confirmation_receipt,
    dayforce_job_closed,
    dayforce_prepare_form,
    dayforce_privacy_consent_required,
    dayforce_url_candidates,
)


def test_form_selector_supports_current_compact_firstname_test_id():
    assert "test-id*='firstname'" in DAYFORCE_FORM_SELECTOR


def test_prepare_form_returns_tag_count_and_never_raises():
    class Page:
        def evaluate(self, script):
            assert "candidate.phone.country" in script
            assert "data-nori-ignore" in script
            return 8

    class BrokenPage:
        def evaluate(self, _script):
            raise RuntimeError("broken")

    assert dayforce_prepare_form(Page()) == 8
    assert dayforce_prepare_form(BrokenPage()) == 0


class _Node:
    def __init__(self, text="", visible=True):
        self._text = text
        self._visible = visible

    def inner_text(self, **_kwargs):
        return self._text

    def is_visible(self):
        return self._visible


class _Page:
    def __init__(self, body="", privacy=False, confirmation=None):
        self.url = "https://jobs.dayforcehcm.com/en-US/acme/CANDIDATEPORTAL/jobs/123"
        self.body = body
        self.privacy = privacy
        self.confirmation = confirmation

    def query_selector(self, selector):
        if "privacy" in selector.lower():
            return _Node() if self.privacy else None
        return self.confirmation

    def locator(self, selector):
        assert selector == "body"
        return _Node(self.body)

    def wait_for_load_state(self, *_args, **_kwargs):
        return None


def test_dayforce_candidates_include_guest_flow_route():
    candidates = dayforce_url_candidates(
        "https://jobs.dayforcehcm.com/en-US/acme/CANDIDATEPORTAL/jobs/123?source=feed")
    assert "https://jobs.dayforcehcm.com/en-US/acme/CANDIDATEPORTAL/jobs/123" in candidates
    assert ("https://jobs.dayforcehcm.com/en-US/acme/CANDIDATEPORTAL/jobs/123/"
            "apply?flowSelection=true") in candidates


def test_non_dayforce_candidate_does_not_invent_a_route():
    assert dayforce_url_candidates("https://example.com/jobs/123") == [
        "https://example.com/jobs/123"]


def test_privacy_gate_detects_selector_or_specific_copy():
    assert dayforce_privacy_consent_required(_Page(privacy=True)) is True
    assert dayforce_privacy_consent_required(_Page(body=(
        "Please review the policy below. By checking this box, you acknowledge "
        "and consent. I agree to the Privacy Statement."))) is True
    assert dayforce_privacy_consent_required(_Page(body="Apply without an Account")) is False


def test_closed_job_message_is_detected():
    assert dayforce_job_closed(_Page(
        body="This job posting is no longer available.")) is True
    assert dayforce_job_closed(_Page(body="Apply")) is False


def test_receipt_rejects_bare_thanks_and_accepts_specific_evidence():
    assert dayforce_confirmation_receipt(
        _Page(body="Thanks!"), timeout_ms=1)["confirmed"] is False
    receipt = dayforce_confirmation_receipt(_Page(
        body="Your application has been submitted. Confirmation ID DF-55119."),
        timeout_ms=1)
    assert receipt["confirmed"] is True
    assert receipt["ats"] == "dayforce"
    assert receipt["confirmationId"] == "DF-55119"
