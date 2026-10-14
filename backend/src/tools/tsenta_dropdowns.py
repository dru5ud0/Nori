"""tsenta_dropdowns — Universal Combobox and Dynamic Dropdown Engine.

Provides high-resilience option selection across custom ATS dropdowns:
- Native HTML <select> elements.
- ARIA role="combobox" and role="listbox" widgets (Eightfold, Workday, Ashby, Phenom).
- Searchable input filters (type-to-filter dropdowns).
- Fuzzy text matching that strips quotes, apostrophes, accents, and punctuation
  (e.g., "Bachelor's Degree" vs "Bachelors" vs "Bachelor").
- Keyboard traversal fallback (ArrowDown + Enter).

Every public function returns strings/dicts/bools and catches exceptions internally.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple


def normalize_dropdown_text(text: str) -> str:
    """Normalize text for resilient fuzzy comparison.

    Strips apostrophes, punctuation, and extra whitespace, converting to lowercase.
    Example: "Bachelor's Degree" -> "bachelors degree" -> matches "bachelor"

    Args:
        text: Raw label, option value, or search query.

    Returns:
        str: Normalized alphanumeric lowercase string. Never raises.
    """
    try:
        if not text:
            return ""
        # Remove apostrophes / single quotes entirely
        s = re.sub(r"['’`]", "", str(text).lower())
        # Replace non-alphanumeric with spaces
        s = re.sub(r"[^\w\s]", " ", s)
        # Collapse whitespace
        return re.sub(r"\s+", " ", s).strip()
    except Exception:
        return str(text or "").lower().strip()


def matches_dropdown_option(candidate_text: str, target_value: str) -> bool:
    """Determine if a dropdown option matches the desired target value.

    Args:
        candidate_text: Text displayed in or behind the dropdown option.
        target_value: The desired value or preference.

    Returns:
        bool: True if an affirmative or fuzzy match is identified. Never raises.
    """
    try:
        norm_cand = normalize_dropdown_text(candidate_text)
        norm_targ = normalize_dropdown_text(target_value)

        if not norm_cand or not norm_targ:
            return False

        # 1. Exact or substring match
        if norm_targ == norm_cand or norm_targ in norm_cand or norm_cand in norm_targ:
            return True

        # 2. Token overlap match (e.g. "bachelor" in "bachelors of science")
        cand_tokens = set(norm_cand.split())
        targ_tokens = set(norm_targ.split())
        if targ_tokens and targ_tokens.issubset(cand_tokens):
            return True

        # 3. Common semantic aliases
        aliases = {
            "yes": {"yes", "authorized", "i am", "eligible", "true", "i agree", "agree"},
            "no": {"no", "not", "i am not", "none", "false", "do not", "will not"},
            "bachelor": {"bachelor", "bachelors", "undergraduate", "b a", "b s", "ba", "bs"},
            "master": {"master", "masters", "graduate", "m a", "m s", "ma", "ms", "mba"},
            "doctorate": {"doctorate", "phd", "doctoral"},
            "not veteran": {"not a veteran", "not a protected veteran", "i am not a", "neither"},
            "no disability": {"no i do not have a disability", "no disability", "not disabled"},
            "decline": {"decline", "prefer not to say", "choose not to disclose", "i do not wish"},
        }

        for root, group in aliases.items():
            if any(t in norm_targ for t in group) and any(c in norm_cand for c in group):
                return True

        return False
    except Exception:
        return False


def resolve_combobox_option(page_or_frame: Any,
                            control_element: Any,
                            target_value: str,
                            timeout_ms: int = 4000) -> dict:
    """Resolve and click a dropdown option across any custom ATS combobox widget.

    Executes a 4-tier strategy:
    1. Native <select> option selection.
    2. Click to open -> scan floating list items ([role='option'], li, .option).
    3. Type-to-filter search input -> select filtered item.
    4. Keyboard traversal (ArrowDown + Enter).

    Args:
        page_or_frame: Playwright Page or Frame.
        control_element: The dropdown trigger element or input locator.
        target_value: The desired answer text.
        timeout_ms: Maximum wait time in milliseconds.

    Returns:
        dict: {"success": bool, "strategy": str, "matched_text": str, "error": str}
        Never raises.
    """
    result = {"success": False, "strategy": "none", "matched_text": "", "error": ""}
    if not control_element or not target_value:
        result["error"] = "missing-control-or-value"
        return result

    try:
        tag_name = ""
        try:
            tag_name = (control_element.evaluate("el => el.tagName.toLowerCase()") or "")
        except Exception:
            pass

        # Strategy 1: Native HTML <select>
        if tag_name == "select":
            try:
                control_element.select_option(label=target_value, timeout=timeout_ms // 2)
                result["success"] = True
                result["strategy"] = "native-select-label"
                result["matched_text"] = target_value
                return result
            except Exception:
                try:
                    control_element.select_option(value=target_value, timeout=timeout_ms // 2)
                    result["success"] = True
                    result["strategy"] = "native-select-value"
                    result["matched_text"] = target_value
                    return result
                except Exception:
                    pass

        # Strategy 2: ARIA Combobox / Click-to-open
        try:
            control_element.scroll_into_view_if_needed(timeout=1500)
        except Exception:
            pass

        # For React Select / custom shell controls, find the interactive trigger button
        try:
            trigger_node = control_element.evaluate_handle(
                "el => el.closest('.select-shell')?.querySelector('.select__control') || "
                "el.closest('.select__control') || "
                "el.closest('.react-select__control') || "
                "el"
            ).as_element()
            click_target = trigger_node or control_element
        except Exception:
            click_target = control_element

        try:
            click_target.click(timeout=2000)
        except Exception:
            try:
                click_target.evaluate("el => el.click()")
            except Exception as exc:
                result["error"] = f"click-failed: {exc}"
                return result

        # Wait briefly for popup menu to appear
        try:
            if hasattr(page_or_frame, "wait_for_timeout"):
                page_or_frame.wait_for_timeout(400)
        except Exception:
            pass

        # Candidate option selectors across popular ATS frameworks
        option_selectors = [
            "[role='option']",
            ".select__option",
            "[class*='select__option']",
            ".select__menu div",
            "li[role='option']",
            "ul[role='listbox'] li",
            "div[role='listbox'] div",
            ".select-dropdown-item",
            ".dropdown-item",
            "li.select2-results__option",
            "[data-automation-id*='promptOption']",
            "li",
        ]

        found_option = None
        matched_label = ""

        # Scan for matching option in page / frame context
        for opt_sel in option_selectors:
            try:
                candidates = page_or_frame.query_selector_all(opt_sel)
                if not candidates:
                    continue

                for cand in candidates:
                    try:
                        # Only consider visible options
                        if hasattr(cand, "is_visible") and not cand.is_visible():
                            continue
                        text = (cand.inner_text() or cand.get_attribute("title")
                                or cand.get_attribute("aria-label") or "").strip()
                        if text and matches_dropdown_option(text, target_value):
                            found_option = cand
                            matched_label = text
                            break
                    except Exception:
                        continue

                if found_option is not None:
                    break
            except Exception:
                continue

        if found_option is not None:
            try:
                found_option.click(timeout=2000)
                result["success"] = True
                result["strategy"] = "aria-combobox-click"
                result["matched_text"] = matched_label
                return result
            except Exception:
                try:
                    found_option.evaluate("el => el.click()")
                    result["success"] = True
                    result["strategy"] = "aria-combobox-eval-click"
                    result["matched_text"] = matched_label
                    return result
                except Exception as exc:
                    result["error"] = f"option-click-failed: {exc}"

        # Strategy 3: Type-to-filter (searchable input)
        try:
            if tag_name in ("input", "textarea") or control_element.get_attribute("contenteditable"):
                clean_query = re.sub(r"[^\w\s]", "", str(target_value))[:15].strip()
                if clean_query:
                    control_element.fill(clean_query)
                    if hasattr(page_or_frame, "wait_for_timeout"):
                        page_or_frame.wait_for_timeout(300)
                    # Check if filtered options appeared
                    for opt_sel in option_selectors[:4]:
                        filtered = page_or_frame.query_selector_all(opt_sel)
                        for f_opt in filtered:
                            if hasattr(f_opt, "is_visible") and not f_opt.is_visible():
                                continue
                            f_text = (f_opt.inner_text() or "").strip()
                            if f_text and matches_dropdown_option(f_text, target_value):
                                f_opt.click(timeout=1500)
                                result["success"] = True
                                result["strategy"] = "type-to-filter"
                                result["matched_text"] = f_text
                                return result
        except Exception:
            pass

        # Strategy 4: Keyboard traversal fallback
        try:
            control_element.press("ArrowDown")
            if hasattr(page_or_frame, "wait_for_timeout"):
                page_or_frame.wait_for_timeout(200)
            control_element.press("Enter")
            result["success"] = True
            result["strategy"] = "keyboard-traversal"
            result["matched_text"] = target_value
            return result
        except Exception:
            pass

        result["error"] = f"option-not-found: {target_value}"
        return result
    except Exception as exc:
        result["error"] = f"unhandled-exception: {exc}"
        return result
