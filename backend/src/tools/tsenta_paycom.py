"""Paycom guest preflight, application routing, and receipt helpers."""

from __future__ import annotations

import re
import time
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit


PAYCOM_APPLY_BUTTON_SELECTOR = (
    "button[data-testid='Apply-loadingbutton'], button:has-text('Apply')"
)

PAYCOM_PREFLIGHT_SELECTOR = (
    "input[name='firstName'], input[name='lastName'], input[name='email'], "
    "input[name='confirmEmail']"
)

PAYCOM_FORM_SELECTOR = (
    PAYCOM_PREFLIGHT_SELECTOR + ", input[type='file'], textarea, select, "
    "[role='radiogroup'], [data-testid*='question' i]"
)

PAYCOM_CONTINUE_SELECTOR = (
    "button:has-text('Continue To Application'), "
    "button:has-text('Continue to Application')"
)

PAYCOM_CONFIRM_SELECTORS = (
    "[data-testid*='application-confirmation' i]",
    "[data-testid*='application-success' i]",
    "[class*='application-confirmation' i]",
)

_CLOSED_PATTERNS = (
    "this position is no longer available",
    "this job is no longer available",
    "no longer accepting applications",
    "the job you are looking for could not be found",
)

_CONFIRM_PATTERNS = (
    re.compile(r"\byour application has been submitted\b", re.I),
    re.compile(r"\bwe (?:have )?received your application\b", re.I),
    re.compile(r"\bthank you for (?:submitting )?your application\b", re.I),
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


def paycom_url_candidates(url: str) -> list:
    """Return modern and legacy candidates for a Paycom job URL.

    Args:
        url: Paycom legacy ``ViewJobDetails`` or modern portal URL.

    Returns:
        list: modern portal route first when client and job ids are present,
        followed by the original URL. Invalid input returns an empty list.
        The function never raises.
    """
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        if (parts.scheme not in ("http", "https") or
                not (host == "paycomonline.net" or host.endswith(".paycomonline.net"))):
            return []
        original = urlunsplit(parts)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        job_id = str(query.get("job") or "").strip()
        client_key = str(query.get("clientkey") or "").strip()
        candidates = []
        if job_id and client_key:
            candidates.append(urlunsplit((
                parts.scheme, parts.netloc,
                f"/v4/ats/web.php/portal/{client_key}/jobs/{job_id}", "", "",
            )))
        candidates.append(original)
        return list(dict.fromkeys(item for item in candidates if item))
    except Exception:
        return []


def paycom_dismiss_cookie_notice(page) -> bool:
    """Close Paycom's cookie notice without accepting optional cookies.

    Args:
        page: Playwright-compatible page.

    Returns:
        bool: true when the exact dismiss control was clicked. Never raises.
    """
    try:
        body = page.locator("body").inner_text(timeout=1500) or ""
        if "website uses cookies" not in body.lower():
            return False
        buttons = page.query_selector_all("button")
        for button in buttons:
            try:
                if (button.inner_text() or "").strip() != "X" or not button.is_visible():
                    continue
                try:
                    button.click(timeout=3000)
                except TypeError:
                    button.click()
                return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def paycom_job_closed(page) -> bool:
    """Return whether Paycom explicitly reports a closed or missing job.

    Args:
        page: Playwright-compatible page.

    Returns:
        bool: true only for a known closed-job message. Never raises.
    """
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").lower()[:8000]
        return any(pattern in text for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def paycom_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture Paycom-owned confirmation evidence after explicit submission.

    Args:
        page: Playwright-compatible page after submit.
        timeout_ms: bounded wait budget in milliseconds.

    Returns:
        dict: structured receipt. Generic gratitude text is accepted only on
        an application confirmation route. Never raises.
    """
    receipt = {
        "confirmed": False,
        "ats": "paycom",
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
    for selector in PAYCOM_CONFIRM_SELECTORS:
        try:
            node = page.query_selector(selector)
            if node is not None and (not hasattr(node, "is_visible") or node.is_visible()):
                receipt["signals"].append({"kind": "selector", "value": selector})
                receipt["confirmationText"] = (node.inner_text() or "").strip()[:2000]
                break
        except Exception:
            continue
    body = ""
    title = ""
    try:
        body = page.locator("body").inner_text(timeout=min(timeout_ms, 4000)) or ""
        title = str(page.title() or "")
    except Exception:
        pass
    context = bool(re.search(
        r"application[-_/]?(?:confirmation|complete|submitted)|confirmation",
        receipt["url"] + " " + title, re.I))
    if context:
        for pattern in _CONFIRM_PATTERNS:
            match = pattern.search(body)
            if match:
                receipt["signals"].append({"kind": "context+text",
                                           "value": match.group(0)})
                if not receipt["confirmationText"]:
                    start = max(0, match.start() - 120)
                    receipt["confirmationText"] = body[
                        start:match.end() + 240].strip()[:2000]
                break
    reference = re.search(
        r"(?:confirmation|application|reference)\s*(?:id|number|#)\s*[:#-]?\s*"
        r"([A-Z0-9-]{5,40})", receipt["confirmationText"], re.I)
    if reference:
        receipt["confirmationId"] = reference.group(1)
    receipt["confirmed"] = bool(receipt["signals"])
    return receipt
