"""UKG Pro / UltiPro job routing, identity gates, and receipt evidence."""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlsplit, urlunsplit


ULTIPRO_APPLY_BUTTON_SELECTOR = (
    "ukg-button[data-automation='apply-now-button'], "
    "button[data-automation='apply-now-button'], button:has-text('Apply now')"
)

ULTIPRO_FORM_SELECTOR = (
    "input[type='file'], input[autocomplete='given-name'], "
    "input[autocomplete='family-name'], textarea, "
    "[data-automation*='application' i] input"
)

ULTIPRO_ACCOUNT_SELECTOR = (
    "input#username, input[name='username'], input[type='password'], "
    "form[action*='login' i]"
)

ULTIPRO_CONFIRM_SELECTORS = (
    "[data-automation*='application-confirmation' i]",
    "[data-automation*='application-success' i]",
    "[class*='application-confirmation' i]",
)

_CLOSED_PATTERNS = (
    "this job is no longer available",
    "this position is no longer available",
    "this opportunity is no longer available",
    "no longer accepting applications",
)

_CONFIRM_PATTERNS = (
    re.compile(r"\byour application has been submitted\b", re.I),
    re.compile(r"\bwe (?:have )?received your application\b", re.I),
    re.compile(r"\bthank you for (?:submitting )?your application\b", re.I),
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


def ultipro_url_candidates(url: str) -> list:
    """Return canonical HTTPS UKG Pro/UltiPro opportunity URL candidates."""
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        valid = (host == "ultipro.com" or host.endswith(".ultipro.com")
                 or host == "ukg.net" or host.endswith(".ukg.net"))
        if parts.scheme != "https" or not valid:
            return []
        original = urlunsplit(parts)
        canonical = urlunsplit((parts.scheme, parts.netloc, parts.path,
                                parts.query, ""))
        return list(dict.fromkeys(item for item in (canonical, original) if item))
    except Exception:
        return []


def ultipro_job_closed(page) -> bool:
    """Return whether UKG explicitly reports the opportunity as closed."""
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").lower()[:8000]
        return any(pattern in text for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def ultipro_account_required(page) -> bool:
    """Return whether UKG candidate sign-in/sign-up blocks the application."""
    try:
        url = str(getattr(page, "url", "") or "").lower()
        credential = page.query_selector(ULTIPRO_ACCOUNT_SELECTOR)
        if credential is None or (hasattr(credential, "is_visible")
                                  and not credential.is_visible()):
            return False
        text = (page.locator("body").inner_text(timeout=2500) or "").lower()[:3500]
        return ("signin-" in url or "/login" in url or
                ("email address" in text and "password" in text and
                 ("sign in" in text or "sign up" in text)))
    except Exception:
        return False


def ultipro_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture strict UKG-owned evidence after an explicit submit attempt."""
    receipt = {
        "confirmed": False,
        "ats": "ultipro",
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
    for selector in ULTIPRO_CONFIRM_SELECTORS:
        try:
            node = page.query_selector(selector)
            if node is not None and (not hasattr(node, "is_visible") or node.is_visible()):
                receipt["signals"].append({"kind": "selector", "value": selector})
                receipt["confirmationText"] = (node.inner_text() or "").strip()[:2000]
                break
        except Exception:
            continue
    body = ""
    title = ""
    try:
        body = page.locator("body").inner_text(timeout=min(timeout_ms, 4000)) or ""
        title = str(page.title() or "")
    except Exception:
        pass
    context = bool(re.search(
        r"application[-_/]?(?:confirmation|complete|submitted)|confirmation",
        receipt["url"] + " " + title, re.I))
    if context:
        for pattern in _CONFIRM_PATTERNS:
            match = pattern.search(body)
            if match:
                receipt["signals"].append({"kind": "context+text",
                                           "value": match.group(0)})
                if not receipt["confirmationText"]:
                    start = max(0, match.start() - 120)
                    receipt["confirmationText"] = body[
                        start:match.end() + 240].strip()[:2000]
                break
    reference = re.search(
        r"(?:confirmation|application|reference)\s*(?:id|number|#)\s*[:#-]?\s*"
        r"([A-Z0-9-]{5,40})", receipt["confirmationText"], re.I)
    if reference:
        receipt["confirmationId"] = reference.group(1)
    receipt["confirmed"] = bool(receipt["signals"])
    return receipt
