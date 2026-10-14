"""JazzHR/Resumator URL, form, and confirmation helpers."""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlsplit, urlunsplit


JAZZHR_FORM_SELECTOR = (
    "form#form_submit_new_resume, "
    "input#resumator-firstname-value, input#resumator-email-value, "
    "input#resumator-resume-value"
)

JAZZHR_CONFIRM_SELECTORS = (
    "#resumator-thank-you",
    ".resumator-thank-you",
    ".thank-you-message",
    "[data-testid='application-confirmation']",
)

_CONFIRM_PATTERNS = (
    re.compile(r"\bthank you for applying\b", re.I),
    re.compile(r"\byour application has been (?:received|submitted)\b", re.I),
    re.compile(r"\bwe (?:have )?received your application\b", re.I),
    re.compile(r"\bapplication submitted successfully\b", re.I),
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


def jazzhr_url_candidates(url: str) -> list:
    """Return original and clean JazzHR application URLs."""
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return []
        original = urlunsplit(parts)
        if not parts.hostname.lower().endswith(".applytojob.com"):
            return [original]
        clean = urlunsplit((parts.scheme, parts.netloc,
                            re.sub(r"/+$", "", parts.path), "", ""))
        return list(dict.fromkeys(item for item in (original, clean) if item))
    except Exception:
        return []


def jazzhr_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture JazzHR-owned application completion evidence."""
    receipt = {
        "confirmed": False,
        "ats": "jazzhr",
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
    for selector in JAZZHR_CONFIRM_SELECTORS:
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
                receipt["confirmationText"] = body_text[start:match.end() + 240].strip()[:2000]
            break
    receipt_match = re.search(
        r"(?:confirmation|application|reference)\s*(?:id|number|#)\s*[:#-]?\s*([A-Z0-9-]{5,40})",
        receipt["confirmationText"], re.I)
    if receipt_match:
        receipt["confirmationId"] = receipt_match.group(1)
    receipt["confirmed"] = bool(receipt["signals"])
    return receipt
