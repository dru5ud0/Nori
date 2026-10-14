"""Tests for Phenom routing, safe normalization, and answer mapping."""

from playwright.sync_api import sync_playwright

from backend.src.tools.tsenta_apply import collect_fields, default_answerer
from backend.src.tools.tsenta_llm import make_llm_answerer
from backend.src.tools.tsenta_profiles import empty_profile
from backend.src.tools.tsenta_phenom import (
    phenom_apply_url, phenom_confirmation_receipt, phenom_job_closed,
    phenom_prepare_form, phenom_reject_optional_cookies,
    phenom_url_candidates,
)
from backend.src.tools.tsenta_trace import Trace


class _Node:
    def __init__(self, text="", visible=True, href=""):
        self._text = text
        self._visible = visible
        self._href = href
        self.clicked = False

    def inner_text(self, **_kwargs):
        return self._text

    def is_visible(self):
        return self._visible

    def click(self, **_kwargs):
        self.clicked = True

    def get_attribute(self, name):
        return self._href if name == "href" else ""


class _Page:
    def __init__(self, body="", url=None, title="", buttons=None,
                 links=None, confirmation=None):
        self.body = body
        self.url = url or "https://careers.example.com/us/en/job/R1/Role"
        self._title = title
        self.buttons = buttons or []
        self.links = links or []
        self.confirmation = confirmation

    def locator(self, selector):
        assert selector == "body"
        return _Node(self.body)

    def query_selector_all(self, selector):
        if selector == "button":
            return self.buttons
        return self.links

    def query_selector(self, _selector):
        return self.confirmation

    def title(self):
        return self._title

    def wait_for_load_state(self, *_args, **_kwargs):
        return None


def test_branded_job_and_apply_routes_are_normalized():
    job = "https://careers.example.com/us/en/job/R168782/Role?source=feed#apply"
    apply = "https://careers.example.com/us/en/apply?jobSeqNo=ABC123#top"
    assert phenom_url_candidates(job) == [
        "https://careers.example.com/us/en/job/R168782/Role?source=feed"]
    assert phenom_url_candidates(apply) == [
        "https://careers.example.com/us/en/apply?jobSeqNo=ABC123"]


def test_non_phenom_or_insecure_url_is_rejected():
    assert phenom_url_candidates("https://example.com/jobs/security") == []
    assert phenom_url_candidates(
        "http://careers.example.com/us/en/job/R1/Role") == []


def test_apply_link_must_be_same_origin_https():
    page = _Page(links=[
        _Node("Apply", href="https://evil.example/apply?jobSeqNo=R1"),
        _Node("Apply now", href="/us/en/apply?jobSeqNo=R1"),
    ])
    assert phenom_apply_url(
        page, "https://careers.example.com/us/en/job/R1/Role") == (
            "https://careers.example.com/us/en/apply?jobSeqNo=R1")


def test_cookie_helper_denies_and_never_allows():
    deny = _Node("Deny")
    allow = _Node("Allow")
    assert phenom_reject_optional_cookies(_Page(
        body="We use cookies to improve your experience.",
        buttons=[allow, deny])) is True
    assert deny.clicked is True
    assert allow.clicked is False


