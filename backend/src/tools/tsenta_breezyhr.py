"""Breezy HR URL, public form, closed-job, and receipt helpers."""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit


BREEZYHR_FORM_SELECTOR = (
    "input[name='cName'], input[name='cEmail']"
)

BREEZYHR_APPLY_LINK_SELECTOR = (
    "a[href*='.breezy.hr/p/'][href$='/apply'], "
    "a[href$='/apply']:has-text('Apply to Position'), "
    "a:has-text('Apply To Position')"
)

BREEZYHR_CONFIRM_SELECTORS = (
    ".application-submitted",
    "[data-testid='application-success']",
    "[aria-label='Application submitted']",
    ".position-application-success",
)

_CONFIRM_PATTERNS = (
    re.compile(r"\byour application has been submitted\b", re.I),
    re.compile(r"\bwe (?:have )?received your application\b", re.I),
    re.compile(r"\bthank you for applying\b", re.I),
    re.compile(r"\bapplication submitted successfully\b", re.I),
)

_CLOSED_PATTERNS = (
    "this position is no longer accepting applications",
    "this position is no longer available",
    "this job is no longer available",
    "position has been filled",
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


def breezyhr_url_candidates(url: str) -> list:
    """Return safe Breezy HR posting and canonical application candidates.

    Args:
        url: possible Breezy HR posting/application URL.

    Returns:
        list: original, clean, and `/apply` candidates when applicable.
        Invalid input returns an empty list.
    """
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return []
        original = urlunsplit(parts)
        if not parts.hostname.lower().endswith(".breezy.hr"):
            return [original]
        path = re.sub(r"/+$", "", parts.path)
        clean = urlunsplit((parts.scheme, parts.netloc, path, "", ""))
        candidates = [original, clean]
        if re.search(r"/p/[^/]+$", path, re.I):
            candidates.append(urlunsplit(
                (parts.scheme, parts.netloc, path + "/apply", "", "")))
        return list(dict.fromkeys(item for item in candidates if item))
    except Exception:
        return []


def breezyhr_apply_url(page) -> str:
    """Extract a Breezy-owned `/apply` URL from a posting page.

    Args:
        page: Playwright-compatible page.

    Returns:
        str: absolute HTTPS application URL, or ``""`` when absent.
    """
    try:
        link = page.query_selector(BREEZYHR_APPLY_LINK_SELECTOR)
        href = (link.get_attribute("href") or "").strip() if link else ""
        absolute = urljoin(str(getattr(page, "url", "") or ""), href)
        parts = urlsplit(absolute)
        if (parts.scheme == "https" and parts.hostname
                and parts.hostname.lower().endswith(".breezy.hr")
                and re.search(r"/p/[^/]+/apply/?$", parts.path, re.I)):
            return absolute
    except Exception:
        pass
    return ""


def breezyhr_job_closed(page) -> bool:
    """Return whether Breezy explicitly reports the position closed.

    Args:
        page: Playwright-compatible page.

    Returns:
        bool: true for a known closed-position message; false on uncertainty.
    """
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").lower()[:5000]
        return any(pattern in text for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def breezyhr_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture Breezy-owned submission evidence.

    Args:
        page: Playwright-compatible page after a submit click.
        timeout_ms: maximum wait budget in milliseconds.

    Returns:
        dict: structured receipt. Bare “thank you” text is insufficient.
    """
    receipt = {
        "confirmed": False,
        "ats": "breezyhr",
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
    for selector in BREEZYHR_CONFIRM_SELECTORS:
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
