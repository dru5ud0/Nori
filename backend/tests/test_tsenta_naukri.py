"""Tests for Naukri's non-clicking, account-aware adapter helpers."""

from backend.src.tools.tsenta_naukri import (
    naukri_account_required,
    naukri_apply_state,
    naukri_browser_blocked,
    naukri_confirmation_receipt,
    naukri_job_closed,
    naukri_url_candidates,
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
    def __init__(self, body="", url=None, title="", google=None,
                 login=None, apply=None, forms=None, confirmation=None):
        self.body = body
        self.url = url or (
            "https://www.naukri.com/job-listings-cyber-security-analyst-"
            "genpact-hyderabad-2-to-4-years-070926023470")
        self._title = title
        self.google = google
        self.login = login
        self.apply = apply
        self.forms = forms or []
        self.confirmation = confirmation

    def locator(self, selector):
        assert selector == "body"
        return _Node(self.body)

    def query_selector(self, selector):
        lowered = selector.lower()
        if "confirmation" in lowered and self.confirmation is not None:
            return self.confirmation
        if "continue-with-google" in lowered:
            return self.google
        if "login.naukri.com" in lowered or "login_layer" in lowered:
            return self.login
        if "apply" in lowered:
            return self.apply
        return None

    def query_selector_all(self, selector):
        return list(self.forms) if "applyform" in selector.lower() else []

    def title(self):
        return self._title

    def wait_for_load_state(self, *_args, **_kwargs):
        return None


def test_naukri_current_job_url_is_canonical_and_tracking_is_removed():
    url = (
        "https://www.naukri.com/job-listings-cyber-security-analyst-genpact-"
        "noida-hyderabad-bangalore-rural-2-to-4-years-070926023470?src=search#top")
    assert naukri_url_candidates(url) == [url.split("?", 1)[0]]


def test_naukri_rejects_search_login_insecure_and_spoofed_urls():
    assert naukri_url_candidates("https://www.naukri.com/cyber-security-jobs") == []
    assert naukri_url_candidates("https://login.naukri.com/nLogin/Login.php") == []
    assert naukri_url_candidates("http://www.naukri.com/job/security-123") == []
    assert naukri_url_candidates("https://naukri.com.evil.test/job/security-123") == []


def test_logged_out_job_is_an_account_checkpoint_not_a_form():
    page = _Page(google=_Node(visible=True), login=_Node(visible=True),
                 apply=_Node(visible=False))
    assert naukri_account_required(page) is True
    assert naukri_apply_state(page) == "account-required"


def test_visible_apply_is_classified_as_ambiguous_one_click():
    page = _Page(google=_Node(visible=False), login=_Node(visible=True),
                 apply=_Node(visible=True))
    assert naukri_account_required(page) is False
    assert naukri_apply_state(page) == "one-click"


def test_real_form_can_be_observed_without_clicking_apply():
    page = _Page(apply=_Node(visible=False), forms=[_Node(visible=True)])
    assert naukri_apply_state(page) == "form"


def test_closed_and_browser_block_states_are_specific():
    assert naukri_job_closed(_Page(body="This job has expired.")) is True
    blocked = _Page(title="Access Denied", body="Access denied. Request blocked.")
    assert naukri_browser_blocked(blocked) is True
    assert naukri_apply_state(blocked) == "browser-blocked"


def test_receipt_rejects_failure_and_external_redirect_notices():
    failed = naukri_confirmation_receipt(_Page(
        url="https://apply.naukri.com/apply/processCSite",
        body="Your apply was unsuccessful. To apply again, go back."), timeout_ms=1)
    assert failed["confirmed"] is False
    redirect = naukri_confirmation_receipt(_Page(
        url="https://apply.naukri.com/apply/showAcp",
        body="You were redirected to the company website for completing your application process."),
        timeout_ms=1)
    assert redirect["confirmed"] is False


def test_receipt_accepts_only_specific_naukri_success_text():
    receipt = naukri_confirmation_receipt(_Page(
        url="https://apply.naukri.com/apply/showAcp",
        body="You have successfully applied. Application ID NK-55102."), timeout_ms=1)
    assert receipt["confirmed"] is True
    assert receipt["confirmationId"] == "NK-55102"
