"""Tests for the dedicated Paylocity adapter helpers."""

from backend.src.tools.tsenta_paylocity import (
    paylocity_confirmation_receipt,
    paylocity_job_closed,
    paylocity_url_candidates,
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
    def __init__(self, body="", url=None, confirmation=None):
        self.url = url or "https://recruiting.paylocity.com/Recruiting/jobs/Apply/4402416"
        self.body = body
        self.confirmation = confirmation

    def query_selector(self, _selector):
        return self.confirmation

    def locator(self, selector):
        assert selector == "body"
        return _Node(self.body)

    def wait_for_load_state(self, *_args, **_kwargs):
        return None


def test_paylocity_candidates_put_direct_apply_route_first():
    candidates = paylocity_url_candidates(
        "https://recruiting.paylocity.com/recruiting/jobs/Details/4402416/Acme/Security-Engineer?source=feed")
    assert candidates[0] == (
        "https://recruiting.paylocity.com/Recruiting/jobs/Apply/4402416")


def test_non_paylocity_candidate_does_not_invent_route():
    url = "https://example.com/jobs/4402416"
    assert paylocity_url_candidates(url) == [url]


def test_closed_job_message_is_detected():
    assert paylocity_job_closed(_Page(
        body="This job is no longer accepting applications.")) is True
    assert paylocity_job_closed(_Page(body="Step 1 of 5")) is False


def test_receipt_rejects_gratitude_on_apply_route():
    receipt = paylocity_confirmation_receipt(
        _Page(body="Thank you for your application."), timeout_ms=1)
    assert receipt["confirmed"] is False


def test_receipt_accepts_confirmation_route_plus_specific_text():
    receipt = paylocity_confirmation_receipt(_Page(
        body="Your application has been submitted. Confirmation ID PCTY-55119.",
        url="https://recruiting.paylocity.com/Recruiting/jobs/Confirmation"),
        timeout_ms=1)
    assert receipt["confirmed"] is True
    assert receipt["ats"] == "paylocity"
    assert receipt["confirmationId"] == "PCTY-55119"


def test_receipt_accepts_paylocity_confirmation_element():
    receipt = paylocity_confirmation_receipt(
        _Page(body="", confirmation=_Node("Application submitted")), timeout_ms=1)
    assert receipt["confirmed"] is True
