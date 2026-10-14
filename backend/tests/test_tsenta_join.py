"""Tests for JOIN routing and the safe email-authentication handoff."""

from playwright.sync_api import sync_playwright

from backend.src.tools.tsenta_apply import _advance_form, collect_fields, default_answerer
from backend.src.tools.tsenta_join import (
    join_application_surface_visible, join_confirmation_receipt,
    join_email_verification_required,
    join_job_closed, join_prepare_checkpoint, join_url_candidates,
)
from backend.src.tools.tsenta_profiles import empty_profile
from backend.src.tools.tsenta_trace import Trace


class _Node:
    def __init__(self, text="", visible=True):
        self._text = text
        self._visible = visible

    def inner_text(self, **_kwargs):
        return self._text

    def is_visible(self):
        return self._visible


class _Page:
    def __init__(self, body="", url=None, title="", email=None,
                 confirmation=None):
        self.body = body
        self.url = url or "https://join.com/companies/acme/123/role"
        self._title = title
        self.email = email
        self.confirmation = confirmation

    def locator(self, selector):
        assert selector == "body"
        return _Node(self.body)

    def query_selector(self, selector):
        if selector == "input#email[name='email']":
            return self.email
        return self.confirmation

    def title(self):
        return self._title

    def wait_for_load_state(self, *_args, **_kwargs):
        return None


def test_join_company_url_is_normalized_and_fragment_removed():
    url = "https://join.com/companies/acme/123-security-engineer?src=feed#apply"
    assert join_url_candidates(url) == [
        "https://join.com/companies/acme/123-security-engineer?src=feed"]


def test_unrelated_or_insecure_join_url_is_rejected():
    assert join_url_candidates("https://example.com/companies/acme/123") == []
    assert join_url_candidates("http://join.com/companies/acme/123") == []


def test_email_authentication_checkpoint_is_detected():
    page = _Page(
        url="https://join.com/companies/acme/123/apply/authentication",
        email=_Node())
    assert join_email_verification_required(page) is True
    assert _advance_form(page, "join") is False
    assert getattr(page, "_nori_advance_error") == (
        "join-email-verification-required")


def test_join_checkpoint_normalizes_email_without_clicking_continue():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.set_content("""
          <label for="email">Email</label>
          <input id="email" name="email" type="email">
          <button id="continue" type="button">Continue</button>
        """)
        assert join_prepare_checkpoint(page) == 1
        field = collect_fields(page)[0]
        assert field["field_id"] == "email"
        assert field["label"] == "Email"
        assert field["required"] is True
        assert page.locator("#continue").get_attribute("data-clicked") is None
        profile = empty_profile()
        profile["personalInformation"]["email"] = "jane@example.com"
        answer = default_answerer(field, profile, {}, Trace())
        assert answer["value"] == "jane@example.com"
        browser.close()


def test_hidden_preloaded_form_is_not_treated_as_an_open_application():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.set_content("""
          <input type="file" style="display:none">
          <input id="email" name="email" type="email" style="display:none">
        """)
        assert join_application_surface_visible(page) is False
        page.locator("#email").evaluate("el => el.style.display = 'block'")
        assert join_application_surface_visible(page) is True
        browser.close()


def test_closed_job_message_is_detected():
    assert join_job_closed(_Page(
        body="This job is no longer available. The deadline has passed."))
    assert not join_job_closed(_Page(body="Apply now"))


def test_join_receipt_rejects_generic_thanks_without_context():
    receipt = join_confirmation_receipt(
        _Page(body="Thank you for your application."), timeout_ms=1)
    assert receipt["confirmed"] is False


def test_join_receipt_accepts_confirmation_context_and_specific_text():
    receipt = join_confirmation_receipt(_Page(
        url="https://join.com/companies/acme/123/apply/confirmation",
        title="Application Confirmation",
        body="Your application has been submitted. Reference ID JN-44219.",
    ), timeout_ms=1)
    assert receipt["confirmed"] is True
    assert receipt["confirmationId"] == "JN-44219"
