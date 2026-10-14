"""Oracle Recruiting adapter contracts."""

from backend.src.tools.tsenta_oraclecloud import (
    oraclecloud_confirmation_receipt, oraclecloud_job_closed,
    oraclecloud_url_candidates,
)


def test_oraclecloud_url_candidates_keep_original_and_strip_tracking():
    url = "https://acme.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX/job/123?utm_source=feed#apply"
    assert oraclecloud_url_candidates(url) == [
        url,
        "https://acme.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX/job/123",
    ]


def test_oraclecloud_non_oracle_url_is_preserved():
    url = "https://example.com/jobs/1"
    assert oraclecloud_url_candidates(url) == [url]


class _Node:
    def __init__(self, text=""):
        self.text = text

    def is_visible(self):
        return True

    def inner_text(self):
        return self.text


class _Locator:
    def __init__(self, text):
        self.text = text

    def inner_text(self, timeout=None):
        return self.text


class _Page:
    url = "https://acme.fa.us2.oraclecloud.com/confirmation"

    def __init__(self, text):
        self.text = text

    def wait_for_load_state(self, *args, **kwargs):
        return None

    def query_selector(self, selector):
        if selector == "[data-automation-id='applicationSubmitted']" and "submitted" in self.text.lower():
            return _Node(self.text)
        return None

    def locator(self, selector):
        return _Locator(self.text)


def test_oraclecloud_closed_page_detection():
    assert oraclecloud_job_closed(_Page("This job is no longer available")) is True
    assert oraclecloud_job_closed(_Page("Apply now")) is False


def test_oraclecloud_receipt_requires_oracle_owned_signal():
    confirmed = oraclecloud_confirmation_receipt(
        _Page("Your application has been submitted"))
    assert confirmed["confirmed"] is True
    assert confirmed["ats"] == "oraclecloud"
    bare = oraclecloud_confirmation_receipt(_Page("Thank you for visiting"))
    assert bare["confirmed"] is False