def test_native_form_is_normalized_for_generic_collector():
    html = """<div class="resume-upload-wrapper"><input type="file"></div>
      <div class="form-group"><label for="country">Country*</label>
        <select id="country" required><option value="USA">United States of America</option></select></div>
      <div class="form-group"><label for="phoneWidget.countryPhoneCode">Country Phone Code*</label>
        <select id="phoneWidget.countryPhoneCode" required><option value="USA_1">United States (+1)</option></select></div>
      <div class="form-group" role="radiogroup" aria-label="Have you been employed by Adobe in the past?">
        <input type="radio" name="candidateSelfIdentifyAsPriorWorker" id="prior-yes" value="true" aria-label="Yes">
        <input type="radio" name="candidateSelfIdentifyAsPriorWorker" id="prior-no" value="false" aria-label="No"></div>
      <div class="form-group"><label><input id="privacy" type="checkbox" required>
        I consent to processing my information.</label></div>"""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.set_content(html)
        assert phenom_prepare_form(page) >= 5
        fields = {item["field_id"]: item for item in collect_fields(page)}
        assert fields["phenom.resume"]["label"] == "Resume"
        assert fields["phenom.resume"]["required"] is True
        assert fields["candidate.phone.country"]["label"] == "Country Phone Code"
        prior = fields["candidateSelfIdentifyAsPriorWorker"]
        assert prior["label"] == "Have you worked for us before?"
        assert prior["options"] == [
            {"label": "Yes", "value": "true"},
            {"label": "No", "value": "false"},
        ]
        assert fields["privacy"]["kind"] == "checkbox"
        assert "consent" in fields["privacy"]["label"].lower()
        browser.close()


def test_country_source_and_second_address_line_use_declared_profile_values():
    profile = empty_profile()
    profile["personalInformation"].update({
        "country": "US",
        "address": "100 Test Street",
    })
    profile["workPreferences"]["howDidYouHearAboutRole"] = "LinkedIn"
    trace = Trace()
    phone = default_answerer({
        "field_id": "candidate.phone.country", "label": "Country Phone Code",
        "kind": "select", "required": True, "options": [
            {"label": "Australia (+61)", "value": "AUS_61"},
            {"label": "United States (+1)", "value": "USA_1"},
        ],
    }, profile, {}, trace)
    source = default_answerer({
        "field_id": "source", "label": "How Did You Hear About Us?",
        "kind": "select", "required": True, "options": [
            {"label": "Job Boards", "value": "Job Boards"},
            {"label": "Social Media", "value": "Social Media"},
        ],
    }, profile, {}, trace)
    line_two = default_answerer({
        "field_id": "cntryFields.addressLine2", "label": "Address Line 2",
        "kind": "text", "required": False, "options": [],
    }, profile, {}, trace)
    assert phone["value"] == "USA_1"
    assert source["value"] == "Job Boards"
    assert line_two["source"] == "skip"


def test_llm_answerer_does_not_call_model_for_direct_phenom_fields():
    profile = empty_profile()
    profile["personalInformation"]["country"] = "United States"
    profile["workPreferences"]["howDidYouHearAboutRole"] = "HiringCafe"
    calls = []
    answerer = make_llm_answerer(
        profile, llm_cfg={"api_key": "test"},
        chat=lambda messages: calls.append(messages) or "wrong")
    phone = answerer({
        "field_id": "candidate.phone.country", "label": "Country Phone Code",
        "kind": "select", "required": True,
        "options": [{"label": "United States (+1)", "value": "USA_1"}],
    }, profile, {}, Trace())
    source = answerer({
        "field_id": "source", "label": "How Did You Hear About Us?",
        "kind": "select", "required": True,
        "options": [{"label": "Job Boards", "value": "Job Boards"}],
    }, profile, {}, Trace())
    assert phone["value"] == "USA_1"
    assert source["value"] == "Job Boards"
    assert calls == []


def test_closed_message_and_receipt_context_are_strict():
    assert phenom_job_closed(_Page(
        body="The job that you were looking for either does not exist or is no longer open."))
    assert not phenom_job_closed(_Page(body="Apply now"))
    assert not phenom_confirmation_receipt(_Page(
        body="Thank you for your application."), timeout_ms=1)["confirmed"]
    receipt = phenom_confirmation_receipt(_Page(
        url="https://careers.example.com/us/en/apply?stepname=confirmation",
        title="Application Confirmation",
        body="Your application has been submitted. Reference ID PH-55119.",
    ), timeout_ms=1)
    assert receipt["confirmed"] is True
    assert receipt["confirmationId"] == "PH-55119"
