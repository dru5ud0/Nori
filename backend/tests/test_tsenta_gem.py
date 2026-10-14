"""Tests for Gem ATS public application preparation and receipt safety."""

from playwright.sync_api import sync_playwright

from backend.src.tools.tsenta_apply import (
    _execute_actions, answer_fields, collect_fields,
)
from backend.src.tools.tsenta_gem import (
    gem_confirmation_receipt, gem_job_closed, gem_prepare_form,
    gem_url_candidates,
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
        self.url = url or "https://jobs.gem.com/acme/4965519002"
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


def test_gem_job_url_is_canonical_and_tracking_is_removed():
    assert gem_url_candidates(
        "https://jobs.gem.com/gem/am9icG9zdDqTzmNGwXTdU65YRLOAU6ZL?utm_source=test#apply"
    ) == [
        "https://jobs.gem.com/gem/am9icG9zdDqTzmNGwXTdU65YRLOAU6ZL"
    ]


def test_gem_rejects_board_only_insecure_and_spoofed_urls():
    assert gem_url_candidates("https://jobs.gem.com/gem") == []
    assert gem_url_candidates("http://jobs.gem.com/gem/4965519002") == []
    assert gem_url_candidates("https://jobs.gem.com.evil.test/gem/4965519002") == []


def test_gem_normalizes_identity_resume_and_sponsorship_without_eeo(tmp_path):
    fields = "".join(
        f"<div style='display:flex;flex-direction:column'><span>{label} *</span>"
        f"<div><div><input data-1p-ignore='true' type='text'></div></div></div>"
        for label in (
            "First name", "Last name", "Email", "LinkedIn URL",
            "Phone number", "Location",
        )
    )
    html = f"""<div id="application">
      {fields}
      <div style="display:flex;flex-direction:column"><span>Resume *</span>
        <div><input type="file" style="display:none"></div></div>
      <div><p>Will you now or in the future require sponsorship for employment
        visa status in the United States? *</p>
        <div>
          <div><input id="sponsor-yes" type="radio"><label for="sponsor-yes">Yes</label></div>
          <div><input id="sponsor-no" type="radio"><label for="sponsor-no">No</label></div>
          <div><input id="sponsor-na" type="radio"><label for="sponsor-na">N/A</label></div>
        </div>
      </div>
      <div><div>Gender</div><button type="button">Please select</button></div>
      <div id="actions"><button type="submit">Apply and save</button>
        <button type="submit">Apply without saving</button></div>
    </div>"""
    resume_path = tmp_path / "fake-resume.pdf"
    resume_path.write_bytes(b"%PDF-1.4\n% synthetic test only\n")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.set_content(html)
        assert gem_prepare_form(page) >= 10
        assert page.locator("[data-nori-scope='gem-application']").count() == 1
        collected = {field["field_id"]: field for field in collect_fields(page)}
        assert set(("firstName", "lastName", "email", "linkedinUrl",
                    "phone", "city", "resume", "needsSponsorship")).issubset(collected)
        assert collected["resume"]["required"] is True
        assert collected["needsSponsorship"]["required"] is True
        assert [item["label"] for item in collected["needsSponsorship"]["options"]] == [
            "Yes", "No", "N/A"]
        assert "gem-gender" not in collected

        actions = answer_fields(list(collected.values()), _profile(), {}, Trace())
        summary = _execute_actions(page, actions, str(resume_path))
        assert summary["field_failures"] == []
        assert page.locator("[data-nori-field='firstName']").input_value() == "Jane"
        assert page.locator("[data-nori-field='city']").input_value() == "Chicago"
        assert page.locator("#sponsor-no").is_checked()
        assert page.locator("[data-nori-field='resume']").evaluate(
            "el => el.files.length") == 1
        assert page.get_by_role("button", name="Please select").inner_text() == "Please select"
        browser.close()


def test_gem_closed_detection_and_receipt_are_strict():
    assert gem_job_closed(_Page(body="This job post is no longer active."))
    assert not gem_job_closed(_Page(body="Ready to apply?"))
    assert not gem_confirmation_receipt(
        _Page(body="Thanks for applying"), timeout_ms=1)["confirmed"]

    receipt = gem_confirmation_receipt(_Page(
        url="https://jobs.gem.com/acme/4965519002/confirmation",
        title="Application confirmation",
        body="Your application was submitted successfully. Reference ID GM-55102.",
    ), timeout_ms=1)
    assert receipt["confirmed"] is True
    assert receipt["confirmationId"] == "GM-55102"
