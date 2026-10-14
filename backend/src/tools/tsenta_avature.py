"""Avature branded-career routing, résumé-first flows, and receipt evidence."""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlsplit, urlunsplit


AVATURE_APPLY_SELECTOR = (
    "a[href*='JobDetailApply' i], a[href*='ApplicationMethods' i], "
    "a:has-text('Apply'), button:has-text('Apply')"
)

AVATURE_RESUME_METHOD_SELECTOR = (
    "#methodButton--file, a:has-text('From Device')"
)

AVATURE_FORM_SELECTOR = (
    "#manualRegisterMethodsForm input[type='file'], "
    "form input[autocomplete='given-name'], form input[name*='first' i], "
    "form textarea, form select"
)

AVATURE_ACCOUNT_SELECTOR = (
    "input#username, input[name='username'], input[type='password']"
)

AVATURE_CONFIRM_SELECTORS = (
    "[id*='applicationConfirmation' i]",
    "[class*='application-confirmation' i]",
    "[class*='application-success' i]",
)

_CLOSED_PATTERNS = (
    "this job is no longer available",
    "this position is no longer available",
    "this requisition is no longer available",
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


def avature_url_candidates(url: str) -> list:
    """Return canonical candidates for a known Avature branded-career route.

    Args:
        url: exact feed URL or an Avature job/application route.

    Returns:
        list: fragment-free HTTPS URL followed by the original when distinct.
        Unrelated paths and invalid input return an empty list. Never raises.
    """
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        path = parts.path.lower()
        valid_path = any(marker in path for marker in (
            "/jobdetail/", "/jobdetailapply", "/applicationmethods",
            "/register", "/careers/",
        ))
        if parts.scheme != "https" or not parts.hostname or not valid_path:
            return []
        original = urlunsplit(parts)
        canonical = urlunsplit((parts.scheme, parts.netloc, parts.path,
                                parts.query, ""))
        return list(dict.fromkeys(item for item in (canonical, original) if item))
    except Exception:
        return []


def avature_job_closed(page) -> bool:
    """Return whether the Avature-branded posting is explicitly closed."""
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").lower()[:8000]
        return any(pattern in text for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def avature_account_required(page) -> bool:
    """Return whether only registered-user credentials are available."""
    try:
        credential = page.query_selector(AVATURE_ACCOUNT_SELECTOR)
        if credential is None or (hasattr(credential, "is_visible")
                                  and not credential.is_visible()):
            return False
        guest = page.query_selector(
            AVATURE_RESUME_METHOD_SELECTOR + ", a[href*='/Register' i]")
        if guest is not None and (not hasattr(guest, "is_visible") or guest.is_visible()):
            return False
        text = (page.locator("body").inner_text(timeout=2500) or "").lower()[:3500]
        return ("already registered" in text or "forgot your password" in text
                or ("username" in text and "password" in text and "log in" in text))
    except Exception:
        return False


def avature_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture strict Avature-owned evidence after explicit submission."""
    receipt = {
        "confirmed": False,
        "ats": "avature",
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
    for selector in AVATURE_CONFIRM_SELECTORS:
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
