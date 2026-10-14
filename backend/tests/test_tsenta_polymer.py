"""Tests for Polymer public-form preparation and receipt safety."""

from playwright.sync_api import sync_playwright

from backend.src.tools.tsenta_apply import (
    _execute_actions, answer_fields, collect_fields,
)
from backend.src.tools.tsenta_polymer import (
    polymer_confirmation_receipt, polymer_job_closed, polymer_prepare_form,
    polymer_url_candidates,
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
        self.url = url or "https://jobs.polymer.co/themis/40401"
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
        "city": "Chicago",
    })
    return profile


def test_polymer_job_url_is_canonical_and_tracking_is_removed():
    assert polymer_url_candidates(
        "https://jobs.polymer.co/themis/40401?source=linkedin#apply"
    ) == ["https://jobs.polymer.co/themis/40401"]


def test_polymer_rejects_board_only_insecure_and_spoofed_urls():
    assert polymer_url_candidates("https://jobs.polymer.co/themis") == []
    assert polymer_url_candidates("http://jobs.polymer.co/themis/40401") == []
    assert polymer_url_candidates(
        "https://jobs.polymer.co.evil.test/themis/40401") == []


def test_polymer_normalizes_profile_resume_and_custom_questions(tmp_path):
    html = """<main>
      <section id="apply">
        <h2>Apply here</h2>
        <div><label for="inputName">Name <span>( required )</span></label>
          <input id="inputName" required></div>
        <div><label for="inputEmail">Email address <span>( required )</span></label>
          <input id="inputEmail" type="email" required></div>
        <div><label for="inputPhone">Phone number</label>
          <input id="inputPhone" type="tel"></div>
        <div><label for="inputLocation">Location</label>
          <input id="inputLocation"></div>
        <div><label for="inputLinkedInprofile">LinkedIn profile</label>
          <input id="inputLinkedInprofile"></div>
        <div><label for="file">Resume <span>( required )</span></label>
          <input id="file" type="file" required></div>
        <div><label for="inputWhy">Why do you want to work here?
          <span>( required )</span></label><textarea id="inputWhy" required></textarea></div>
        <textarea name="g-recaptcha-response" hidden></textarea>
        <button type="submit">Submit application</button>
      </section>
    </main>"""
    resume_path = tmp_path / "fake-resume.pdf"
    resume_path.write_bytes(b"%PDF-1.4\n% synthetic test only\n")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.set_content(html)
        assert polymer_prepare_form(page) == 7
        assert page.locator(
            "[data-nori-scope='polymer-application']").count() == 1
        fields = {field["field_id"]: field for field in collect_fields(page)}
        assert set(("fullName", "email", "phone", "city", "linkedinUrl",
                    "resume", "inputWhy")).issubset(fields)
        assert fields["fullName"]["required"] is True
        assert fields["resume"]["required"] is True
        assert fields["inputWhy"]["required"] is True
        assert "g-recaptcha-response" not in fields

        # The custom employer question remains a review/LLM responsibility;
        # execute only the direct profile fields and required attachment here.
        direct_fields = [field for key, field in fields.items() if key != "inputWhy"]
        actions = answer_fields(direct_fields, _profile(), {}, Trace())
        summary = _execute_actions(page, actions, str(resume_path))
        assert summary["field_failures"] == []
        assert page.locator("#inputName").input_value() == "Jane Doe"
        assert page.locator("#inputEmail").input_value() == "jane@example.test"
        assert page.locator("#inputLocation").input_value() == "Chicago"
        assert page.locator("#file").evaluate("el => el.files.length") == 1
        browser.close()


def test_polymer_closed_detection_and_receipt_are_strict():
    assert polymer_job_closed(_Page(
        body="This role is no longer accepting applications."))
    assert not polymer_job_closed(_Page(body="Apply here"))
    assert not polymer_confirmation_receipt(
        _Page(body="Thanks for applying"), timeout_ms=1)["confirmed"]

    receipt = polymer_confirmation_receipt(_Page(
        url="https://jobs.polymer.co/themis/40401/confirmation",
        title="Application confirmation",
        body="Your application has been received. Reference ID PM-55102.",
    ), timeout_ms=1)
    assert receipt["confirmed"] is True
    assert receipt["confirmationId"] == "PM-55102"
