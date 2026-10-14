"""Unit tests for tsenta_eightfold adapter."""

from unittest.mock import MagicMock
from backend.src.tools.tsenta_eightfold import (
    eightfold_url_candidates,
    eightfold_job_closed,
    eightfold_dismiss_privacy_modal,
    eightfold_confirmation_receipt,
)


def test_eightfold_url_candidates_conversion():
    # Converts /careers/job/123 to /careers/apply?pid=123
    url = "https://talent.mtsi-va.com/careers/job/1133915068168"
    candidates = eightfold_url_candidates(url)
    assert candidates[0] == "https://talent.mtsi-va.com/careers/apply?pid=1133915068168"

    # Preserves existing /careers/apply?pid=123
    apply_url = "https://talent.mtsi-va.com/careers/apply?pid=1133915068168"
    assert eightfold_url_candidates(apply_url) == ["https://talent.mtsi-va.com/careers/apply?pid=1133915068168"]


def test_eightfold_job_closed():
    page_open = MagicMock()
    page_open.locator.return_value.inner_text.return_value = "Apply for this exciting role"
    assert not eightfold_job_closed(page_open)

    page_closed = MagicMock()
    page_closed.locator.return_value.inner_text.return_value = "This position is no longer available"
    assert eightfold_job_closed(page_closed)


def test_eightfold_dismiss_privacy_modal():
    page = MagicMock()
    mock_btn = MagicMock()
    mock_btn.is_visible.return_value = True
    page.query_selector.return_value = mock_btn

    assert eightfold_dismiss_privacy_modal(page) is True
    mock_btn.click.assert_called()


def test_eightfold_confirmation_receipt():
    page = MagicMock()
    page.locator.return_value.inner_text.return_value = "Thank you for applying! Your application has been submitted."
    res = eightfold_confirmation_receipt(page)
    assert res["confirmed"] is True
    assert "application has been submitted" in res["evidence"]
