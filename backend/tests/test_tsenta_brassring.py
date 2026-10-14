"""Tests for the dedicated BrassRing adapter helpers."""

from backend.src.tools.tsenta_brassring import (
    brassring_account_required,
    brassring_confirmation_receipt,
    brassring_job_closed,
    brassring_privacy_consent_required,
    brassring_url_candidates,
)


class _Node:
    def __init__(self, text="", visible=True):
        self._text = text
        self._visible = visible

    def inner_text(self, **_kwargs):
        return self._text

    def is_visible(self):
        return self._visible


class _Page:
    def __init__(self, body="", url=None, title="", selectors=None):
        self.url = url or ("https://sjobs.brassring.com/TGnewUI/Search/home/"
                           "HomeWithPreLoad?partnerid=1&siteid=2&"
                           "PageType=JobDetails&jobid=123")
        self.body = body
        self._title = title
        self.selectors = selectors or {}

    def query_selector(self, selector):
        if selector in self.selectors:
            return self.selectors[selector]
        for key, value in self.selectors.items():
            if key in selector:
                return value
        return None

    def locator(self, selector):
        assert selector == "body"
        return _Node(self.body)

    def title(self):
        return self._title

    def wait_for_load_state(self, *_args, **_kwargs):
        return None


def test_candidates_canonicalize_query_and_hash_job_details():
    candidates = brassring_url_candidates(
        "https://sjnub.brassring.com/TGnewUI/Search/home/HomeWithPreLoad?"
        "siteid=5010&partnerid=25037#jobDetails=852814_5010")
    assert candidates[0] == (
        "https://sjnub.brassring.com/TGnewUI/Search/home/HomeWithPreLoad?"
        "partnerid=25037&siteid=5010&PageType=JobDetails&jobid=852814")


def test_non_brassring_url_does_not_invent_a_route():
    assert brassring_url_candidates("https://example.com/jobs/123") == [
        "https://example.com/jobs/123"]


def test_closed_job_and_account_gate_detection():
    assert brassring_job_closed(_Page(
        body="The job posting you are looking for has expired or the position has already been filled."))
    assert not brassring_job_closed(_Page(body="Apply as External Applicant"))
    gated = _Page(title="Sign In", selectors={
        "#loginField": _Node(), "#password": _Node(),
    })
    assert brassring_account_required(gated) is True


def test_privacy_gate_requires_specific_control_or_copy():
    assert brassring_privacy_consent_required(_Page(selectors={
        "Agree to Privacy Policy": _Node(),
    })) is True
    assert brassring_privacy_consent_required(_Page(
        body="Privacy Policy. Note: You must AGREE to proceed. Agree Disagree")) is True
    assert brassring_privacy_consent_required(_Page(body="Privacy Policy")) is False


def test_receipt_rejects_bare_gratitude_without_confirmation_context():
    receipt = brassring_confirmation_receipt(
        _Page(body="Thank you for your application."), timeout_ms=1)
    assert receipt["confirmed"] is False


def test_receipt_accepts_confirmation_context_with_specific_text():
    page = _Page(
        url=("https://sjobs.brassring.com/TGnewUI/Search/home/"
             "HomeWithPreLoad#applicationConfirmation"),
        title="Application Confirmation",
        body="Your application has been submitted. Confirmation ID BR-55119.",
    )
    receipt = brassring_confirmation_receipt(page, timeout_ms=1)
    assert receipt["confirmed"] is True
    assert receipt["ats"] == "brassring"
    assert receipt["confirmationId"] == "BR-55119"
