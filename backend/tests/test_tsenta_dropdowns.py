"""Tests for tsenta_dropdowns universal combobox and dynamic dropdown engine."""

import pytest
from unittest.mock import MagicMock

from backend.src.tools.tsenta_dropdowns import (
    matches_dropdown_option,
    normalize_dropdown_text,
    resolve_combobox_option,
)


def test_normalize_dropdown_text():
    assert normalize_dropdown_text("Bachelor's Degree") == "bachelors degree"
    assert normalize_dropdown_text("Master’s (M.S.)") == "masters m s"
    assert normalize_dropdown_text("  United States of America!  ") == "united states of america"
    assert normalize_dropdown_text(None) == ""


def test_matches_dropdown_option():
    # Fuzzy quotes and substrings
    assert matches_dropdown_option("Bachelor's Degree", "Bachelor")
    assert matches_dropdown_option("Bachelor of Science", "bachelors")
    assert matches_dropdown_option("Master's Degree", "Master")
    assert matches_dropdown_option("Doctorate (Ph.D.)", "PhD")

    # Semantic aliases: Yes / No
    assert matches_dropdown_option("Yes, I am authorized", "Yes")
    assert matches_dropdown_option("No, I will require sponsorship", "No")

    # Semantic aliases: EEO
    assert matches_dropdown_option("I am not a protected veteran", "not veteran")
    assert matches_dropdown_option("No, I do not have a disability", "no disability")
    assert matches_dropdown_option("I choose not to disclose", "decline")

    # Negative mismatch
    assert not matches_dropdown_option("Yes, I am authorized", "No")
    assert not matches_dropdown_option("High School", "Bachelor")


def test_resolve_combobox_native_select():
    mock_el = MagicMock()
    mock_el.evaluate.return_value = "select"

    res = resolve_combobox_option(None, mock_el, "Bachelor")
    assert res["success"] is True
    assert res["strategy"] == "native-select-label"
    mock_el.select_option.assert_called()


def test_resolve_combobox_aria_option():
    mock_page = MagicMock()
    mock_control = MagicMock()
    mock_control.evaluate.return_value = "div"

    mock_opt1 = MagicMock()
    mock_opt1.is_visible.return_value = True
    mock_opt1.inner_text.return_value = "High School"

    mock_opt2 = MagicMock()
    mock_opt2.is_visible.return_value = True
    mock_opt2.inner_text.return_value = "Bachelor's Degree"

    mock_page.query_selector_all.return_value = [mock_opt1, mock_opt2]

    res = resolve_combobox_option(mock_page, mock_control, "Bachelor")
    assert res["success"] is True
    assert res["strategy"] == "aria-combobox-click"
    assert "Bachelor's Degree" in res["matched_text"]
    mock_opt2.click.assert_called()
