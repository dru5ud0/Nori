"""Lever reference-adapter tests."""

from backend.src.tools.tsenta_lever import (
    lever_confirmation_receipt, lever_url_candidates,
)


def test_normalizes_posting_and_apply_urls():
    candidates = lever_url_candidates(
        "https://jobs.lever.co/acme/abc-123?lever-source=LinkedIn")
    assert candidates[0].endswith("abc-123?lever-source=LinkedIn")
    assert "https://jobs.lever.co/acme/abc-123/apply" in candidates
    assert "https://jobs.lever.co/acme/abc-123" in candidates


def test_preserves_eu_lever_host():
    candidates = lever_url_candidates("https://jobs.eu.lever.co/acme/abc-123")
    assert "https://jobs.eu.lever.co/acme/abc-123/apply" in candidates


class _Body:
    def __init__(self, text):
        self.text = text

    def inner_text(self, timeout=None):
        return self.text


class _ReceiptPage:
    def __init__(self, text, selector=None):
        self.url = "https://jobs.lever.co/acme/abc-123/apply"
        self.text = text
        self.selector = selector

    def wait_for_load_state(self, *args, **kwargs):
        return None

    def query_selector(self, selector):
        return _Body(self.text) if selector == self.selector else None

    def locator(self, selector):
        return _Body(self.text)


def test_bare_thank_you_is_not_a_receipt():
    assert lever_confirmation_receipt(_ReceiptPage("Thank you"), 100)["confirmed"] is False


def test_specific_text_and_owned_selector_confirm():
    text_receipt = lever_confirmation_receipt(
        _ReceiptPage("Thank you for applying. Reference number LEV-77889"), 100)
    assert text_receipt["confirmed"] is True
    assert text_receipt["confirmationId"] == "LEV-77889"
    selector_receipt = lever_confirmation_receipt(
        _ReceiptPage("Complete", ".application-confirmation"), 100)
    assert selector_receipt["confirmed"] is True
    assert selector_receipt["signals"][0]["kind"] == "selector"
