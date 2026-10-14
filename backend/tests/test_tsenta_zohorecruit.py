"""Tests for the dedicated Zoho Recruit public-form adapter."""

from playwright.sync_api import sync_playwright

from backend.src.tools.tsenta_apply import _click_custom_option, collect_fields
from backend.src.tools.tsenta_zohorecruit import (
    zohorecruit_confirmation_receipt,
    zohorecruit_decline_optional_cookies,
    zohorecruit_job_closed,
    zohorecruit_prepare_form,
    zohorecruit_url_candidates,
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
        self.url = url or "https://tenant.zohorecruit.com/jobs/careers/42/Role"
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


def test_url_candidate_preserves_tenant_and_drops_fragment():
    candidates = zohorecruit_url_candidates(
        "https://tenant.zohorecruit.com/jobs/careers/42/SOC-Analyst#apply")
    assert candidates[0] == (
        "https://tenant.zohorecruit.com/jobs/careers/42/SOC-Analyst")


def test_unrelated_or_insecure_url_is_rejected():
    assert zohorecruit_url_candidates("https://example.com/jobs/42") == []
    assert zohorecruit_url_candidates(
        "http://tenant.zohorecruit.com/jobs/careers/42/Role") == []


def test_cookie_helper_declines_nonessential_and_never_accepts_all():
    accept = _Node("Accept all")
    decline = _Node("Decline non-essential")
    page = _Page(buttons=[accept, decline])
    assert zohorecruit_decline_optional_cookies(page) is True
    assert decline.clicked is True
    assert accept.clicked is False


def test_custom_markup_is_normalized_for_generic_collector():
    html = """<form>
      <div class="crc-form-row crc-rec-form_first">
        <label class="crm-from-label"><span class="crc-label-text">First Name <span class="crc-form-mandatory">*</span></span></label>
        <crux-text-component id="rec-form_first"><input name="raw-first"></crux-text-component>
      </div>
      <div class="crc-form-row crc-rec-form_source">
        <label class="crm-from-label"><span class="crc-label-text">How did you hear about us <span class="crc-form-mandatory">*</span></span></label>
        <crux-picklist-component id="rec-form_source"><div role="combobox" aria-haspopup="listbox"></div></crux-picklist-component>
      </div>
      <div class="crc-form-row crc-rec-form_tracking">
        <label class="crm-from-label"><span class="crc-label-text">Time Tracking <span class="crc-form-mandatory">*</span></span></label>
        <div class="crc-custom-cheackbox"><input type="checkbox" name="checkbox"><span class="crc-terms-text">Are you comfortable using time-tracking software?</span></div>
      </div>
      <input type="file" name="rec-easyresume_file">
    </form>"""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.set_content(html)
        assert zohorecruit_prepare_form(page) == 4
        fields = {field["field_id"]: field for field in collect_fields(page)}
        assert fields["rec-form_first"]["label"].startswith("First Name")
        assert fields["rec-form_first"]["required"] is True
        assert fields["rec-form_source"]["kind"] == "select"
        assert fields["rec-form_tracking"]["kind"] == "checkbox"
        assert "time-tracking software" in fields["rec-form_tracking"]["label"]
        assert fields["zohorecruit-optional-resume-autofill"]["required"] is False
        browser.close()


def test_existing_us_phone_code_is_accepted_without_reopening_dropdown():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.set_content(
            '<div role="combobox" data-nori-field="candidate.phone.country">(+1)</div>')
        control = page.locator('[data-nori-field="candidate.phone.country"]')
        assert _click_custom_option(page, control, "United States") is True
        browser.close()


def test_closed_job_message_is_detected():
    assert zohorecruit_job_closed(_Page(
        body="We are no longer accepting applications.")) is True
    assert zohorecruit_job_closed(_Page(body="I'm interested")) is False


def test_receipt_rejects_generic_thank_you_without_confirmation_context():
    receipt = zohorecruit_confirmation_receipt(
        _Page(body="Thank you for applying."), timeout_ms=1)
    assert receipt["confirmed"] is False


def test_receipt_accepts_specific_text_on_confirmation_route():
    receipt = zohorecruit_confirmation_receipt(_Page(
        url="https://tenant.zohorecruit.com/jobs/application-confirmation",
        title="Application Confirmation",
        body="Your application has been submitted. Reference ID ZR-55119.",
    ), timeout_ms=1)
    assert receipt["confirmed"] is True
    assert receipt["ats"] == "zohorecruit"
    assert receipt["confirmationId"] == "ZR-55119"
