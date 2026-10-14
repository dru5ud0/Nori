"""Eightfold.ai public application routing, form normalization, and receipts."""

from __future__ import annotations

import re
import time
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit


EIGHTFOLD_FORM_SELECTOR = (
    "input[id*='Contact_Information_firstname' i], "
    "input[id*='Contact_Information_email' i], "
    "button:has-text('Submit application'), "
    "button:has-text('Submit Application')"
)

EIGHTFOLD_CONFIRM_SELECTORS = (
    "your application has been submitted",
    "application submitted",
    "thank you for applying",
    "we have received your application",
    "css:[class*='submissionSuccess' i]",
    "css:[class*='applicationSubmitted' i]",
)

_CLOSED_PATTERNS = (
    "this job is no longer available",
    "this position is no longer available",
    "this job posting is no longer active",
    "no longer accepting applications",
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


def eightfold_url_candidates(url: str) -> list:
    """Return safe canonical Eightfold public-application URL candidates.

    Translates posting view URLs (/careers/job/<pid>) to the direct apply route
    (/careers/apply?pid=<pid>) whenever applicable.

    Args:
        url: Candidate job posting or application URL.

    Returns:
        list: Canonical HTTPS apply URLs to attempt. Never raises.
    """
    try:
        raw = _decode(url).strip()
        parts = urlsplit(raw)
        if not parts.hostname:
            return []

        host = parts.hostname.lower()
        path = parts.path or ""
        qs = parse_qs(parts.query)

        # 1. Direct apply route already
        if "/careers/apply" in path and "pid" in qs:
            pid = qs["pid"][0]
            canonical = urlunsplit(("https", host, "/careers/apply", f"pid={pid}", ""))
            return [canonical]

        # 2. Translate /careers/job/<pid> or /job/<pid>
        job_match = re.search(r"/(?:careers/)?job/(\d+)", path, re.IGNORECASE)
        if job_match:
            pid = job_match.group(1)
            canonical = urlunsplit(("https", host, "/careers/apply", f"pid={pid}", ""))
            return [canonical, raw]

        # 3. Query pid param
        if "pid" in qs:
            pid = qs["pid"][0]
            canonical = urlunsplit(("https", host, "/careers/apply", f"pid={pid}", ""))
            return [canonical, raw]

        return [raw]
    except Exception:
        return []


def eightfold_job_closed(page) -> bool:
    """Return whether Eightfold explicitly reports that the job is closed.

    Args:
        page: Playwright Page or Frame.

    Returns:
        bool: True if closed message is detected. Never raises.
    """
    try:
        body = (page.locator("body").inner_text(timeout=2500) or "").lower()[:10000]
        return any(pat in body for pat in _CLOSED_PATTERNS)
    except Exception:
        return False


def eightfold_dismiss_privacy_modal(page) -> bool:
    """Auto-dismiss Eightfold's blocking Data Privacy Agreement modal if present.

    Args:
        page: Playwright Page.

    Returns:
        bool: True if a modal was detected and dismissed. Never raises.
    """
    try:
        agree_selectors = [
            "button:has-text('I Agree')",
            "button:has-text('Agree')",
            "button:has-text('Accept')",
            ".privacyAgreementDialogWrapper button",
            "[data-testid*='privacy-agree' i]",
        ]
        for sel in agree_selectors:
            try:
                btn = page.query_selector(sel)
                if btn is not None and btn.is_visible():
                    btn.click(timeout=1500)
                    if hasattr(page, "wait_for_timeout"):
                        page.wait_for_timeout(500)
                    return True
            except Exception:
                continue
        return False
    except Exception:
        return False


def eightfold_confirmation_receipt(page) -> dict:
    """Detect and return confirmation evidence for an Eightfold submission.

    Args:
        page: Playwright Page after submission attempt.

    Returns:
        dict: {"confirmed": bool, "evidence": str, "timestamp": float}
        Never raises.
    """
    evidence = ""
    try:
        body = (page.locator("body").inner_text(timeout=3000) or "").lower()[:10000]
        for pattern in EIGHTFOLD_CONFIRM_SELECTORS:
            if pattern.startswith("css:"):
                sel = pattern[4:]
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        evidence = f"selector:{sel}"
                        break
                except Exception:
                    continue
            else:
                if pattern in body:
                    evidence = f"text:{pattern}"
                    break
    except Exception:
        pass

    return {
        "confirmed": bool(evidence),
        "evidence": evidence,
        "timestamp": time.time(),
    }
