"""Workday-specific URL, form, navigation, and receipt helpers.

Workday candidate sites are single-page applications and their ordinary job
search controls also carry ``data-automation-id`` attributes.  The selectors
in this module deliberately require an apply-flow surface or an application
field so a search box is never mistaken for an application form.
"""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlsplit, urlunsplit


WORKDAY_HOST_MARKERS = (
    "myworkdayjobs.com",
    "workdaysite.com",
    "myworkdayjobs-impl.com",
)

WORKDAY_FORM_SELECTOR = (
    "form[data-automation-id='apply-form'], "
    "[data-automation-id='applyFlow'], "
    "[data-automation-id='applicationPage'], "
    "input[data-automation-id='legalNameSection_firstName'], "
    "input[data-automation-id='legalNameSection_lastName'], "
    "input[data-automation-id='email'][aria-required='true'], "
    "input[data-automation-id='phone-number'][aria-required='true']"
)

WORKDAY_SCOPE_SELECTOR = (
    "form[data-automation-id='apply-form'], "
    "[data-automation-id='applyFlow'], "
    "[data-automation-id='applicationPage']"
)

WORKDAY_CUSTOM_FIELD_SELECTOR = (
    "button[data-automation-id='select-widget-button'], "
    "button[data-automation-id='promptSearchButton'], "
    "button[role='combobox'], input[role='combobox']"
)

WORKDAY_NEXT_SELECTORS = (
    "button[data-automation-id='bottom-navigation-next-button']",
    "button[data-automation-id='pageFooterNextButton']",
    "button[data-automation-id='nextButton']",
)

WORKDAY_CONFIRM_SELECTORS = (
    "[data-automation-id='applicationSubmitted']",
    "[data-automation-id='confirmationPage']",
    "[data-automation-id='applicationConfirmation']",
    ".confirmation-message",
    "[data-automation-id*='confirmation' i]",
)

WORKDAY_LOGIN_SELECTORS = (
    "[data-automation-id='signInPage']",
    "[data-automation-id='signInContent']",
    "button[data-automation-id='signInSubmitButton']",
    "input[type='password']",
)

_CONFIRM_PATTERNS = (
    re.compile(r"\bapplication (?:has been )?submitted\b", re.I),
    re.compile(r"\bthank you for (?:submitting your application|applying)\b", re.I),
    re.compile(r"\bwe (?:have )?received your application\b", re.I),
    re.compile(r"\byour application is complete\b", re.I),
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


def workday_url_candidates(url: str) -> list:
    """Return safe Workday posting/apply URL candidates, original first.

    Query parameters commonly contain source attribution and are preserved on
    the original candidate.  The canonical posting and ``/apply`` candidates
    omit them because Workday tenants frequently reject deep apply URLs that
    contain tracking parameters.
    """
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        if parts.scheme not in ("http", "https") or not host:
            return []
        original = urlunsplit(parts)
        if not any(marker in host for marker in WORKDAY_HOST_MARKERS):
            return [original]
        path = re.sub(r"/+$", "", parts.path or "")
        posting = urlunsplit((parts.scheme, parts.netloc, path, "", ""))
        candidates = [original]
        if posting:
            candidates.append(posting)
            if "/job/" in path.lower() and not path.lower().endswith("/apply"):
                candidates.append(posting + "/apply")
        return list(dict.fromkeys(item for item in candidates if item))
    except Exception:
        return []


def workday_login_required(surface) -> bool:
    """Return whether a Workday sign-in/account gate is visibly blocking apply."""
    try:
        for selector in WORKDAY_LOGIN_SELECTORS:
            node = surface.query_selector(selector)
            if node is not None and (not hasattr(node, "is_visible") or node.is_visible()):
                return True
    except Exception:
        pass
    try:
        text = (surface.locator("body").inner_text(timeout=2500) or "").lower()[:6000]
        return bool(
            "sign in to your candidate account" in text
            or ("create account" in text and "forgot password" in text)
        )
    except Exception:
        return False


def workday_next_button(frame):
    """Return a visible enabled Workday intermediate-step control, or None.

    Workday may reuse its bottom navigation automation id on the final step.
    Controls whose text or automation id indicates submission are therefore
    excluded here; they remain available only to the separately guarded submit
    path.
    """
    try:
        for selector in WORKDAY_NEXT_SELECTORS:
            nodes = frame.query_selector_all(selector)
            for node in nodes:
                try:
                    text = (node.inner_text() or "").strip().lower()
                    automation_id = (node.get_attribute("data-automation-id") or "").lower()
                    if "submit" in text or "submit" in automation_id:
                        continue
                    if text and not re.search(
                            r"\b(next|continue|save\s*(?:&|and)\s*continue|review)\b", text, re.I):
                        continue
                    if node.is_visible() and (not hasattr(node, "is_enabled") or node.is_enabled()):
                        return node
                except Exception:
                    continue
    except Exception:
        return None
    return None


def workday_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture Workday-owned evidence that an application was submitted."""
    receipt = {
        "confirmed": False,
        "ats": "workday",
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
    for selector in WORKDAY_CONFIRM_SELECTORS:
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
