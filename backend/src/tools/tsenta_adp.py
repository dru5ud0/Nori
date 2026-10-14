"""ADP career-site routing, account gates, and receipt evidence.

ADP currently exposes two public candidate experiences: the newer
``myjobs.adp.com/<tenant>/cx`` application and the classic Workforce Now
career center. Both normally require an ADP candidate identity before the
actual application form, so Nori preserves the browser session and reports a
specific account gate instead of pretending the sign-in form is an
application draft.
"""

from __future__ import annotations

import re
import time
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit


ADP_APPLY_BUTTON_SELECTOR = (
    "#recruitment_jobDescription_candidateApply, "
    "#recruitment_jobDescription_apply, "
    "button[data-testid*='apply' i], button:has-text('Apply')"
)

ADP_FORM_SELECTOR = (
    "form input[type='file'], form sdf-file-uploader, form sdf-upload, "
    "form input[autocomplete='given-name'], form input[autocomplete='family-name'], "
    "form textarea, form [data-automation-id*='question' i]"
)

ADP_AUTH_SELECTOR = (
    "sdf-input#userEmail, sdf-input[formcontrolname='userName'], "
    "form.login-form, input[type='password']"
)

ADP_CONFIRM_SELECTORS = (
    "[data-testid*='application-confirmation' i]",
    "[data-automation-id*='application-confirmation' i]",
    "[class*='application-confirmation' i]",
    "[id*='applicationConfirmation' i]",
)

_CLOSED_PATTERNS = (
    "we are no longer accepting applications for this position",
    "this job is no longer available",
    "this position is no longer available",
    "this job is no longer accepting applications",
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


def adp_url_candidates(url: str) -> list:
    """Return stable ADP job URL candidates without changing tenant identity.

    Args:
        url: Workforce Now or ``myjobs.adp.com`` job-detail URL.

    Returns:
        list: canonical URL followed by the original when distinct. Invalid
        input returns an empty list. The function never raises.
    """
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        if (parts.scheme not in ("http", "https") or
                host not in ("workforcenow.adp.com", "myjobs.adp.com")):
            return []
        original = urlunsplit(parts)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        if host == "myjobs.adp.com":
            req_id = str(query.get("reqId") or query.get("reqid") or "").strip()
            canonical_query = urlencode({"reqId": req_id}) if req_id else parts.query
        else:
            ordered = ((key, query[key]) for key in
                       ("cid", "ccId", "jobId", "lang", "source") if key in query)
            canonical_query = urlencode(list(ordered)) or parts.query
        canonical = urlunsplit((parts.scheme, parts.netloc, parts.path,
                                canonical_query, ""))
        return list(dict.fromkeys(item for item in (canonical, original) if item))
    except Exception:
        return []


def adp_dismiss_cookie_notice(page) -> bool:
    """Dismiss ADP's OneTrust notice without accepting optional cookies.

    Args:
        page: Playwright-compatible page.

    Returns:
        bool: true when the close control was clicked. Never raises or changes
        the user's cookie preferences.
    """
    try:
        button = page.query_selector(
            "#onetrust-banner-sdk button.onetrust-close-btn-handler[aria-label='Close']")
        if button is None or (hasattr(button, "is_visible") and not button.is_visible()):
            return False
        try:
            button.click(timeout=3000)
        except TypeError:
            button.click()
        return True
    except Exception:
        return False


def adp_job_closed(page) -> bool:
    """Return whether ADP explicitly reports that the posting is closed.

    Args:
        page: Playwright-compatible page.

    Returns:
        bool: true only for a known closed-posting message. Never raises.
    """
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").lower()[:8000]
        return any(pattern in text for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def adp_account_required(page) -> bool:
    """Return whether ADP is waiting for candidate sign-in or registration.

    Args:
        page: Playwright-compatible page.

    Returns:
        bool: true for the ADP email/phone identity checkpoint or a credential
        form. The function never types, continues, or creates an account.
    """
    try:
        url = str(getattr(page, "url", "") or "").lower()
        auth = page.query_selector(ADP_AUTH_SELECTOR)
        if auth is not None and ("/auth" in url or "login" in url or "signin" in url):
            return True
        text = (page.locator("body").inner_text(timeout=2500) or "").lower()[:2500]
        return ("welcome!" in text and "use phone number" in text and
                "continue" in text and ("/auth" in url or auth is not None))
    except Exception:
        return False


def adp_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture strict ADP-owned evidence after an explicit submit attempt.

    Args:
        page: Playwright-compatible page after submit.
        timeout_ms: bounded wait budget in milliseconds.

    Returns:
        dict: receipt with ATS, URL, signals, confirmation text, and optional
        reference id. Generic gratitude text is accepted only on an ADP
        confirmation route. Never raises.
    """
    receipt = {
        "confirmed": False,
        "ats": "adp",
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
    for selector in ADP_CONFIRM_SELECTORS:
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
        body = (page.locator("body").inner_text(timeout=min(timeout_ms, 4000)) or "")
        title = str(page.title() or "")
    except Exception:
        pass
    context = bool(re.search(
        r"(?:application[-_/]?(?:confirmation|complete|submitted)|confirmation)",
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
