"""Lever-specific URL, form, and confirmation helpers."""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlsplit, urlunsplit


LEVER_FORM_SELECTOR = (
    "form.application-form, form[action*='/apply'], "
    "[data-qa='application-form'], .application-form, "
    "input[name='name'][required], input[name='email'][required]"
)

LEVER_CONFIRM_SELECTORS = (
    "[data-qa='application-confirmation']",
    "[data-qa='application-success']",
    ".application-confirmation",
    ".postings-form-success",
    "[class*='application-success']",
)

_CONFIRM_PATTERNS = (
    re.compile(r"\bthank you for applying\b", re.I),
    re.compile(r"\bthank you for your application\b", re.I),
    re.compile(r"\byour application has been submitted\b", re.I),
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


def lever_url_candidates(url: str) -> list:
    """Return canonical Lever posting and apply URLs, original first."""
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        if parts.scheme not in ("http", "https") or host not in (
                "jobs.lever.co", "jobs.eu.lever.co"):
            return [urlunsplit(parts)] if parts.scheme and parts.hostname else []
        segments = [segment for segment in parts.path.split("/") if segment]
        candidates = [urlunsplit(parts)]
        if len(segments) >= 2:
            company, posting = segments[0], segments[1]
            base = f"{parts.scheme}://{parts.netloc}/{company}/{posting}"
            candidates.extend([base + "/apply", base])
        return list(dict.fromkeys(item.rstrip("/") for item in candidates if item))
    except Exception:
        return []


def lever_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture Lever-owned submission evidence from the resulting page."""
    receipt = {
        "confirmed": False,
        "ats": "lever",
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
    for selector in LEVER_CONFIRM_SELECTORS:
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
        body_text = (page.locator("body").inner_text(timeout=min(timeout_ms, 5000)) or "").strip()
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
