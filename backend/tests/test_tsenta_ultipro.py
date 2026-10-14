"""Tests for the UKG Pro / UltiPro account-aware adapter."""

from backend.src.tools.tsenta_ultipro import (
    ULTIPRO_ACCOUNT_SELECTOR,
    ultipro_account_required,
    ultipro_confirmation_receipt,
    ultipro_job_closed,
    ultipro_url_candidates,
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
        self.url = url or (
            "https://recruiting2.ultipro.com/acme/JobBoard/board/OpportunityDetail?"
            "opportunityId=42")
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


def test_ultipro_candidate_preserves_opportunity_identity():
    url = ("https://recruiting2.ultipro.com/acme/JobBoard/board/OpportunityDetail?"
           "opportunityId=abc-123#details")
    candidates = ultipro_url_candidates(url)
    assert candidates[0].endswith("OpportunityDetail?opportunityId=abc-123")


def test_new_ukg_domain_is_supported():
    url = ("https://acme.rec.pro.ukg.net/tenant/JobBoard/board/OpportunityDetail?"
           "opportunityId=abc-123")
    assert ultipro_url_candidates(url) == [url]


def test_unrelated_or_insecure_url_is_rejected():
    assert ultipro_url_candidates("https://example.com/jobs/42") == []
    assert ultipro_url_candidates(
        "http://recruiting2.ultipro.com/acme/JobBoard/42") == []


def test_closed_opportunity_message_is_detected():
    assert ultipro_job_closed(_Page(
        body="This opportunity is no longer available.")) is True
    assert ultipro_job_closed(_Page(body="Apply now")) is False


def test_signin_redirect_is_an_explicit_checkpoint():
    page = _Page(
        url="https://signin-us.ultipro.com/u/login?state=fixture",
        body="Welcome. Email address Password Sign in. Don't have an account? Sign up",
        selectors={ULTIPRO_ACCOUNT_SELECTOR: _Node()},
    )
    assert ultipro_account_required(page) is True


def test_hidden_credential_control_is_not_a_checkpoint():
    page = _Page(
        body="Opportunity details Apply now",
        selectors={ULTIPRO_ACCOUNT_SELECTOR: _Node(visible=False)},
    )
    assert ultipro_account_required(page) is False


def test_receipt_rejects_generic_gratitude_on_job_page():
    receipt = ultipro_confirmation_receipt(
        _Page(body="Thank you for your application."), timeout_ms=1)
    assert receipt["confirmed"] is False


def test_receipt_accepts_confirmation_context_and_specific_text():
    receipt = ultipro_confirmation_receipt(_Page(
        url="https://recruiting2.ultipro.com/acme/application-confirmation",
        title="Application Confirmation",
        body="Your application has been submitted. Confirmation ID UKG-55119.",
    ), timeout_ms=1)
    assert receipt["confirmed"] is True
    assert receipt["ats"] == "ultipro"
    assert receipt["confirmationId"] == "UKG-55119"
