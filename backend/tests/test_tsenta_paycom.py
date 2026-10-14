"""Tests for the dedicated Paycom guest-application adapter."""

from backend.src.tools.tsenta_paycom import (
    paycom_confirmation_receipt,
    paycom_dismiss_cookie_notice,
    paycom_job_closed,
    paycom_url_candidates,
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
    def __init__(self, body="", url=None, title="", nodes=None, confirmation=None):
        self.body = body
        self.url = url or "https://www.paycomonline.net/v4/ats/web.php/portal/ABC/jobs/42"
        self._title = title
        self.nodes = nodes or []
        self.confirmation = confirmation

    def locator(self, selector):
        assert selector == "body"
        return _Node(self.body)

    def query_selector_all(self, selector):
        assert selector == "button"
        return self.nodes

    def query_selector(self, _selector):
        return self.confirmation

    def title(self):
        return self._title

    def wait_for_load_state(self, *_args, **_kwargs):
        return None


def test_legacy_url_resolves_to_modern_portal_route():
    candidates = paycom_url_candidates(
        "https://www.paycomonline.net/v4/ats/web.php/jobs/ViewJobDetails?"
        "job=288688&clientkey=69D616DFF45C67FFBB9BA0C33E62DBAE")
    assert candidates[0] == (
        "https://www.paycomonline.net/v4/ats/web.php/portal/"
        "69D616DFF45C67FFBB9BA0C33E62DBAE/jobs/288688")


def test_non_paycom_url_is_rejected():
    assert paycom_url_candidates("https://example.com/jobs/42") == []


def test_closed_job_message_is_detected():
    assert paycom_job_closed(_Page(body="This position is no longer available."))
    assert not paycom_job_closed(_Page(body="Apply Overview Description"))


def test_cookie_notice_closes_x_without_accepting_cookies():
    dismiss = _Node("X")
    accept = _Node("Accept Cookies")
    page = _Page(body="This website uses cookies to customize your experience.",
                 nodes=[accept, dismiss])
    assert paycom_dismiss_cookie_notice(page) is True
    assert dismiss.clicked is True
    assert accept.clicked is False


def test_receipt_rejects_bare_gratitude_on_job_page():
    receipt = paycom_confirmation_receipt(
        _Page(body="Thank you for your application."), timeout_ms=1)
    assert receipt["confirmed"] is False


def test_receipt_accepts_confirmation_context_and_specific_text():
    receipt = paycom_confirmation_receipt(_Page(
        url="https://www.paycomonline.net/v4/ats/web.php/application-confirmation",
        title="Application Confirmation",
        body="Your application has been submitted. Confirmation ID PC-55119.",
    ), timeout_ms=1)
    assert receipt["confirmed"] is True
    assert receipt["ats"] == "paycom"
    assert receipt["confirmationId"] == "PC-55119"


def test_receipt_accepts_paycom_confirmation_element():
    receipt = paycom_confirmation_receipt(
        _Page(confirmation=_Node("Application submitted")), timeout_ms=1)
    assert receipt["confirmed"] is True
