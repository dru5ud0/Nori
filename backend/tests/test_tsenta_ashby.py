"""Ashby reference-adapter tests."""

from backend.src.tools.tsenta_ashby import (
    ashby_confirmation_receipt,
    ashby_url_candidates,
)


def test_ashby_url_candidates_include_dedicated_application_route():
    original = "https://jobs.ashbyhq.com/acme/abc-123?utm_source=linkedin"
    candidates = ashby_url_candidates(original)
    assert candidates[0] == original
    assert "https://jobs.ashbyhq.com/acme/abc-123/application" in candidates
    assert "https://jobs.ashbyhq.com/acme/abc-123" in candidates


class _Body:
    def __init__(self, text):
        self.text = text

    def inner_text(self, timeout=None):
        return self.text

    def is_visible(self):
        return True


class _Page:
    def __init__(self, text, selector=None):
        self.url = "https://jobs.ashbyhq.com/acme/abc-123/application"
        self.text = text
        self.selector = selector

    def wait_for_load_state(self, *args, **kwargs):
        return None

    def query_selector(self, selector):
        return _Body(self.text) if selector == self.selector else None

    def locator(self, selector):
        assert selector == "body"
        return _Body(self.text)


def test_bare_thank_you_is_not_a_receipt():
    assert ashby_confirmation_receipt(_Page("Thank you"), 100)["confirmed"] is False


def test_specific_text_and_owned_surface_confirm():
    text_receipt = ashby_confirmation_receipt(
        _Page("Thank you for applying. Confirmation number ASH-77889"), 100)
    assert text_receipt["confirmed"] is True
    assert text_receipt["confirmationId"] == "ASH-77889"
    selector = "[data-testid='application-success']"
    selector_receipt = ashby_confirmation_receipt(
        _Page("Complete", selector=selector), 100)
    assert selector_receipt["confirmed"] is True
    assert selector_receipt["signals"][0]["value"] == selector
