"""Naukri job routing and non-clicking application-state inspection.

Naukri applications are profile/account centric.  A logged-in posting may
turn its visible ``Apply`` control into an immediate application action rather
than a form-opening step.  Nori therefore inspects the state but never clicks
that ambiguous control during draft preparation.
"""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlsplit, urlunsplit


NAUKRI_ACCOUNT_SELECTOR = (
    "#continue-with-google-button, a#login_Layer, "
    "a[href*='login.naukri.com'], a[href*='/registration/createAccount']"
)

NAUKRI_APPLY_SELECTOR = (
    "#apply-button, button.apply-button, button:has-text('Apply'), "
    "a:has-text('Apply Now')"
)

NAUKRI_FORM_SELECTOR = (
    "#applyForm input:not([type='hidden']), #applyForm textarea, #applyForm select, "
    "form[action*='apply' i] input:not([type='hidden']), "
    "form[action*='apply' i] textarea, form[action*='apply' i] select"
)

NAUKRI_CONFIRM_SELECTORS = (
    "[class*='apply-success' i]",
    "[class*='application-success' i]",
    "[data-testid*='application-success' i]",
)

_CLOSED_PATTERNS = (
    "this job is no longer available",
    "this job has expired",
    "this position is no longer available",
    "this job is no longer accepting applications",
    "job posting has been closed",
)

_CONFIRM_PATTERNS = (
    re.compile(r"\byou have successfully applied\b", re.I),
    re.compile(r"\bapplication (?:was |has been )?submitted successfully\b", re.I),
    re.compile(r"\byour application has been submitted\b", re.I),
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


def _visible(node) -> bool:
    try:
        return node is not None and (
            not hasattr(node, "is_visible") or bool(node.is_visible()))
    except Exception:
        return False


def naukri_url_candidates(url: str) -> list:
    """Return one safe canonical Naukri job-detail URL.

    Args:
        url: Current slug-style or legacy Naukri job URL.

    Returns:
        list: Canonical HTTPS URL without tracking query/fragment, or an empty
        list for search, account, insecure, or spoofed URLs. Never raises.
    """
    try:
        parts = urlsplit(_decode(url).strip())
        host = (parts.hostname or "").lower().rstrip(".")
        path = parts.path.rstrip("/")
        current = bool(re.fullmatch(r"/job-listings-[A-Za-z0-9._~%-]+", path, re.I))
        legacy = bool(re.fullmatch(r"/job/[A-Za-z0-9._~%-]+", path, re.I))
        if (parts.scheme != "https" or host not in ("naukri.com", "www.naukri.com")
                or not (current or legacy)):
            return []
        return [urlunsplit(("https", parts.netloc, path, "", ""))]
    except Exception:
        return []


def naukri_job_closed(page) -> bool:
    """Return whether Naukri explicitly reports that a job is closed.

    Args:
        page: Playwright-compatible Naukri job page.

    Returns:
        bool: True only for known closed-job copy. Never raises.
    """
    try:
        text = (page.locator("body").inner_text(timeout=2500) or "").lower()[:8000]
        return any(pattern in text for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def naukri_browser_blocked(page) -> bool:
    """Return whether Naukri blocked or challenged the isolated browser.

    Args:
        page: Playwright-compatible Naukri page.

    Returns:
        bool: True for explicit access-denied or human-verification surfaces.
        This helper never bypasses a challenge and never raises.
    """
    try:
        title = str(page.title() or "").lower()
        text = (page.locator("body").inner_text(timeout=2500) or "").lower()[:6000]
        return (("access denied" in title or "request blocked" in title)
                and ("access denied" in text or "request blocked" in text)
                or "verify you are human" in text)
    except Exception:
        return False


def naukri_account_required(page) -> bool:
    """Return whether the posting is waiting for a Naukri candidate account.

    Args:
        page: Playwright-compatible job or identity page.

    Returns:
        bool: True when a visible account control replaces the usable Apply
        action. Never clicks Google, logs in, registers, or raises.
    """
    try:
        google = page.query_selector("#continue-with-google-button")
        login = page.query_selector(
            "a#login_Layer, a[href*='login.naukri.com'], "
            "a[href*='/registration/createAccount']")
        apply_button = page.query_selector(NAUKRI_APPLY_SELECTOR)
        return ((_visible(google) or _visible(login)) and not _visible(apply_button))
    except Exception:
        return False


def naukri_apply_state(page) -> str:
    """Classify the current Naukri apply state without clicking anything.

    Args:
        page: Playwright-compatible Naukri page.

    Returns:
        str: ``closed``, ``browser-blocked``, ``account-required``, ``form``,
        ``one-click``, or ``unavailable``. Never raises.
    """
    try:
        if naukri_browser_blocked(page):
            return "browser-blocked"
        if naukri_job_closed(page):
            return "closed"
        if naukri_account_required(page):
            return "account-required"
        forms = page.query_selector_all(NAUKRI_FORM_SELECTOR)
        if any(_visible(node) for node in forms):
            return "form"
        if _visible(page.query_selector(NAUKRI_APPLY_SELECTOR)):
            return "one-click"
        return "unavailable"
    except Exception:
        return "unavailable"


def naukri_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture strict Naukri-owned evidence after an authorized submission.

    Args:
        page: Playwright-compatible page after a user-authorized apply action.
        timeout_ms: Maximum observation budget in milliseconds.

    Returns:
        dict: Structured receipt. Redirect notices and unsuccessful-apply
        messages are explicitly rejected; only specific success text on a
        Naukri-owned surface confirms an application. Never raises.
    """
    receipt = {
        "confirmed": False,
        "ats": "naukri",
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
    body = ""
    try:
        body = page.locator("body").inner_text(timeout=min(timeout_ms, 4000)) or ""
    except Exception:
        pass
    rejected = bool(re.search(
        r"apply was unsuccessful|redirected to the company website for "
        r"completing your application", body, re.I))
    if not rejected:
        for selector in NAUKRI_CONFIRM_SELECTORS:
            try:
                node = page.query_selector(selector)
                if not _visible(node):
                    continue
                text = (node.inner_text() or "").strip()
                if any(pattern.search(text) for pattern in _CONFIRM_PATTERNS):
                    receipt["signals"].append({"kind": "selector+text", "value": selector})
                    receipt["confirmationText"] = text[:2000]
                    break
            except Exception:
                continue
    parts = urlsplit(receipt["url"])
    owned = ((parts.hostname or "").lower().rstrip(".") == "naukri.com"
             or (parts.hostname or "").lower().endswith(".naukri.com"))
    if owned and not rejected and not receipt["signals"]:
        for pattern in _CONFIRM_PATTERNS:
            match = pattern.search(body)
            if match:
                receipt["signals"].append({"kind": "owned+text", "value": match.group(0)})
                start = max(0, match.start() - 120)
                receipt["confirmationText"] = body[start:match.end() + 240].strip()[:2000]
                break
    reference = re.search(
        r"(?:application|reference)\s*(?:id|number|#)\s*[:#-]?\s*"
        r"([A-Z0-9-]{5,40})", receipt["confirmationText"], re.I)
    if reference:
        receipt["confirmationId"] = reference.group(1)
    receipt["confirmed"] = bool(receipt["signals"])
    return receipt
