"""Greenhouse reference-adapter tests."""

import json

from backend.src.tools.tsenta_apply import _save_browser_state
from backend.src.tools.tsenta_greenhouse import (
    greenhouse_confirmation_receipt, greenhouse_url_candidates,
)


def test_normalizes_modern_classic_and_embed_urls():
    candidates = greenhouse_url_candidates(
        "https://boards.greenhouse.io/embed/job_app?for=acme&token=12345")
    assert candidates[0].startswith("https://boards.greenhouse.io/embed/job_app")
    assert "https://job-boards.greenhouse.io/acme/jobs/12345" in candidates
    assert "https://boards.greenhouse.io/acme/jobs/12345" in candidates


def test_custom_gh_jid_url_is_preserved_without_inventing_board_token():
    url = "https://careers.acme.test/security?gh_jid=98765"
    assert greenhouse_url_candidates(url) == [url]


class _Body:
    def __init__(self, text):
        self.text = text

    def inner_text(self, timeout=None):
        return self.text


class _ReceiptPage:
    def __init__(self, text, selector=None):
        self.url = "https://job-boards.greenhouse.io/acme/confirmation"
        self.text = text
        self.selector = selector

    def wait_for_load_state(self, *args, **kwargs):
        return None

    def query_selector(self, selector):
        return _Body(self.text) if selector == self.selector else None

    def locator(self, selector):
        assert selector == "body"
        return _Body(self.text)


def test_receipt_requires_application_specific_evidence():
    bare = greenhouse_confirmation_receipt(_ReceiptPage("Thank you"), 100)
    assert bare["confirmed"] is False
    receipt = greenhouse_confirmation_receipt(_ReceiptPage(
        "Thank you for applying. Application confirmation ID: GH-12345"), 100)
    assert receipt["confirmed"] is True
    assert receipt["confirmationId"] == "GH-12345"
    assert receipt["signals"][0]["kind"] == "text"


def test_receipt_accepts_greenhouse_owned_success_surface():
    receipt = greenhouse_confirmation_receipt(_ReceiptPage(
        "Application complete", "#application_confirmation"), 100)
    assert receipt["confirmed"] is True
    assert receipt["signals"][0] == {
        "kind": "selector", "value": "#application_confirmation"}


def test_browser_storage_state_is_saved_atomically(tmp_path):
    target = tmp_path / "sessions" / "greenhouse.json"

    class Context:
        def storage_state(self, path):
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"cookies": [{"name": "session", "value": "local"}],
                           "origins": []}, handle)

    assert _save_browser_state(Context(), str(target)) is True
    assert json.loads(target.read_text(encoding="utf-8"))["cookies"][0]["name"] == "session"
    assert not (tmp_path / "sessions" / "greenhouse.json.tmp").exists()
