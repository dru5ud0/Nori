"""SmartRecruiters OneClick URL, challenge, form, and receipt helpers."""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlsplit, urlunsplit


SMARTRECRUITERS_APPLY_LINK_SELECTOR = (
    "a.js-oneclick[href*='/oneclick-ui/'], "
    "a#st-apply[href*='/oneclick-ui/'], "
    "a[href*='jobs.smartrecruiters.com/oneclick-ui/']"
)

SMARTRECRUITERS_FORM_SELECTOR = (
    "form input[name='firstName'], form input[name='lastName'], "
    "form input[name='email'], form input[autocomplete='given-name'], "
    "form input[type='email'][required]"
)

SMARTRECRUITERS_CONFIRM_SELECTORS = (
    "[data-testid='application-success']",
    "[data-testid='application-submitted']",
    "[data-test='application-success']",
    "[aria-label='Application submitted']",
)

_CONFIRM_PATTERNS = (
    re.compile(r"\byour application has been submitted\b", re.I),
    re.compile(r"\bthank you for applying\b", re.I),
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


def smartrecruiters_url_candidates(url: str) -> list:
    """Return normalized SmartRecruiters URLs without inventing publication ids."""
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return []
        original = urlunsplit(parts)
        if parts.hostname.lower() not in ("jobs.smartrecruiters.com", "www.smartr.me"):
            return [original]
        clean = urlunsplit((parts.scheme, parts.netloc,
                            re.sub(r"/+$", "", parts.path), "", ""))
        return list(dict.fromkeys(item for item in (original, clean) if item))
    except Exception:
        return []


def smartrecruiters_apply_url(page) -> str:
    """Extract the employer-provided OneClick apply URL from a posting page."""
    try:
        link = page.query_selector(SMARTRECRUITERS_APPLY_LINK_SELECTOR)
        href = (link.get_attribute("href") or "").strip() if link is not None else ""
        if href.startswith("https://") and "/oneclick-ui/" in href:
            return href
    except Exception:
        pass
    return ""


def smartrecruiters_challenge_present(page) -> bool:
    """Return whether SmartRecruiters' DataDome human challenge is active."""
    try:
        for frame in getattr(page, "frames", ()):
            url = str(getattr(frame, "url", "") or "").lower()
            if "captcha-delivery.com/captcha" in url or "datadome" in url:
                return True
    except Exception:
        pass
    try:
        return page.query_selector(
            "iframe[src*='captcha-delivery.com'], #datadome-captcha, "
            "[data-captcha-provider='datadome']") is not None
    except Exception:
        return False


def smartrecruiters_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture SmartRecruiters-owned application completion evidence."""
    receipt = {
        "confirmed": False,
        "ats": "smartrecruiters",
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
    for selector in SMARTRECRUITERS_CONFIRM_SELECTORS:
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
