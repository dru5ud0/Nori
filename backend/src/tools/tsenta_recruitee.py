"""Recruitee URL, application-form, closed-job, and receipt helpers."""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit


RECRUITEE_FORM_SELECTOR = "#offer-application-form, input[name='candidate.name']"

RECRUITEE_APPLY_LINK_SELECTOR = (
    "a[href$='/c/new'], a[href*='/o/'][href*='/c/new'], "
    "a:has-text('Apply for this job')"
)

RECRUITEE_CONFIRM_SELECTORS = (
    "[data-testid='application-success']",
    "[data-cy='application-success']",
    "[aria-label='Application sent']",
    ".application-success",
)

_CONFIRM_PATTERNS = (
    re.compile(r"\byour application has been (?:sent|submitted)\b", re.I),
    re.compile(r"\bwe (?:have )?received your application\b", re.I),
    re.compile(r"\bthank you for (?:your )?application\b", re.I),
    re.compile(r"\bapplication sent successfully\b", re.I),
)

_CLOSED_PATTERNS = (
    "this job is no longer available",
    "this position is no longer available",
    "this job is no longer accepting applications",
    "the job you are looking for is no longer open",
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


def recruitee_url_candidates(url: str) -> list:
    """Return normalized Recruitee posting and direct application URLs.

    Args:
        url: possible Recruitee posting/application URL.

    Returns:
        list: safe candidate URLs, including the documented `/c/new` form
        route for a posting. Invalid input returns an empty list.
    """
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return []
        original = urlunsplit(parts)
        if not parts.hostname.lower().endswith(".recruitee.com"):
            return [original]
        path = re.sub(r"/+$", "", parts.path)
        clean = urlunsplit((parts.scheme, parts.netloc, path, "", ""))
        candidates = [original, clean]
        if re.search(r"/o/[^/]+$", path, re.I):
            candidates.append(urlunsplit(
                (parts.scheme, parts.netloc, path + "/c/new", "", "")))
        return list(dict.fromkeys(item for item in candidates if item))
    except Exception:
        return []


def recruitee_apply_url(page) -> str:
    """Extract an HTTPS Recruitee-owned direct application URL.

    Args:
        page: Playwright-compatible posting page.

    Returns:
        str: absolute `/o/<job>/c/new` URL, or ``""`` when absent.
    """
    try:
        link = page.query_selector(RECRUITEE_APPLY_LINK_SELECTOR)
        href = (link.get_attribute("href") or "").strip() if link else ""
        absolute = urljoin(str(getattr(page, "url", "") or ""), href)
        parts = urlsplit(absolute)
        if (parts.scheme == "https" and parts.hostname
                and parts.hostname.lower().endswith(".recruitee.com")
                and re.search(r"/o/[^/]+/c/new/?$", parts.path, re.I)):
            return absolute
    except Exception:
        pass
    return ""


def recruitee_job_closed(page) -> bool:
    """Return whether Recruitee explicitly reports the posting closed.

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


def recruitee_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture Recruitee-owned evidence after a submission attempt.

    Args:
        page: Playwright-compatible page after a submit click.
        timeout_ms: maximum wait budget in milliseconds.

    Returns:
        dict: structured receipt. Generic gratitude alone is not accepted.
    """
    receipt = {
        "confirmed": False,
        "ats": "recruitee",
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
    for selector in RECRUITEE_CONFIRM_SELECTORS:
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
