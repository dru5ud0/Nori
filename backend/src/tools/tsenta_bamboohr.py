"""BambooHR career-page, application-form, and receipt helpers."""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlsplit, urlunsplit


BAMBOOHR_FORM_SELECTOR = (
    "form input[name='firstName'], form input[name='lastName'], "
    "form input[name='email'], form input[aria-label='file-input']"
)

BAMBOOHR_CONFIRM_SELECTORS = (
    "[data-testid='application-success']",
    "[data-testid='application-confirmation']",
    "[aria-label='Application submitted']",
    ".posting-submit-success",
)

_CONFIRM_PATTERNS = (
    re.compile(r"\byour application has been submitted\b", re.I),
    re.compile(r"\bapplication submitted successfully\b", re.I),
    re.compile(r"\bwe (?:have )?received your application\b", re.I),
    re.compile(r"\bthank you for (?:your interest|applying)\b", re.I),
)

_CLOSED_PATTERNS = (
    re.compile(r"\bthis job is no longer available\b", re.I),
    re.compile(r"\bthis position is no longer available\b", re.I),
    re.compile(r"\bjob opening (?:was )?not found\b", re.I),
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


def bamboohr_url_candidates(url: str) -> list:
    """Return original and clean BambooHR career-posting URLs."""
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return []
        original = urlunsplit(parts)
        if not parts.hostname.lower().endswith(".bamboohr.com"):
            return [original]
        segments = [segment for segment in parts.path.split("/") if segment]
        candidates = [original]
        if len(segments) >= 2 and segments[0].lower() == "careers":
            clean = f"{parts.scheme}://{parts.netloc}/careers/{segments[1]}"
            candidates.append(clean)
        return list(dict.fromkeys(item for item in candidates if item))
    except Exception:
        return []


def bamboohr_job_closed(page) -> bool:
    """Return whether BambooHR explicitly reports a missing/closed posting."""
    try:
        body = (page.locator("body").inner_text(timeout=4000) or "")[:8000]
        return any(pattern.search(body) for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def bamboohr_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture BambooHR-owned application completion evidence."""
    receipt = {
        "confirmed": False,
        "ats": "bamboohr",
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
    for selector in BAMBOOHR_CONFIRM_SELECTORS:
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
