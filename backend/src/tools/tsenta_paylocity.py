"""Paylocity apply-route, form, closed-job, and receipt helpers."""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlsplit, urlunsplit


PAYLOCITY_FORM_SELECTOR = (
    "#appDetailDiv input[data-automation-id='infoFirstName'], "
    "#appDetailDiv input[id='info.firstName'], "
    "#appDetailDiv button[data-automation-id='btnNext']"
)

PAYLOCITY_SCOPE_SELECTOR = "#appDetailDiv"

PAYLOCITY_CONFIRM_SELECTORS = (
    "[data-automation-id='applicationConfirmation']",
    "[data-automation-id='applicationSubmitted']",
    "#application-confirmation",
    ".application-confirmation",
)

_CONFIRM_PATTERNS = (
    re.compile(r"\byour application has been submitted\b", re.I),
    re.compile(r"\bwe (?:have )?received your application\b", re.I),
    re.compile(r"\bthank you for (?:submitting )?your application\b", re.I),
)

_CLOSED_PATTERNS = (
    "this job is no longer available",
    "this position is no longer available",
    "this job is no longer accepting applications",
    "the position you are looking for is no longer available",
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


def paylocity_url_candidates(url: str) -> list:
    """Return normalized Paylocity posting and direct application URLs.

    Args:
        url: possible Paylocity job or application URL.

    Returns:
        list: safe URL candidates with the direct apply route first when a
        numeric job id is present; invalid input returns an empty list.
    """
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        if parts.scheme not in ("http", "https") or not host:
            return []
        original = urlunsplit(parts)
        if host != "recruiting.paylocity.com":
            return [original]
        match = re.search(
            r"/recruiting/jobs/(?:details|apply)/(\d+)(?:/.*)?$",
            parts.path, re.I)
        if not match:
            return [original]
        job_id = match.group(1)
        apply_url = urlunsplit((parts.scheme, parts.netloc,
                                f"/Recruiting/jobs/Apply/{job_id}", "", ""))
        clean = urlunsplit((parts.scheme, parts.netloc,
                            re.sub(r"/+$", "", parts.path), "", ""))
        return list(dict.fromkeys((apply_url, original, clean)))
    except Exception:
        return []


def paylocity_job_closed(page) -> bool:
    """Return whether Paylocity explicitly reports the posting unavailable.

    Args:
        page: Playwright-compatible page.

    Returns:
        bool: true only for a known closed-job message.
    """
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").lower()[:5000]
        return any(pattern in text for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def paylocity_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture Paylocity-owned evidence after a submission attempt.

    Args:
        page: Playwright-compatible page after submit.
        timeout_ms: maximum wait budget in milliseconds.

    Returns:
        dict: structured receipt. A generic gratitude string by itself is not
        sufficient; evidence must be on a Paylocity application/confirmation
        route or in a Paylocity confirmation element.
    """
    receipt = {
        "confirmed": False,
        "ats": "paylocity",
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
    for selector in PAYLOCITY_CONFIRM_SELECTORS:
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
    route_is_confirmation = bool(re.search(
        r"/recruiting/jobs/(?:application)?confirmation(?:/|$|\?)",
        receipt["url"], re.I))
    if route_is_confirmation:
        for pattern in _CONFIRM_PATTERNS:
            match = pattern.search(body_text)
            if match:
                receipt["signals"].append({"kind": "route+text", "value": match.group(0)})
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
