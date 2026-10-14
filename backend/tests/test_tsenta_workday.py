"""Workday reference-adapter tests."""

from backend.src.tools.tsenta_workday import (
    workday_confirmation_receipt,
    workday_login_required,
    workday_next_button,
    workday_url_candidates,
)


def test_workday_url_candidates_preserve_original_and_add_clean_apply_url():
    original = (
        "https://acme.wd1.myworkdayjobs.com/en-US/Careers/"
        "job/Austin/Security-Engineer_R12345?source=LinkedIn"
    )
    candidates = workday_url_candidates(original)
    assert candidates[0] == original
    assert candidates[-1].endswith("Security-Engineer_R12345/apply")
    assert "source=" not in candidates[-1]


def test_non_workday_url_is_preserved_without_inventing_routes():
    url = "https://careers.example.com/job/security"
    assert workday_url_candidates(url) == [url]


class _Node:
    def __init__(self, text="", attrs=None, visible=True, enabled=True):
        self.text = text
        self.attrs = attrs or {}
        self.visible = visible
        self.enabled = enabled
        self.clicked = False

    def inner_text(self):
        return self.text

    def get_attribute(self, name):
        return self.attrs.get(name)

    def is_visible(self):
        return self.visible

    def is_enabled(self):
        return self.enabled

    def click(self):
        self.clicked = True


class _Body:
    def __init__(self, text):
        self.text = text

    def inner_text(self, timeout=None):
        return self.text


class _Surface:
    def __init__(self, text="", selectors=None, buttons=None):
        self.url = "https://acme.wd1.myworkdayjobs.com/Careers/application"
        self.text = text
        self.selectors = selectors or {}
        self.buttons = buttons or []

    def wait_for_load_state(self, *args, **kwargs):
        return None

    def query_selector(self, selector):
        return self.selectors.get(selector)

    def query_selector_all(self, selector):
        return list(self.buttons)

    def locator(self, selector):
        assert selector == "body"
        return _Body(self.text)


def test_receipt_rejects_bare_thank_you_and_accepts_specific_evidence():
    assert workday_confirmation_receipt(_Surface("Thank you"), 100)["confirmed"] is False
    receipt = workday_confirmation_receipt(_Surface(
        "Your application has been submitted. Confirmation ID: WD-77889"), 100)
    assert receipt["confirmed"] is True
    assert receipt["confirmationId"] == "WD-77889"


def test_receipt_accepts_workday_owned_confirmation_surface():
    selector = "[data-automation-id='applicationSubmitted']"
    receipt = workday_confirmation_receipt(_Surface(
        "Complete", selectors={selector: _Node("Application complete")}), 100)
    assert receipt["confirmed"] is True
    assert receipt["signals"][0] == {"kind": "selector", "value": selector}


def test_next_button_never_returns_submit_control():
    submit = _Node("Submit", {"data-automation-id": "bottom-navigation-next-button"})
    next_button = _Node("Save and Continue", {
        "data-automation-id": "bottom-navigation-next-button"})
    assert workday_next_button(_Surface(buttons=[submit, next_button])) is next_button


def test_login_gate_detection_is_specific():
    selector = "button[data-automation-id='signInSubmitButton']"
    assert workday_login_required(_Surface(selectors={selector: _Node("Sign In")})) is True
    assert workday_login_required(_Surface("Search jobs and join our team")) is False


def test_next_button_recognizes_review_step_but_rejects_review_and_submit():
    review_submit = _Node("Review and Submit", {"data-automation-id": "bottom-navigation-next-button"})
    review_next = _Node("Review Application", {"data-automation-id": "bottom-navigation-next-button"})
    assert workday_next_button(_Surface(buttons=[review_submit])) is None
    assert workday_next_button(_Surface(buttons=[review_next])) is review_next
