"""Tests for the dedicated Breezy HR adapter helpers."""

from backend.src.tools.tsenta_breezyhr import (
    breezyhr_apply_url,
    breezyhr_confirmation_receipt,
    breezyhr_job_closed,
    breezyhr_url_candidates,
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
    def __init__(self, url="https://rule4.breezy.hr/p/abc-role", body="", link=None,
                 confirmation=None):
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


def test_breezy_candidates_add_canonical_apply_url_and_remove_tracking():
    candidates = breezyhr_url_candidates(
        "https://rule4.breezy.hr/p/e77a31669a44-cybersecurity-engineer/?src=feed")
    assert candidates[-1] == (
        "https://rule4.breezy.hr/p/e77a31669a44-cybersecurity-engineer/apply")
    assert len(candidates) == len(set(candidates))


def test_non_breezy_candidates_do_not_invent_an_apply_path():
    candidates = breezyhr_url_candidates("https://careers.example.com/job/123")
    assert candidates == ["https://careers.example.com/job/123"]


def test_apply_url_accepts_only_https_breezy_owned_links():
    page = _Page(link=_Node(href="/p/abc-role/apply"))
    assert breezyhr_apply_url(page) == "https://rule4.breezy.hr/p/abc-role/apply"

    page.link = _Node(href="https://evil.example/apply")
    assert breezyhr_apply_url(page) == ""


def test_closed_job_message_is_detected():
    page = _Page(body="This position is no longer accepting applications.")
    assert breezyhr_job_closed(page) is True
    assert breezyhr_job_closed(_Page(body="Apply to this position")) is False


def test_bare_thank_you_is_not_a_submission_receipt():
    receipt = breezyhr_confirmation_receipt(_Page(body="Thank you."), timeout_ms=1)
    assert receipt["confirmed"] is False
    assert receipt["signals"] == []


def test_specific_confirmation_text_is_a_receipt_and_extracts_id():
    page = _Page(body=(
        "Your application has been submitted. "
        "Application number: BRZ-12345. We will be in touch."))
    receipt = breezyhr_confirmation_receipt(page, timeout_ms=1)
    assert receipt["confirmed"] is True
    assert receipt["ats"] == "breezyhr"
    assert receipt["confirmationId"] == "BRZ-12345"

