"""Tests for the dedicated Teamtailor adapter helpers."""

from backend.src.tools.tsenta_teamtailor import (
    teamtailor_confirmation_receipt,
    teamtailor_job_closed,
    teamtailor_open_application,
)


class _Node:
    def __init__(self, text="", visible=True):
        self._text = text
        self._visible = visible
        self.clicked = False

    def inner_text(self, **_kwargs):
        return self._text

    def is_visible(self):
        return self._visible

    def click(self, **_kwargs):
        self.clicked = True


class _Page:
    def __init__(self, body="", form=None, button=None, confirmation=None):
        self.url = "https://company.teamtailor.com/jobs/123-security-engineer"
        self.body = body
        self.form = form
        self.button = button
        self.confirmation = confirmation
        self.waited = []

    def query_selector(self, selector):
        if selector == "#job-application-form":
            return self.form
        if "form-overlay" in selector or "Apply for this job" in selector:
            return self.button
        return self.confirmation

    def wait_for_selector(self, selector, **_kwargs):
        self.waited.append(selector)
        return self.form or _Node()

    def wait_for_load_state(self, *_args, **_kwargs):
        return None

    def locator(self, selector):
        assert selector == "body"
        return _Node(self.body)


def test_application_overlay_opens_without_touching_cookie_controls():
    button = _Node("Apply for this job")
    page = _Page(button=button)
    assert teamtailor_open_application(page, timeout_ms=50) is True
    assert button.clicked is True
    assert getattr(page, "_nori_scope_selector") == "#job-application-form"


def test_existing_visible_application_form_is_reused():
    page = _Page(form=_Node(visible=True))
    assert teamtailor_open_application(page, timeout_ms=50) is True
    assert getattr(page, "_nori_scope_selector") == "#job-application-form"


def test_closed_job_message_is_detected():
    assert teamtailor_job_closed(_Page(
        body="This job is no longer accepting applications.")) is True
    assert teamtailor_job_closed(_Page(body="Apply for this job")) is False


def test_receipt_rejects_bare_thanks_and_accepts_specific_evidence():
    assert teamtailor_confirmation_receipt(
        _Page(body="Thanks!"), timeout_ms=1)["confirmed"] is False
    receipt = teamtailor_confirmation_receipt(_Page(
        body="Your application has been submitted. Reference number TT-44991."),
        timeout_ms=1)
    assert receipt["confirmed"] is True
    assert receipt["ats"] == "teamtailor"
    assert receipt["confirmationId"] == "TT-44991"
