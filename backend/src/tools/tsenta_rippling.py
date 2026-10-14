"""Rippling ATS application URL, form, and confirmation helpers."""

from __future__ import annotations

import re
import time
from urllib.parse import parse_qs, unquote, urlencode, urlsplit, urlunsplit


RIPPLING_FORM_SELECTOR = (
    "form input[data-testid='input-first_name'], "
    "form input[data-testid='input-last_name'], "
    "form input[data-testid='input-email']"
)

RIPPLING_CONFIRM_SELECTORS = (
    "[data-testid='application-success']",
    "[data-testid='application-confirmation']",
    "[aria-label='Application submitted']",
    "[data-rippling-component='application-success']",
)

_CONFIRM_PATTERNS = (
    re.compile(r"\byour application has been submitted\b", re.I),
    re.compile(r"\bapplication submitted successfully\b", re.I),
    re.compile(r"\bwe (?:have )?received your application\b", re.I),
    re.compile(r"\bthank you for applying\b", re.I),
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


def rippling_url_candidates(url: str) -> list:
    """Return original, dedicated apply, and canonical Rippling posting URLs."""
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return []
        original = urlunsplit(parts)
        if parts.hostname.lower() != "ats.rippling.com":
            return [original]
        segments = [segment for segment in parts.path.split("/") if segment]
        jobs_index = next((i for i, segment in enumerate(segments)
                           if segment.lower() == "jobs"), -1)
        candidates = [original]
        if jobs_index > 0 and len(segments) > jobs_index + 1:
            prefix = "/".join(segments[:jobs_index])
            slug = segments[jobs_index - 1]
            job_id = segments[jobs_index + 1]
            base = f"{parts.scheme}://{parts.netloc}/{prefix}/jobs/{job_id}"
            query = urlencode({"jobBoardSlug": slug, "jobId": job_id,
                               "step": "application"})
            candidates.extend((base + "/apply?" + query, base))
        return list(dict.fromkeys(item for item in candidates if item))
    except Exception:
        return []


def rippling_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture Rippling-owned application completion evidence."""
    receipt = {
        "confirmed": False,
        "ats": "rippling",
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
        query = parse_qs(urlsplit(receipt["url"]).query)
        step = str((query.get("step") or [""])[0]).lower()
        if step in ("confirmation", "submitted", "success"):
            receipt["signals"].append({"kind": "url", "value": "step=" + step})
    except Exception:
        pass
    for selector in RIPPLING_CONFIRM_SELECTORS:
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
