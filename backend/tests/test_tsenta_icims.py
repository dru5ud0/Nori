"""iCIMS adapter tests."""

from backend.src.tools.tsenta_icims import (
    ICIMS_APPLY_LINK_SELECTOR,
    icims_apply_url,
    icims_confirmation_receipt,
    icims_frame_with,
    icims_url_candidates,
)


def test_url_candidates_preserve_original_and_clean_tracking_query():
    url = "https://careers-acme.icims.com/jobs/123/security/job?in_iframe=1&source=x"
    candidates = icims_url_candidates(url)
    assert candidates[0] == url
    assert candidates[1] == "https://careers-acme.icims.com/jobs/123/security/job"


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


class _Surface:
    def __init__(self, url, nodes=None, text=""):
        self.url = url
        self.nodes = nodes or {}
        self.text = text
        self.frames = [self]

    def query_selector(self, selector):
        return self.nodes.get(selector)

    def locator(self, selector):
        return _Node(self.text)

    def wait_for_load_state(self, *args, **kwargs):
        return None


def test_finds_apply_link_inside_content_frame_and_resolves_relative_url():
    href = "/jobs/123/security/job?mode=apply&apply=yes&in_iframe=1"
    frame = _Surface("https://careers-acme.icims.com/jobs/123/security/job",
                     {ICIMS_APPLY_LINK_SELECTOR: _Node(href=href)})
    page = _Surface("https://careers-acme.icims.com/jobs/123/security/job")
    page.frames = [page, frame]
    assert icims_frame_with(page, ICIMS_APPLY_LINK_SELECTOR) is frame
    assert icims_apply_url(page).endswith("mode=apply&apply=yes&in_iframe=1")


def test_receipt_rejects_bare_thank_you_and_reads_child_frame():
    page = _Surface("https://careers-acme.icims.com/jobs/123/job")
    page.text = "Thank you"
    assert icims_confirmation_receipt(page, 100)["confirmed"] is False
    child = _Surface(page.url, text=(
        "Your application has been submitted. Confirmation ID ICIMS-77889"))
    page.frames = [page, child]
    receipt = icims_confirmation_receipt(page, 100)
    assert receipt["confirmed"] is True
    assert receipt["confirmationId"] == "ICIMS-77889"
