"""Tests for Indeed routing, identity checkpoints, and form safety."""

from playwright.sync_api import sync_playwright

from backend.src.tools.tsenta_apply import _execute_actions, answer_fields, collect_fields
from backend.src.tools.tsenta_indeed import (
    indeed_account_required,
    indeed_application_surface_visible,
    indeed_apply_target,
    indeed_browser_blocked,
    indeed_confirmation_receipt,
    indeed_job_closed,
    indeed_owned_url,
    indeed_phone_verification_required,
    indeed_prepare_form,
    indeed_url_candidates,
)
from backend.src.tools.tsenta_profiles import empty_profile
from backend.src.tools.tsenta_trace import Trace


class _Node:
    def __init__(self, text="", href="", visible=True):
        self._text = text
        self._href = href
        self._visible = visible

    def inner_text(self, **_kwargs):
        return self._text

    def get_attribute(self, name):
        return self._href if name == "href" else None

    def is_visible(self):
        return self._visible


class _Page:
    def __init__(self, body="", url="https://www.indeed.com/viewjob?jk=abcdef1234567890",
                 title="", nodes=None, confirmation=None):
        self.body = body
        self.url = url
        self._title = title
        self.nodes = nodes or []
        self.confirmation = confirmation

    def locator(self, selector):
        assert selector == "body"
        return _Node(self.body)

    def query_selector(self, selector):
        if self.confirmation is not None and "confirmation" in selector.lower():
            return self.confirmation
        return self.nodes[0] if self.nodes else None

    def query_selector_all(self, _selector):
        return list(self.nodes)

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
        "city": "Chicago",
        "state": "Illinois",
    })
    return profile


def test_indeed_job_url_is_canonical_and_tracking_is_removed():
    assert indeed_url_candidates(
        "https://www.indeed.com/viewjob?jk=12056a2c8b76ba40&q=cybersecurity&from=web#top"
    ) == ["https://www.indeed.com/viewjob?jk=12056a2c8b76ba40"]


def test_indeed_rejects_search_auth_insecure_and_spoofed_urls():
    assert indeed_url_candidates("https://www.indeed.com/jobs?q=security") == []
    assert indeed_url_candidates("https://secure.indeed.com/auth?jk=abcdef12") == []
    assert indeed_url_candidates("http://www.indeed.com/viewjob?jk=abcdef12") == []
    assert indeed_url_candidates("https://indeed.com.evil.test/viewjob?jk=abcdef12") == []
    assert indeed_owned_url("https://smartapply.indeed.com/apply/start") is True
    assert indeed_owned_url("https://indeed.com.evil.test/apply/start") is False


def test_visible_apply_destination_is_resolved_without_clicking():
    target = (
        "https://smartapply.indeed.com/beta/indeedapply/"
        "applybyapplyablejobid?id=test"
    )
    page = _Page(nodes=[_Node(href=target)])
    assert indeed_apply_target(page) == target


def test_account_and_phone_checkpoints_are_distinct():
    account = _Page(
        url="https://secure.indeed.com/auth?continue=https%3A%2F%2Fsmartapply.indeed.com",
        body="Ready to take the next step? Create an account or sign in. Continue with Google",
        nodes=[_Node()],
    )
    assert indeed_account_required(account) is True
    assert indeed_application_surface_visible(account) is False
    phone = _Page(
        url="https://secure.indeed.com/phone-verification",
        body="Verify your phone number. Enter the verification code.",
    )
    assert indeed_phone_verification_required(phone) is True
    assert indeed_account_required(phone) is False


def test_closed_job_message_is_detected():
    assert indeed_job_closed(_Page(body="This job has expired.")) is True
    assert indeed_job_closed(_Page(body="Apply now")) is False


def test_browser_block_is_reported_as_a_checkpoint():
    page = _Page(
        title="Blocked - Indeed.com",
        body="Request Blocked. You have been blocked. Troubleshooting Cloudflare Errors",
    )
    assert indeed_browser_blocked(page) is True
    assert indeed_browser_blocked(_Page(body="Apply now")) is False


def test_indeed_normalizes_identity_resume_and_custom_question(tmp_path):
    html = """<form>
      <label>First name *<input autocomplete="given-name" required></label>
      <label>Last name *<input autocomplete="family-name" required></label>
      <label>Email address *<input autocomplete="email" required></label>
      <label>Phone number<input autocomplete="tel"></label>
      <label>Resume *<input type="file" required></label>
      <label>Describe one security incident you investigated *<textarea required></textarea></label>
      <label>Text me about similar jobs<input type="checkbox"></label>
      <textarea name="g-recaptcha-response"></textarea>
      <button type="submit">Submit your application</button>
    </form>"""
    resume_path = tmp_path / "fake-resume.pdf"
    resume_path.write_bytes(b"%PDF-1.4\n% synthetic test only\n")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.goto("https://smartapply.indeed.com/beta/indeedapply/apply", wait_until="commit")
        page.set_content(html)
        assert indeed_application_surface_visible(page) is True
        assert indeed_prepare_form(page) == 7
        setattr(page, "_nori_scope_selector", "[data-nori-scope='indeed-application']")
        collected = {field["field_id"]: field for field in collect_fields(page)}
        assert set(("firstName", "lastName", "email", "phone", "resume")).issubset(collected)
        assert "g-recaptcha-response" not in collected
        custom = next(field for field in collected.values()
                      if "security incident" in field["label"].lower())
        assert custom["required"] is True
        assert collected["resume"]["required"] is True

        # Direct profile values and the resume can be prepared without ever
        # pressing the third-party submit control.
        direct_fields = [collected[key] for key in
                         ("firstName", "lastName", "email", "phone", "resume")]
        actions = answer_fields(direct_fields, _profile(), {}, Trace())
        summary = _execute_actions(page, actions, str(resume_path))
        assert summary["field_failures"] == []
        assert page.locator("[data-nori-field='firstName']").input_value() == "Jane"
        assert page.locator("[data-nori-field='resume']").evaluate(
            "el => el.files.length") == 1
        browser.close()


def test_indeed_receipt_rejects_job_page_and_accepts_confirmation_context():
    assert indeed_confirmation_receipt(_Page(
        body="Thank you for your application."), timeout_ms=1)["confirmed"] is False
    receipt = indeed_confirmation_receipt(_Page(
        url="https://smartapply.indeed.com/apply/confirmation",
        title="Application confirmation",
        body="Your application has been submitted. Application ID IA-55102.",
    ), timeout_ms=1)
    assert receipt["confirmed"] is True
    assert receipt["confirmationId"] == "IA-55102"
