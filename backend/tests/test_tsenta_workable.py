"""Workable reference-adapter tests."""

from backend.src.tools.tsenta_workable import (
    workable_confirmation_receipt,
    workable_job_closed,
    workable_url_candidates,
)


def test_url_candidates_include_dedicated_application_route():
    original = "https://apply.workable.com/acme/j/ABC123/?source=linkedin"
    candidates = workable_url_candidates(original)
    assert candidates[0] == original
    assert "https://apply.workable.com/acme/j/ABC123/apply/" in candidates
    assert "https://apply.workable.com/acme/j/ABC123/" in candidates


class _Body:
    def __init__(self, text):
        self.text = text

    def inner_text(self, timeout=None):
        return self.text

    def is_visible(self):
        return True


class _Page:
    def __init__(self, text, selector=None, url=None):
        self.url = url or "https://apply.workable.com/acme/j/ABC123/apply/"
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
    assert workable_confirmation_receipt(_Page("Thank you"), 100)["confirmed"] is False
    receipt = workable_confirmation_receipt(_Page(
        "Your application has been submitted. Confirmation ID WRK-77889"), 100)
    assert receipt["confirmed"] is True
    assert receipt["confirmationId"] == "WRK-77889"


def test_receipt_accepts_owned_success_url_or_surface():
    by_url = workable_confirmation_receipt(_Page(
        "Complete", url="https://apply.workable.com/acme/j/ABC123/apply/success/"), 100)
    assert by_url["confirmed"] is True
    assert by_url["signals"][0]["kind"] == "url"
    selector = "[data-testid='application-success']"
    by_surface = workable_confirmation_receipt(_Page("Complete", selector=selector), 100)
    assert by_surface["confirmed"] is True
    assert by_surface["signals"][0]["value"] == selector


def test_closed_page_detection_uses_url_or_explicit_copy():
    assert workable_job_closed(_Page(
        "No jobs here", url="https://apply.workable.com/acme/j/ABC/not_found")) is True
    assert workable_job_closed(_Page("This job is no longer available")) is True
    assert workable_job_closed(_Page("Staff Security Engineer application")) is False
