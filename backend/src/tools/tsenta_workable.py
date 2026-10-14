"""Workable application URL, form, and confirmation helpers."""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlsplit, urlunsplit


WORKABLE_FORM_SELECTOR = (
    "form input[name='firstname'], "
    "form input[name='lastname'], "
    "form input[name='email'], "
    "form input[type='file']"
)

WORKABLE_CONFIRM_SELECTORS = (
    "[data-ui='application-success']",
    "[data-testid='application-success']",
    "[data-testid='application-submitted']",
    "[aria-label='Application submitted']",
    ".application-confirmation",
)

_CONFIRM_PATTERNS = (
    re.compile(r"\byour application has been submitted\b", re.I),
    re.compile(r"\bapplication submitted successfully\b", re.I),
    re.compile(r"\bwe (?:have )?received your application\b", re.I),
    re.compile(r"\bthank you for applying\b", re.I),
)

_CLOSED_PATTERNS = (
    re.compile(r"\bthis job is no longer available\b", re.I),
    re.compile(r"\bthis position is no longer available\b", re.I),
    re.compile(r"\bjob (?:is )?not found\b", re.I),
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


def workable_url_candidates(url: str) -> list:
    """Return original, dedicated application, and canonical Workable URLs."""
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return []
        original = urlunsplit(parts)
        if parts.hostname.lower() != "apply.workable.com":
            return [original]
        segments = [segment for segment in parts.path.split("/") if segment]
        candidates = [original]
        if len(segments) >= 3 and segments[1].lower() == "j":
            base = f"{parts.scheme}://{parts.netloc}/{segments[0]}/j/{segments[2]}"
            candidates.extend((base + "/apply/", base + "/"))
        return list(dict.fromkeys(item for item in candidates if item))
    except Exception:
        return []


def workable_job_closed(page) -> bool:
    """Return whether a Workable page explicitly says the posting is closed."""
    try:
        path = urlsplit(str(getattr(page, "url", "") or "")).path.lower()
        if "/not_found" in path or path.rstrip("/").endswith("/not-found"):
            return True
        body = (page.locator("body").inner_text(timeout=4000) or "")[:8000]
        return any(pattern.search(body) for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def workable_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture Workable-owned evidence that an application was submitted."""
    receipt = {
        "confirmed": False,
        "ats": "workable",
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
    try:
        path = urlsplit(receipt["url"]).path.lower()
        if re.search(r"/apply/(?:success|confirmation|submitted)/?$", path):
            receipt["signals"].append({"kind": "url", "value": path})
    except Exception:
        pass
    for selector in WORKABLE_CONFIRM_SELECTORS:
        try:
            node = page.query_selector(selector)
            if node is not None and (not hasattr(node, "is_visible") or node.is_visible()):
                receipt["signals"].append({"kind": "selector", "value": selector})
                receipt["confirmationText"] = (node.inner_text() or "").strip()[:2000]
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
                receipt["confirmationText"] = body_text[
                    start:match.end() + 240].strip()[:2000]
            break
    receipt_match = re.search(
        r"(?:confirmation|application|reference)\s*(?:id|number|#)\s*[:#-]?\s*"
        r"([A-Z0-9-]{5,40})", receipt["confirmationText"], re.I)
    if receipt_match:
        receipt["confirmationId"] = receipt_match.group(1)
    receipt["confirmed"] = bool(receipt["signals"])
    return receipt
