"""Tests for Pinpoint public application routing and safe preparation."""

from playwright.sync_api import sync_playwright

from backend.src.tools.tsenta_apply import _click_custom_option, collect_fields
from backend.src.tools.tsenta_pinpoint import (
    pinpoint_confirmation_receipt,
    pinpoint_job_closed,
    pinpoint_prepare_form,
    pinpoint_reject_optional_cookies,
    pinpoint_url_candidates,
)


class _Node:
    def __init__(self, text="", visible=True):
        self._text = text
        self._visible = visible
        self.clicked = False

    def inner_text(self, **_kwargs):
        return self._text

    def is_visible(self):
        return self._visible

    def click(self, **_kwargs):
        self.clicked = True


class _Page:
    def __init__(self, body="", url=None, title="", buttons=None,
                 confirmation=None):
        self.body = body
        self.url = url or "https://tenant.pinpointhq.com/en/postings/role-id"
        self._title = title
        self.buttons = buttons or []
        self.confirmation = confirmation

    def locator(self, selector):
        assert selector == "body"
        return _Node(self.body)

    def query_selector_all(self, selector):
        assert selector == "button"
        return self.buttons

    def query_selector(self, _selector):
        return self.confirmation

    def title(self):
        return self._title

    def wait_for_load_state(self, *_args, **_kwargs):
        return None


def test_posting_routes_to_public_application_and_drops_tracking_fragment():
    candidates = pinpoint_url_candidates(
        "https://tenant.pinpointhq.com/en/postings/role-id?source=feed#apply")
    assert candidates[0] == (
        "https://tenant.pinpointhq.com/en/postings/role-id/applications/new")


def test_existing_application_url_is_preserved():
    url = "https://tenant.pinpointhq.com/en/postings/role-id/applications/new"
    assert pinpoint_url_candidates(url)[0] == url


def test_unrelated_or_insecure_url_is_rejected():
    assert pinpoint_url_candidates("https://example.com/en/postings/role") == []
    assert pinpoint_url_candidates(
        "http://tenant.pinpointhq.com/en/postings/role") == []


def test_cookie_helper_rejects_and_never_accepts_all():
    accept = _Node("Accept all")
    reject = _Node("Reject all")
    assert pinpoint_reject_optional_cookies(
        _Page(buttons=[accept, reject])) is True
    assert reject.clicked is True
    assert accept.clicked is False


def test_pinpoint_markup_is_normalized_for_generic_collector():
    html = """<form action="/en/postings/role/applications">
      <div class="col-1-1"><label class="external-form__label--required">Country</label>
        <input id="application_form[application][country]" class="react-select__input" role="combobox"></div>
      <div class="col-1-1"><label class="external-form__label--required">City</label>
        <input id="address2"></div>
      <div class="pad-v-3"><label><span class="external-form__label--title external-form__label--required">Are you legally authorized to work in the United States?</span></label>
        <input id="auth-yes" type="radio" name="application_form[application][answers_attributes][0][boolean_answer]" value="true"><label for="auth-yes">Yes</label>
        <input id="auth-no" type="radio" name="application_form[application][answers_attributes][0][boolean_answer]" value="false"><label for="auth-no">No</label>
      </div>
    </form>"""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.set_content(html)
        assert pinpoint_prepare_form(page) == 4
        fields = {item["field_id"]: item for item in collect_fields(page)}
        assert fields["personalInformation.country"]["label"] == "Country"
        assert fields["personalInformation.country"]["required"] is True
        assert page.locator(
            '[data-nori-field="personalInformation.country"]'
        ).get_attribute("data-nori-lazy-options") == "true"
        assert fields["personalInformation.city"]["label"] == "City"
        radio = fields[
            "application_form[application][answers_attributes][0][boolean_answer]"]
        assert radio["label"] == "Are you legally authorized to work in the United States?"
        assert radio["required"] is True
        assert radio["options"] == [
            {"label": "Yes", "value": "true"},
            {"label": "No", "value": "false"},
        ]
        browser.close()


def test_state_code_matches_full_react_select_option():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.set_content("""
          <div class="react-select__control">
            <input id="state" class="react-select__input" role="combobox"
              aria-owns="state-listbox">
          </div>
          <div id="state-listbox"><div id="react-select-3-option-0">Illinois</div></div>
        """)
        assert _click_custom_option(page, page.locator("#state"), "IL") is True
        browser.close()


def test_closed_job_message_is_detected():
    assert pinpoint_job_closed(_Page(
        body="This posting is no longer available.")) is True
    assert pinpoint_job_closed(_Page(body="Apply Now")) is False


def test_receipt_rejects_generic_gratitude_on_application_form():
    receipt = pinpoint_confirmation_receipt(
        _Page(body="Thank you for your application."), timeout_ms=1)
    assert receipt["confirmed"] is False


def test_receipt_accepts_specific_confirmation_context_and_text():
    receipt = pinpoint_confirmation_receipt(_Page(
        url="https://tenant.pinpointhq.com/en/applications/confirmation",
        title="Application Confirmation",
        body="Your application has been submitted. Reference ID PP-55119.",
    ), timeout_ms=1)
    assert receipt["confirmed"] is True
    assert receipt["ats"] == "pinpoint"
    assert receipt["confirmationId"] == "PP-55119"
