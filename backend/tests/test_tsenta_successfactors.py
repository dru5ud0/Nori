"""Tests for SAP SuccessFactors account-aware application routing."""

from backend.src.tools.tsenta_successfactors import (
    SUCCESSFACTORS_ACCOUNT_SELECTOR,
    successfactors_account_required,
    successfactors_confirmation_receipt,
    successfactors_job_closed,
    successfactors_url_candidates,
)


class _Node:
    def __init__(self, text="", visible=True):
        self._text = text
        self._visible = visible

    def inner_text(self, **_kwargs):
        return self._text

    def is_visible(self):
        return self._visible


class _Page:
    def __init__(self, body="", url=None, title="", selectors=None):
        self.body = body
        self.url = url or "https://career2.successfactors.eu/career?company=Example"
        self._title = title
        self.selectors = selectors or {}

    def locator(self, selector):
        assert selector == "body"
        return _Node(self.body)

    def query_selector(self, selector):
        if selector in self.selectors:
            return self.selectors[selector]
        return None

    def title(self):
        return self._title

    def wait_for_load_state(self, *_args, **_kwargs):
        return None


def test_classic_url_keeps_tenant_query_and_drops_fragment():
    candidates = successfactors_url_candidates(
        "https://career2.successfactors.eu/career?company=Ericsson&career_job_req_id=42#apply")
    assert candidates[0] == (
        "https://career2.successfactors.eu/career?company=Ericsson&career_job_req_id=42")


def test_branded_hiringcafe_job_url_is_preserved():
    url = "https://careers.example.com/job/Chicago/SOC-Analyst/1409649100"
    assert successfactors_url_candidates(url) == [url]


def test_non_https_url_is_rejected():
    assert successfactors_url_candidates("http://career.example.com/job/42") == []


def test_closed_job_message_is_detected():
    assert successfactors_job_closed(_Page(
        body="The requisition is no longer available.")) is True
    assert successfactors_job_closed(_Page(body="Apply for this role")) is False


def test_sign_in_and_account_creation_are_explicit_checkpoints():
    page = _Page(
        body="Already have an account? Please sign in. Create an account to apply.",
        title="Career Opportunities: Sign In",
        selectors={SUCCESSFACTORS_ACCOUNT_SELECTOR: _Node()},
    )
    assert successfactors_account_required(page) is True


def test_hidden_password_control_is_not_an_account_checkpoint():
    page = _Page(
        body="Application form",
        selectors={SUCCESSFACTORS_ACCOUNT_SELECTOR: _Node(visible=False)},
    )
    assert successfactors_account_required(page) is False


def test_receipt_rejects_generic_thank_you_on_job_page():
    receipt = successfactors_confirmation_receipt(
        _Page(body="Thank you for your application."), timeout_ms=1)
    assert receipt["confirmed"] is False


def test_receipt_accepts_confirmation_context_and_specific_text():
    receipt = successfactors_confirmation_receipt(_Page(
        url="https://career2.successfactors.eu/application-confirmation",
        title="Application Confirmation",
        body="Your application has been submitted. Confirmation ID SF-55119.",
    ), timeout_ms=1)
    assert receipt["confirmed"] is True
    assert receipt["ats"] == "successfactors"
    assert receipt["confirmationId"] == "SF-55119"
