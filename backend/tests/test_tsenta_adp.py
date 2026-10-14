"""Tests for the dedicated ADP career-site adapter helpers."""

from backend.src.tools.tsenta_adp import (
    adp_account_required,
    adp_confirmation_receipt,
    adp_dismiss_cookie_notice,
    adp_job_closed,
    adp_url_candidates,
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
    def __init__(self, body="", url="https://myjobs.adp.com/acme/cx/job-details?reqId=42",
                 title="", selectors=None):
        self.url = url
        self.body = body
        self._title = title
        self.selectors = selectors or {}

    def query_selector(self, selector):
        if selector in self.selectors:
            return self.selectors[selector]
        for key, value in self.selectors.items():
            if key in selector:
                return value
        return None

    def locator(self, selector):
        assert selector == "body"
        return _Node(self.body)

    def title(self):
        return self._title

    def wait_for_load_state(self, *_args, **_kwargs):
        return None


def test_myjobs_candidate_keeps_tenant_and_req_id():
    candidates = adp_url_candidates(
        "https://myjobs.adp.com/ecsfederal/cx/job-details?foo=bar&reqId=5001211271206")
    assert candidates[0] == (
        "https://myjobs.adp.com/ecsfederal/cx/job-details?reqId=5001211271206")


def test_workforcenow_candidate_preserves_required_identity_parameters():
    candidates = adp_url_candidates(
        "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html?"
        "jobId=612997&ccId=19000101_000001&cid=tenant&lang=en_US")
    assert "cid=tenant" in candidates[0]
    assert "ccId=19000101_000001" in candidates[0]
    assert "jobId=612997" in candidates[0]


def test_non_adp_url_is_rejected():
    assert adp_url_candidates("https://example.com/jobs/42") == []


def test_closed_job_message_is_detected():
    assert adp_job_closed(_Page(
        body="We are no longer accepting applications for this position.")) is True
    assert adp_job_closed(_Page(body="Apply for this position")) is False


def test_new_candidate_auth_checkpoint_is_not_mistaken_for_application():
    page = _Page(
        body="Welcome! Let's find your dream job! Continue Use phone number",
        url="https://myjobs.adp.com/ecsfederal/auth",
        selectors={"sdf-input#userEmail": _Node()},
    )
    assert adp_account_required(page) is True


def test_cookie_notice_is_closed_without_selecting_preferences():
    close = _Node()
    page = _Page(selectors={"#onetrust-banner-sdk": close})
    assert adp_dismiss_cookie_notice(page) is True
    assert close.clicked is True


def test_receipt_rejects_generic_thank_you_on_job_page():
    receipt = adp_confirmation_receipt(
        _Page(body="Thank you for your application."), timeout_ms=1)
    assert receipt["confirmed"] is False


def test_receipt_accepts_confirmation_route_and_specific_text():
    receipt = adp_confirmation_receipt(_Page(
        url="https://myjobs.adp.com/acme/cx/application-confirmation",
        title="Application Confirmation",
        body="Your application has been submitted. Confirmation ID ADP-55119.",
    ), timeout_ms=1)
    assert receipt["confirmed"] is True
    assert receipt["ats"] == "adp"
    assert receipt["confirmationId"] == "ADP-55119"
