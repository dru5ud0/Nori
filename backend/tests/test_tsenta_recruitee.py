"""Tests for the dedicated Recruitee adapter helpers."""

from backend.src.tools.tsenta_recruitee import (
    recruitee_apply_url,
    recruitee_confirmation_receipt,
    recruitee_job_closed,
    recruitee_url_candidates,
)


class _Node:
    def __init__(self, text="", href="", visible=True):
        self._text = text
        self._href = href
        self._visible = visible

    def get_attribute(self, name):
        return self._href if name == "href" else None

    def inner_text(self):
        return self._text

    def is_visible(self):
        return self._visible


class _Locator:
    def __init__(self, text):
        self._text = text

    def inner_text(self, **_kwargs):
        return self._text


class _Page:
    def __init__(self, url="https://sequra.recruitee.com/o/security-engineer",
                 body="", link=None, confirmation=None):
        self.url = url
        self.body = body
        self.link = link
        self.confirmation = confirmation

    def query_selector(self, selector):
        if "href" in selector:
            return self.link
        return self.confirmation

    def locator(self, selector):
        assert selector == "body"
        return _Locator(self.body)

    def wait_for_load_state(self, *_args, **_kwargs):
        return None


def test_recruitee_candidates_add_documented_application_route():
    candidates = recruitee_url_candidates(
        "https://sequra.recruitee.com/o/security-engineer/?source=feed")
    assert candidates[-1] == (
        "https://sequra.recruitee.com/o/security-engineer/c/new")


def test_non_recruitee_candidate_does_not_invent_a_route():
    assert recruitee_url_candidates("https://example.com/o/security-engineer") == [
        "https://example.com/o/security-engineer"]


def test_apply_url_accepts_only_https_recruitee_owned_url():
    page = _Page(link=_Node(href="/o/security-engineer/c/new"))
    assert recruitee_apply_url(page) == (
        "https://sequra.recruitee.com/o/security-engineer/c/new")
    page.link = _Node(href="https://evil.example/o/security-engineer/c/new")
    assert recruitee_apply_url(page) == ""


def test_closed_job_message_is_detected():
    assert recruitee_job_closed(_Page(
        body="This job is no longer accepting applications.")) is True
    assert recruitee_job_closed(_Page(body="Send your application")) is False


def test_receipt_rejects_bare_thanks_and_accepts_specific_evidence():
    assert recruitee_confirmation_receipt(
        _Page(body="Thanks!"), timeout_ms=1)["confirmed"] is False
    receipt = recruitee_confirmation_receipt(_Page(
        body="Your application has been sent. Application number REC-88219."),
        timeout_ms=1)
    assert receipt["confirmed"] is True
    assert receipt["ats"] == "recruitee"
    assert receipt["confirmationId"] == "REC-88219"

