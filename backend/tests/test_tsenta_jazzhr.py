"""JazzHR reference-adapter tests."""

from backend.src.tools.tsenta_jazzhr import (
    jazzhr_confirmation_receipt,
    jazzhr_url_candidates,
)


def test_url_candidates_preserve_application_and_remove_tracking_query():
    url = "https://acme.applytojob.com/apply/abc123/Security-Engineer?source=linkedin"
    candidates = jazzhr_url_candidates(url)
    assert candidates[0] == url
    assert candidates[1] == "https://acme.applytojob.com/apply/abc123/Security-Engineer"


class _Body:
    def __init__(self, text):
        self.text = text

    def inner_text(self, timeout=None):
        return self.text

    def is_visible(self):
        return True


class _Page:
    def __init__(self, text, selector=None):
        self.url = "https://acme.applytojob.com/apply/abc123/Security-Engineer"
        self.text = text
        self.selector = selector

    def wait_for_load_state(self, *args, **kwargs):
        return None

    def query_selector(self, selector):
        return _Body(self.text) if selector == self.selector else None

    def locator(self, selector):
        return _Body(self.text)


def test_receipt_rejects_bare_thank_you_and_accepts_specific_evidence():
    assert jazzhr_confirmation_receipt(_Page("Thank you"), 100)["confirmed"] is False
    receipt = jazzhr_confirmation_receipt(_Page(
        "Thank you for applying. Application ID JAZZ-77889"), 100)
    assert receipt["confirmed"] is True
    assert receipt["confirmationId"] == "JAZZ-77889"


def test_receipt_accepts_owned_success_surface():
    receipt = jazzhr_confirmation_receipt(
        _Page("Application complete", selector="#resumator-thank-you"), 100)
    assert receipt["confirmed"] is True
    assert receipt["signals"][0]["kind"] == "selector"
