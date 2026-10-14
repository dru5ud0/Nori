"""Tests for Avature branded routing and guest/account checkpoints."""

from backend.src.tools.tsenta_avature import (
    AVATURE_ACCOUNT_SELECTOR,
    AVATURE_RESUME_METHOD_SELECTOR,
    avature_account_required,
    avature_confirmation_receipt,
    avature_job_closed,
    avature_url_candidates,
)
from backend.src.tools.tsenta_apply import _advance_form


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
        self.body = body
        self.url = url or "https://careers.example.com/en_US/careers/JobDetail/Role/42"
        self._title = title
        self.selectors = selectors or {}

    def locator(self, selector):
        assert selector == "body"
        return _Node(self.body)

    def query_selector(self, selector):
        return self.selectors.get(selector)

    def title(self):
        return self._title

    def wait_for_load_state(self, *_args, **_kwargs):
        return None


def test_branded_job_url_is_preserved_and_fragment_removed():
    url = "https://careers.example.com/en_US/careers/JobDetail/SOC-Analyst/42#apply"
    candidates = avature_url_candidates(url)
    assert candidates[0] == (
        "https://careers.example.com/en_US/careers/JobDetail/SOC-Analyst/42")


def test_unrelated_or_insecure_url_is_rejected():
    assert avature_url_candidates("https://example.com/about") == []
    assert avature_url_candidates(
        "http://careers.example.com/en_US/careers/JobDetail/Role/42") == []


def test_closed_job_message_is_detected():
    assert avature_job_closed(_Page(
        body="This requisition is no longer available.")) is True
    assert avature_job_closed(_Page(body="Apply")) is False


def test_login_only_page_requires_account():
    page = _Page(
        body="Already Registered? Username Password Log in Forgot your password?",
        selectors={AVATURE_ACCOUNT_SELECTOR: _Node()},
    )
    assert avature_account_required(page) is True


def test_resume_guest_method_wins_over_parallel_login_form():
    page = _Page(
        body="Already Registered? Username Password. Choose any option to apply.",
        selectors={
            AVATURE_ACCOUNT_SELECTOR: _Node(),
            AVATURE_RESUME_METHOD_SELECTOR + ", a[href*='/Register' i]": _Node(),
        },
    )
    assert avature_account_required(page) is False


def test_receipt_rejects_generic_gratitude_on_job_page():
    receipt = avature_confirmation_receipt(
        _Page(body="Thank you for your application."), timeout_ms=1)
    assert receipt["confirmed"] is False


def test_receipt_accepts_confirmation_context_and_specific_text():
    receipt = avature_confirmation_receipt(_Page(
        url="https://careers.example.com/careers/application-confirmation",
        title="Application Confirmation",
        body="Your application has been submitted. Confirmation ID AV-55119.",
    ), timeout_ms=1)
    assert receipt["confirmed"] is True
    assert receipt["ats"] == "avature"
    assert receipt["confirmationId"] == "AV-55119"


def test_advance_uses_visible_resume_continue_when_hidden_method_precedes_it():
    class _Button(_Node):
        def __init__(self, visible):
            super().__init__(visible=visible)
            self.clicked = False

        def click(self, **_kwargs):
            self.clicked = True

    class _Frame:
        def __init__(self):
            self.hidden = _Button(False)
            self.visible = _Button(True)

        def query_selector_all(self, _selector):
            return [self.hidden, self.visible]

        def wait_for_load_state(self, **_kwargs):
            return None

        def wait_for_timeout(self, _timeout):
            return None

    frame = _Frame()
    assert _advance_form(frame, "avature") is True
    assert frame.hidden.clicked is False
    assert frame.visible.clicked is True
