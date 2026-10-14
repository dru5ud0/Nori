"""Tests for Hireology public application preparation and safety."""

from playwright.sync_api import sync_playwright

from backend.src.tools.tsenta_apply import (
    _execute_actions, answer_fields, collect_fields, default_answerer,
)
from backend.src.tools.tsenta_hireology import (
    hireology_confirmation_receipt, hireology_job_closed,
    hireology_prepare_form, hireology_url_candidates,
)
from backend.src.tools.tsenta_llm import make_llm_answerer
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
    def __init__(self, body="", url=None, title="", confirmation=None):
        self.body = body
        self.url = url or (
            "https://careers.hireology.com/employer/123/description")
        self._title = title
        self.confirmation = confirmation

    def locator(self, selector):
        assert selector == "body"
        return _Node(self.body)

    def query_selector(self, _selector):
        return self.confirmation

    def title(self):
        return self._title

    def wait_for_load_state(self, *_args, **_kwargs):
        return None


def test_public_job_url_is_normalized_and_fragment_removed():
    url = "https://careers.hireology.com/dealer/2858462/description?src=feed#apply"
    assert hireology_url_candidates(url) == [
        "https://careers.hireology.com/dealer/2858462/description?src=feed"]


def test_non_hireology_or_insecure_url_is_rejected():
    assert hireology_url_candidates(
        "https://example.com/dealer/2858462/description") == []
    assert hireology_url_candidates(
        "http://careers.hireology.com/dealer/2858462/description") == []


def test_form_labels_required_flags_uploads_and_referral_are_normalized():
    html = """<div>
      <input id="first_name-0" type="text"><label for="first_name-0">First name (required)</label>
      <label><input id="sms_opt_in-0" type="checkbox" checked>Receive text message updates</label>
      <select id="state_id-0"><option value="14">IL</option></select><label for="state_id-0">State/Province</label>
      <div id="candidate_referred-0"><div class="careers-radiobutton__component-label">Were you referred by anyone?</div>
        <label for="candidate_referred-no-0">No</label><input id="candidate_referred-no-0" type="radio" name="candidate_referred-0" value="no"></div>
      <input id="resume-0" type="file"><input id="cover-0" type="file">
      <label for="custom_authorized-0">Are you legally authorized to work in the United States?</label>
      <textarea id="custom_authorized-0"></textarea>
      <label for="custom_preferred-0">Preferred Name (optional)</label>
      <textarea id="custom_preferred-0"></textarea></div>"""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.set_content(html)
        assert hireology_prepare_form(page) >= 8
        fields = {field["field_id"]: field for field in collect_fields(page)}
        assert fields["first_name-0"]["required"] is True
        assert fields["resume-0"]["required"] is True
        assert fields["resume-0"]["label"] == "Resume"
        assert fields["cover-0"]["required"] is False
        assert fields["candidate_referred-0"]["label"] == (
            "Were you referred by anyone?")
        assert fields["sms_opt_in-0"]["kind"] == "checkbox"
        assert fields["custom_authorized-0"]["required"] is True
        assert fields["custom_preferred-0"]["required"] is False
        browser.close()


def test_optional_sms_is_actively_unchecked_and_state_code_matches_exactly():
    profile = empty_profile()
    profile["personalInformation"]["state"] = "IL"
    html = """<label for="sms_opt_in-0">I would like text message updates.</label>
      <input id="sms_opt_in-0" type="checkbox" checked>
      <label for="state_id-0">State/Province</label>
      <select id="state_id-0"><option value="5">CA</option><option value="14">IL</option></select>"""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.set_content(html)
        hireology_prepare_form(page)
        fields = collect_fields(page)
        actions = answer_fields(fields, profile, {}, Trace())
        summary = _execute_actions(page, actions, None)
        assert summary["field_failures"] == []
        assert page.locator("#sms_opt_in-0").is_checked() is False
        assert page.locator("#state_id-0").input_value() == "14"
        browser.close()


def test_hireology_authorization_and_hispanic_answers_are_profile_safe():
    profile = empty_profile()
    profile["personalInformation"]["country"] = "US"
    profile["workAuthorization"].update({
        "isAuthorizedToWork": True,
        "needsSponsorship": False,
        "workAuthorizations": [{
            "countryCode": "US", "isAuthorizedToWork": True,
            "needsSponsorship": False,
        }],
    })
    authorized = default_answerer({
        "field_id": "custom_authorized-0",
        "label": "Are you legally authorized to work in the United States?",
        "kind": "textarea", "required": True, "options": [],
    }, profile, {}, Trace())
    hispanic = default_answerer({
        "field_id": "is_hispanic-0", "label": "Hispanic/Latino",
        "kind": "select", "required": False,
        "options": [
            {"label": "Yes", "value": "yes"},
            {"label": "Decline to self identify", "value": "declined"},
        ],
    }, profile, {}, Trace())
    assert authorized == {
        "value": "Yes", "source": "profile-direct", "display": "Yes"}
    assert hispanic["value"] == "declined"


def test_llm_does_not_receive_sms_or_state_fields():
    profile = empty_profile()
    profile["personalInformation"]["state"] = "IL"
    calls = []
    answerer = make_llm_answerer(
        profile, llm_cfg={"api_key": "test"},
        chat=lambda messages: calls.append(messages) or "wrong")
    sms = answerer({
        "field_id": "sms_opt_in-0", "label": "Receive SMS text messages",
        "kind": "checkbox", "required": False, "options": [],
    }, profile, {}, Trace())
    state = answerer({
        "field_id": "state_id-0", "label": "State/Province",
        "kind": "select", "required": False,
        "options": [{"label": "CA", "value": "5"},
                    {"label": "IL", "value": "14"}],
    }, profile, {}, Trace())
    assert sms["value"] is False
    assert state["value"] == "14"
    assert calls == []


def test_closed_message_and_confirmation_receipt_are_strict():
    assert hireology_job_closed(_Page(body="This job posting has expired."))
    assert not hireology_job_closed(_Page(body="Apply now"))
    assert not hireology_confirmation_receipt(_Page(
        body="Thank you for your application."), timeout_ms=1)["confirmed"]
    receipt = hireology_confirmation_receipt(_Page(
        url="https://careers.hireology.com/employer/123/confirmation",
        title="Application Confirmation",
        body="Your application has been submitted. Reference ID HR-88122.",
    ), timeout_ms=1)
    assert receipt["confirmed"] is True
    assert receipt["confirmationId"] == "HR-88122"
