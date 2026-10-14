"""Tests for Dover public application preparation and receipt safety."""

from pathlib import Path

from playwright.sync_api import sync_playwright

from backend.src.tools.tsenta_apply import (
    _execute_actions, answer_fields, collect_fields,
)
from backend.src.tools.tsenta_dover import (
    dover_confirmation_receipt, dover_job_closed, dover_prepare_form,
    dover_url_candidates,
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
    def __init__(self, body="", url=None, title="", confirmation=None):
        self.body = body
        self.url = url or "https://app.dover.com/apply/acme/2453a2a5-9918-4092-ab05-5988faac9cbc"
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


def _profile() -> dict:
    profile = empty_profile()
    profile["personalInformation"].update({
        "firstName": "Jane",
        "lastName": "Doe",
        "email": "jane@example.test",
        "phone": "+15550101010",
        "linkedinUrl": "https://www.linkedin.com/in/jane-doe-test",
        "country": "United States",
    })
    profile["workAuthorization"].update({
        "isAuthorizedToWork": True,
        "needsSponsorship": False,
        "workAuthorizations": [{
            "countryCode": "US",
            "isAuthorizedToWork": True,
            "needsSponsorship": False,
        }],
    })
    return profile


def test_dover_application_url_is_canonical_and_tracking_is_removed():
    source = (
        "https://app.dover.com/apply/camintalent/"
        "2453a2a5-9918-4092-ab05-5988faac9cbc?utm_source=test#apply")
    assert dover_url_candidates(source) == [
        "https://app.dover.com/apply/camintalent/"
        "2453a2a5-9918-4092-ab05-5988faac9cbc"]


def test_dover_rejects_non_apply_insecure_and_spoofed_urls():
    assert dover_url_candidates(
        "https://app.dover.com/jobs/camintalent") == []
    assert dover_url_candidates(
        "http://app.dover.com/apply/acme/2453a2a5-9918-4092-ab05-5988faac9cbc") == []
    assert dover_url_candidates(
        "https://app.dover.com.evil.test/apply/acme/2453a2a5-9918-4092-ab05-5988faac9cbc") == []


def test_dover_form_normalization_ignores_parser_and_labels_uuid_questions(tmp_path):
    html = """<form>
      <div role="button"><input type="file"><span>Autofill from resume</span></div>
      <div class="row"><div>First Name *</div><div class="MuiFormControl-root"><input name="firstName" required></div></div>
      <div class="row"><div>Last Name *</div><div class="MuiFormControl-root"><input name="lastName" required></div></div>
      <div class="row"><div>Email *</div><div class="MuiFormControl-root"><input name="email" type="email" required></div></div>
      <div class="row"><div>LinkedIn Profile URL *</div><div class="MuiFormControl-root"><input name="linkedinUrl" required></div></div>
      <div class="row"><div>Phone Number</div><div class="MuiFormControl-root"><input name="phoneNumber"></div></div>
      <div class="row"><div>Are you authorized to work in the US for any employer? *</div><div class="MuiFormControl-root"><div role="radiogroup">
        <label><input type="radio" name="uuid-auth" value="Yes" required>Yes</label>
        <label><input type="radio" name="uuid-auth" value="No" required>No</label>
      </div></div></div>
      <div class="row"><div>Will you now or in the future require sponsorship to work in the US? *</div><div class="MuiFormControl-root"><input name="uuid-sponsor" required></div></div>
      <div role="button"><input type="file"><span>Resume *</span></div>
      <button type="submit">Apply</button>
    </form>"""
    resume_path = tmp_path / "fake-resume.pdf"
    resume_path.write_bytes(b"%PDF-1.4\n% test only\n")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.set_content(html)
        assert dover_prepare_form(page) >= 8
        fields = {field["field_id"]: field for field in collect_fields(page)}
        assert "nori-field-0" not in fields
        assert fields["firstName"]["label"] == "First Name"
        assert fields["uuid-auth"]["label"].startswith(
            "Are you authorized to work")
        assert fields["uuid-sponsor"]["label"].startswith(
            "Will you now or in the future require sponsorship")
        assert fields["resume"]["required"] is True

        actions = answer_fields(list(fields.values()), _profile(), {}, Trace())
        summary = _execute_actions(page, actions, str(resume_path))
        assert summary["field_failures"] == []
        assert page.locator("input[name='firstName']").input_value() == "Jane"
        assert page.locator("input[name='uuid-sponsor']").input_value() == "No"
        assert page.locator("input[name='uuid-auth'][value='Yes']").is_checked()
        assert page.locator("input[data-nori-field='resume']").evaluate(
            "el => el.files.length") == 1
        browser.close()


def test_closed_detection_and_receipt_require_context_or_success_surface():
    assert dover_job_closed(_Page(body="This role is no longer accepting applications."))
    assert not dover_job_closed(_Page(body="Apply for this role"))
    assert not dover_confirmation_receipt(_Page(
        body="Thanks for applying"), timeout_ms=1)["confirmed"]

    receipt = dover_confirmation_receipt(_Page(
        url="https://app.dover.com/apply/acme/confirmation",
        title="Application confirmation",
        body="Your application has been received. Reference ID DV-55102.",
    ), timeout_ms=1)
    assert receipt["confirmed"] is True
    assert receipt["confirmationId"] == "DV-55102"
