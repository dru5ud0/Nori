"""Rippling reference-adapter tests."""

from backend.src.tools.tsenta_rippling import (
    rippling_confirmation_receipt,
    rippling_url_candidates,
)


def test_url_candidates_include_dedicated_application_route():
    original = "https://ats.rippling.com/acme/jobs/abc-123"
    candidates = rippling_url_candidates(original)
    assert candidates[0] == original
    assert ("https://ats.rippling.com/acme/jobs/abc-123/apply?"
            "jobBoardSlug=acme&jobId=abc-123&step=application") in candidates


def test_localized_url_preserves_locale_in_apply_route():
    candidates = rippling_url_candidates(
        "https://ats.rippling.com/en-GB/acme/jobs/abc-123")
    assert any("/en-GB/acme/jobs/abc-123/apply?" in item for item in candidates)


class _Body:
    def __init__(self, text):
        self.text = text

    def inner_text(self, timeout=None):
        return self.text

    def is_visible(self):
        return True


class _Page:
    def __init__(self, text, selector=None, url=None):
        self.url = url or "https://ats.rippling.com/acme/jobs/abc/apply?step=application"
        self.text = text
        self.selector = selector

    def wait_for_load_state(self, *args, **kwargs):
        return None

    def query_selector(self, selector):
        return _Body(self.text) if selector == self.selector else None

    def locator(self, selector):
        assert selector == "body"
        return _Body(self.text)


def test_receipt_rejects_bare_thank_you_and_accepts_specific_evidence():
    assert rippling_confirmation_receipt(_Page("Thank you"), 100)["confirmed"] is False
    receipt = rippling_confirmation_receipt(_Page(
        "Thank you for applying. Application ID RIP-77889"), 100)
    assert receipt["confirmed"] is True
    assert receipt["confirmationId"] == "RIP-77889"


def test_receipt_accepts_confirmation_step_or_owned_surface():
    by_url = rippling_confirmation_receipt(_Page(
        "Complete", url="https://ats.rippling.com/acme/jobs/abc/apply?step=confirmation"), 100)
    assert by_url["confirmed"] is True
    assert by_url["signals"][0]["kind"] == "url"
    selector = "[data-testid='application-success']"
    by_surface = rippling_confirmation_receipt(_Page("Complete", selector=selector), 100)
    assert by_surface["confirmed"] is True
    assert by_surface["signals"][0]["value"] == selector
