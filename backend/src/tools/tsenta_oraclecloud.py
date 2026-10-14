"""Oracle Recruiting (Oracle Cloud Candidate Experience) helpers.

Oracle job boards expose a public posting page and hand applications to an
email-first Candidate Experience route. The first application step contains a
real email field plus a consent checkbox; Nori can prepare the email field but
must leave the consent step for explicit user review.
"""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlsplit, urlunsplit


ORACLE_APPLY_BUTTON_SELECTOR = (
    "button.apply-now-button, a.apply-now-button, "
    "button:has-text('Apply Now'), a:has-text('Apply Now')"
)
ORACLE_EMAIL_SELECTOR = (
    "input[name='primary-email'][type='email'], "
    "input[id^='primary-email'][type='email'], "
    "input[autocomplete='email'][type='email']"
)
ORACLE_FORM_SELECTOR = (
    ORACLE_EMAIL_SELECTOR + ", input[id='legal-disclaimer-checkbox']"
)
ORACLE_CONSENT_SELECTOR = (
    "#legal-disclaimer-checkbox, input[name*='disclaimer' i], "
    "input[type='checkbox'][id*='legal' i]"
)
ORACLE_CONFIRM_SELECTORS = (
    "[data-automation-id='applicationSubmitted']",
    "[data-automation-id='confirmationPage']",
    "[data-testid='application-confirmation']",
    ".application-confirmation",
)

_CONFIRM_PATTERNS = (
    re.compile(r"\byour application has been submitted\b", re.I),
    re.compile(r"\bthank you for applying\b", re.I),
    re.compile(r"\bapplication submitted successfully\b", re.I),
    re.compile(r"\bwe (?:have )?received your application\b", re.I),
)
_CLOSED_PATTERNS = (
    re.compile(r"\bthis job is no longer available\b", re.I),
    re.compile(r"\bthis position is no longer available\b", re.I),
    re.compile(r"\bjob opening (?:was )?not found\b", re.I),
    re.compile(r"\bthe job you are looking for is no longer open\b", re.I),
)


def _decode(value: str) -> str:
    text = str(value or "").replace("&amp;", "&")
    for _ in range(3):
        try:
            decoded = unquote(text)
        except Exception:
            break
        if decoded == text:
            break
        text = decoded
    return text


def oraclecloud_url_candidates(url: str) -> list:
    """Return stable Oracle Candidate Experience URL candidates.

    Args:
        url: Oracle Cloud or Taleo posting URL.

    Returns:
        list: original URL followed by a query/hash-free equivalent where
        applicable. Invalid URLs return an empty list and never raise.
    """
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return []
        original = urlunsplit(parts)
        if "oraclecloud.com" not in parts.hostname.lower():
            return [original]
        clean = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        return list(dict.fromkeys(item for item in (original, clean) if item))
    except Exception:
        return []


def oraclecloud_job_closed(page) -> bool:
    """Return whether an Oracle posting explicitly reports closure.

    Args:
        page: Playwright page or compatible test double.

    Returns:
        bool: true only when a known closed-job phrase is visible.
    """
    try:
        body = (page.locator("body").inner_text(timeout=4000) or "")[:10000]
        return any(pattern.search(body) for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def oraclecloud_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture Oracle-owned application completion evidence.

    Args:
        page: Playwright page after an explicit submit.
        timeout_ms: bounded wait for the confirmation surface.

    Returns:
        dict: receipt with `confirmed`, ATS, signals, text, and optional id.
        A generic thank-you outside the Oracle application surface is ignored.
    """
    receipt = {
        "confirmed": False,
        "ats": "oraclecloud",
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
    for selector in ORACLE_CONFIRM_SELECTORS:
        try:
            node = page.query_selector(selector)
            if node is not None and (not hasattr(node, "is_visible") or node.is_visible()):
                receipt["signals"].append({"kind": "selector", "value": selector})
                receipt["confirmationText"] = (node.inner_text() or "").strip()[:2000]
                break
        except Exception:
            continue
    try:
        body = (page.locator("body").inner_text(
            timeout=min(timeout_ms, 5000)) or "").strip()
    except Exception:
        body = ""
    for pattern in _CONFIRM_PATTERNS:
        match = pattern.search(body)
        if match:
            receipt["signals"].append({"kind": "text", "value": match.group(0)})
            if not receipt["confirmationText"]:
                start = max(0, match.start() - 120)
                receipt["confirmationText"] = body[start:match.end() + 240].strip()[:2000]
            break
    receipt_match = re.search(
        r"(?:confirmation|application|reference)\s*(?:id|number|#)\s*[:#-]?\s*"
        r"([A-Z0-9-]{5,40})", receipt["confirmationText"], re.I)
    if receipt_match:
        receipt["confirmationId"] = receipt_match.group(1)
    receipt["confirmed"] = bool(receipt["signals"])
    return receipt
