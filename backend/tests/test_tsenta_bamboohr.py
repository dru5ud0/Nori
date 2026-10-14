"""BambooHR reference-adapter tests."""

from backend.src.tools.tsenta_bamboohr import (
    bamboohr_confirmation_receipt,
    bamboohr_job_closed,
    bamboohr_url_candidates,
)


def test_url_candidates_preserve_source_and_include_clean_posting():
    original = "https://acme.bamboohr.com/careers/179?source=linkedin"
    candidates = bamboohr_url_candidates(original)
    assert candidates[0] == original
    assert candidates[1] == "https://acme.bamboohr.com/careers/179"


class _Body:
    def __init__(self, text):
        self.text = text

    def inner_text(self, timeout=None):
        return self.text

    def is_visible(self):
        return True


class _Page:
    def __init__(self, text, selector=None):
        self.url = "https://acme.bamboohr.com/careers/179"
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
    assert bamboohr_confirmation_receipt(_Page("Thank you"), 100)["confirmed"] is False
    receipt = bamboohr_confirmation_receipt(_Page(
        "We have received your application. Reference number BAM-77889"), 100)
    assert receipt["confirmed"] is True
    assert receipt["confirmationId"] == "BAM-77889"


def test_receipt_accepts_owned_success_surface():
    selector = "[data-testid='application-success']"
    receipt = bamboohr_confirmation_receipt(_Page("Complete", selector=selector), 100)
    assert receipt["confirmed"] is True
    assert receipt["signals"][0]["value"] == selector


def test_closed_copy_is_rejected():
    assert bamboohr_job_closed(_Page("This job is no longer available")) is True
    assert bamboohr_job_closed(_Page("Security Engineer Apply for This Job")) is False
