"""iCIMS posting/apply iframe and confirmation helpers."""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit


ICIMS_APPLY_LINK_SELECTOR = (
    "a.iCIMS_ApplyOnlineButton[href*='mode=apply'], "
    "a[href*='apply=yes'][href*='in_iframe=1'], "
    "a:has-text('Apply for this job online')"
)

ICIMS_FORM_SELECTOR = (
    "input[name='css_loginName'][type='email'], "
    "input[name*='PersonProfileFields'], input[name*='rcf'], "
    "input[name*='icims' i], form input[type='email']"
)

ICIMS_CONFIRM_SELECTORS = (
    ".iCIMS_ApplicationConfirmation",
    ".iCIMS_Confirmation",
    "[data-testid='application-confirmation']",
    "[id*='application'][id*='confirmation' i]",
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


def icims_url_candidates(url: str) -> list:
    """Return original and clean iCIMS URLs without guessing requisitions."""
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return []
        original = urlunsplit(parts)
        if ".icims.com" not in parts.hostname.lower():
            return [original]
        clean = urlunsplit((parts.scheme, parts.netloc,
                            re.sub(r"/+$", "", parts.path), "", ""))
        return list(dict.fromkeys(item for item in (original, clean) if item))
    except Exception:
        return []


def icims_frame_with(page, selector: str):
    """Return the first page/frame containing a visible iCIMS selector."""
    try:
        surfaces = list(getattr(page, "frames", ()) or ())
        if page not in surfaces:
            surfaces.insert(0, page)
        for surface in surfaces:
            try:
                node = surface.query_selector(selector)
                if node is not None and (not hasattr(node, "is_visible") or node.is_visible()):
                    return surface
            except Exception:
                continue
    except Exception:
        pass
    return None


def icims_apply_url(page) -> str:
    """Extract the employer-provided iCIMS apply URL from the content iframe."""
    frame = icims_frame_with(page, ICIMS_APPLY_LINK_SELECTOR)
    if frame is None:
        return ""
    try:
        link = frame.query_selector(ICIMS_APPLY_LINK_SELECTOR)
        href = (link.get_attribute("href") or "").strip() if link is not None else ""
        return urljoin(str(getattr(frame, "url", "") or getattr(page, "url", "")), href)
    except Exception:
        return ""


def icims_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture iCIMS-owned application completion evidence across frames."""
    receipt = {
        "confirmed": False,
        "ats": "icims",
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
    surfaces = list(getattr(page, "frames", ()) or ())
    if page not in surfaces:
        surfaces.insert(0, page)
    for surface in surfaces:
        for selector in ICIMS_CONFIRM_SELECTORS:
            try:
                node = surface.query_selector(selector)
                if node is not None and (not hasattr(node, "is_visible") or node.is_visible()):
                    receipt["signals"].append({"kind": "selector", "value": selector})
                    receipt["confirmationText"] = (node.inner_text() or "").strip()[:2000]
                    break
            except Exception:
                continue
        body_text = ""
        try:
            body_text = (surface.locator("body").inner_text(
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
        if receipt["signals"]:
            break
    receipt_match = re.search(
        r"(?:confirmation|application|reference)\s*(?:id|number|#)\s*[:#-]?\s*([A-Z0-9-]{5,40})",
        receipt["confirmationText"], re.I)
    if receipt_match:
        receipt["confirmationId"] = receipt_match.group(1)
    receipt["confirmed"] = bool(receipt["signals"])
    return receipt
