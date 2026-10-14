"""SAP SuccessFactors career routing, account gates, and receipt evidence.

SuccessFactors has both classic ``career*.successfactors`` pages and branded
career domains.  Most employers require a tenant-specific candidate account
before the application form.  Nori identifies that checkpoint explicitly and
reuses its per-ATS browser state on later runs instead of mistaking a login or
account-creation form for a completed application draft.
"""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlsplit, urlunsplit


SUCCESSFACTORS_APPLY_BUTTON_SELECTOR = (
    "#applyButton_top, #applyButton_bottom, a.dialogApplyBtn, "
    "a:has-text('Apply now'), button:has-text('Apply')"
)

SUCCESSFACTORS_FORM_SELECTOR = (
    "input[type='file'], textarea[name*='cover' i], "
    "input[id*='resume' i], [id*='application'] input, "
    "[data-testid*='application' i] input"
)

SUCCESSFACTORS_ACCOUNT_SELECTOR = (
    "input#fbclc_pwd, input[name='fbclc_pwd'], input[type='password'], "
    "form[action*='login' i]"
)

SUCCESSFACTORS_CONFIRM_SELECTORS = (
    "[id*='applicationConfirmation' i]",
    "[class*='application-confirmation' i]",
    "[aria-label*='application submitted' i]",
)

_CLOSED_PATTERNS = (
    "this job is no longer available",
    "this position is no longer available",
    "the job you are looking for is no longer open",
    "this job is no longer accepting applications",
    "the requisition is no longer available",
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


def successfactors_url_candidates(url: str) -> list:
    """Return safe SuccessFactors or branded-career URL candidates.

    Args:
        url: classic SuccessFactors URL or an exact HiringCafe-branded job URL.

    Returns:
        list: canonical URL followed by the original when distinct. Invalid or
        non-HTTPS input returns an empty list. The function never raises.
    """
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        if parts.scheme != "https" or not parts.hostname:
            return []
        original = urlunsplit(parts)
        canonical = urlunsplit((parts.scheme, parts.netloc, parts.path,
                                parts.query, ""))
        return list(dict.fromkeys(item for item in (canonical, original) if item))
    except Exception:
        return []


def successfactors_job_closed(page) -> bool:
    """Return whether the current SuccessFactors posting is explicitly closed."""
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").lower()[:8000]
        return any(pattern in text for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def successfactors_account_required(page) -> bool:
    """Return whether candidate sign-in or account creation is blocking apply."""
    try:
        credential = page.query_selector(SUCCESSFACTORS_ACCOUNT_SELECTOR)
        if credential is None or (hasattr(credential, "is_visible")
                                  and not credential.is_visible()):
            return False
        text = (page.locator("body").inner_text(timeout=2500) or "").lower()[:5000]
        title = str(page.title() or "").lower()
        return any(signal in text or signal in title for signal in (
            "already have an account", "please sign in", "choose password",
            "create an account", "career opportunities: sign in",
        ))
    except Exception:
        return False


def successfactors_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture strict SuccessFactors-owned evidence after an explicit submit.

    Args:
        page: Playwright-compatible page after submission.
        timeout_ms: bounded wait budget in milliseconds.

    Returns:
        dict: structured receipt. Generic gratitude text counts only on an
        application confirmation/complete route or title. Never raises.
    """
    receipt = {
        "confirmed": False,
        "ats": "successfactors",
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
    for selector in SUCCESSFACTORS_CONFIRM_SELECTORS:
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
