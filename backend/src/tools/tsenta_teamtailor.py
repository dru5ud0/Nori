"""Teamtailor application-overlay, closed-job, and receipt helpers."""

from __future__ import annotations

import re
import time


TEAMTAILOR_FORM_SELECTOR = (
    "#job-application-form, input[name='candidate[first_name]'], "
    "input[name='candidate[email]']"
)

TEAMTAILOR_APPLY_BUTTON_SELECTOR = (
    "button[data-action*='form-overlay#showFormOverlay'], "
    "button:has-text('Apply for this job')"
)

TEAMTAILOR_CONFIRM_SELECTORS = (
    "[data-testid='application-success']",
    "[data-controller='careersite--application-success']",
    "#application-success",
    ".application-success",
)

_CONFIRM_PATTERNS = (
    re.compile(r"\byour application has been (?:sent|submitted)\b", re.I),
    re.compile(r"\bwe (?:have )?received your application\b", re.I),
    re.compile(r"\bthank you for (?:your )?application\b", re.I),
    re.compile(r"\bapplication submitted successfully\b", re.I),
)

_CLOSED_PATTERNS = (
    "this job is no longer available",
    "this position is no longer available",
    "this job is no longer accepting applications",
    "the application period has ended",
)


def teamtailor_job_closed(page) -> bool:
    """Return whether Teamtailor explicitly reports the posting closed.

    Args:
        page: Playwright-compatible page.

    Returns:
        bool: true only for a known closed-position message.
    """
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").lower()[:7000]
        return any(pattern in text for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def teamtailor_open_application(page, timeout_ms: int = 12000) -> bool:
    """Open Teamtailor's application modal without accepting cookie choices.

    Args:
        page: Playwright-compatible Teamtailor job page.
        timeout_ms: maximum wait budget in milliseconds.

    Returns:
        bool: true when the scoped application form becomes visible.
    """
    try:
        existing = page.query_selector("#job-application-form")
        if existing is not None and (not hasattr(existing, "is_visible")
                                     or existing.is_visible()):
            setattr(page, "_nori_scope_selector", "#job-application-form")
            return True
    except Exception:
        pass
    try:
        button = page.query_selector(TEAMTAILOR_APPLY_BUTTON_SELECTOR)
        if button is None:
            return False
        try:
            button.click(timeout=min(timeout_ms, 5000))
        except TypeError:
            button.click()
        page.wait_for_selector(TEAMTAILOR_FORM_SELECTOR,
                               timeout=min(timeout_ms, 12000))
        setattr(page, "_nori_scope_selector", "#job-application-form")
        return True
    except Exception:
        return False


def teamtailor_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture Teamtailor-owned evidence after a submission attempt.

    Args:
        page: Playwright-compatible page after submit.
        timeout_ms: maximum wait budget in milliseconds.

    Returns:
        dict: structured receipt. Bare generic gratitude is insufficient.
    """
    receipt = {
        "confirmed": False,
        "ats": "teamtailor",
        "capturedAt": int(time.time() * 1000),
        "url": str(getattr(page, "url", "") or ""),
        "signals": [],
        "confirmationText": "",
        "confirmationId": "",
    }
    try:
        page.wait_for_load_state("domcontentloaded", timeout=min(timeout_ms, 8000))
    except Exception:
        pass
    for selector in TEAMTAILOR_CONFIRM_SELECTORS:
        try:
            node = page.query_selector(selector)
            if node is not None and (not hasattr(node, "is_visible") or node.is_visible()):
                receipt["signals"].append({"kind": "selector", "value": selector})
                try:
                    receipt["confirmationText"] = (node.inner_text() or "").strip()[:2000]
                except Exception:
                    pass
                break
        except Exception:
            continue
    body_text = ""
    try:
        body_text = (page.locator("body").inner_text(
            timeout=min(timeout_ms, 5000)) or "").strip()
    except Exception:
        pass
    for pattern in _CONFIRM_PATTERNS:
        match = pattern.search(body_text)
        if match:
            receipt["signals"].append({"kind": "text", "value": match.group(0)})
            if not receipt["confirmationText"]:
                start = max(0, match.start() - 120)
                receipt["confirmationText"] = body_text[start:match.end() + 240].strip()[:2000]
            break
    receipt_match = re.search(
        r"(?:confirmation|application|reference)\s*(?:id|number|#)\s*[:#-]?\s*([A-Z0-9-]{5,40})",
        receipt["confirmationText"], re.I)
    if receipt_match:
        receipt["confirmationId"] = receipt_match.group(1)
    receipt["confirmed"] = bool(receipt["signals"])
    return receipt
