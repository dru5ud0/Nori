"""SmartRecruiters adapter tests."""

from backend.src.tools.tsenta_smartrecruiters import (
    smartrecruiters_apply_url,
    smartrecruiters_challenge_present,
    smartrecruiters_confirmation_receipt,
    smartrecruiters_url_candidates,
)


def test_url_candidates_preserve_posting_without_inventing_publication_uuid():
    url = "https://jobs.smartrecruiters.com/Acme/744000123-role?trid=abc"
    candidates = smartrecruiters_url_candidates(url)
    assert candidates[0] == url
    assert candidates[1] == "https://jobs.smartrecruiters.com/Acme/744000123-role"
    assert all("oneclick-ui" not in item for item in candidates)


class _Node:
    def __init__(self, text="", href=""):
        self.text = text
        self.href = href

    def get_attribute(self, name):
        return self.href if name == "href" else None

    def inner_text(self, timeout=None):
        return self.text

    def is_visible(self):
        return True


class _Frame:
    def __init__(self, url):
        self.url = url


class _Page:
    def __init__(self, text="", node=None, frames=None):
        self.url = "https://jobs.smartrecruiters.com/Acme/744000123-role"
        self.text = text
        self.node = node
        self.frames = frames or [self]

    def query_selector(self, selector):
        return self.node

    def locator(self, selector):
        return _Node(self.text)

    def wait_for_load_state(self, *args, **kwargs):
        return None


def test_extracts_only_https_oneclick_apply_url():
    href = "https://jobs.smartrecruiters.com/oneclick-ui/company/Acme/publication/uuid"
    assert smartrecruiters_apply_url(_Page(node=_Node(href=href))) == href
    assert smartrecruiters_apply_url(_Page(node=_Node(href="javascript:void(0)"))) == ""


def test_detects_datadome_frame_as_human_challenge():
    page = _Page(frames=[_Frame(
        "https://geo.captcha-delivery.com/captcha/?referer=smartrecruiters")])
    assert smartrecruiters_challenge_present(page) is True


def test_receipt_rejects_bare_thank_you_and_accepts_specific_text():
    assert smartrecruiters_confirmation_receipt(_Page("Thank you"), 100)["confirmed"] is False
    receipt = smartrecruiters_confirmation_receipt(_Page(
        "Your application has been submitted. Reference number SR-77889"), 100)
    assert receipt["confirmed"] is True
    assert receipt["confirmationId"] == "SR-77889"
