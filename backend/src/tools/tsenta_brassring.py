"""BrassRing job routing, account/privacy gates, and receipt helpers."""

from __future__ import annotations

import re
import time
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit


BRASSRING_APPLY_BUTTON_SELECTOR = (
    "#applyFromDetailBtn, button[ng-click*='postToNextPageFromDetails'][ng-click*='apply']"
)

BRASSRING_CREATE_ACCOUNT_SELECTOR = (
    "a:has-text(\"Don't have an account yet?\"), "
    "a:has-text('Create an account'), a:has-text('Register')"
)

BRASSRING_PRIVACY_SELECTOR = (
    "button[aria-label='Agree to Privacy Policy'], "
    "button:has-text('Agree')[aria-label*='Privacy' i]"
)

BRASSRING_FORM_SELECTOR = (
    "form input[name*='email' i], form input[name*='firstname' i], "
    "form input[name*='resume' i], form input[type='file']"
)

BRASSRING_CONFIRM_SELECTORS = (
    "[id*='applicationConfirmation' i]",
    "[class*='application-confirmation' i]",
    "[aria-label*='application submitted' i]",
)

_CLOSED_PATTERNS = (
    "the job posting you are looking for has expired",
    "the position has already been filled",
    "this job is no longer available",
    "this position is no longer available",
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


def brassring_url_candidates(url: str) -> list:
    """Return canonical BrassRing job-detail URL candidates.

    Args:
        url: possible BrassRing job URL, including hash-only job details.

    Returns:
        list: canonical job-detail URL first when job, partner, and site ids
        are available, followed by the original URL. Invalid input returns an
        empty list. The function never raises.
    """
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        valid_host = (host == "brassring.com" or host.endswith(".brassring.com")
                      or host == "jobs.ubs.com")
        if parts.scheme not in ("http", "https") or not host:
            return []
        original = urlunsplit(parts)
        if not valid_host or "/tgnewui/search/home/" not in parts.path.lower():
            return [original]
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        job_id = str(query.get("jobid") or "")
        if not job_id:
            match = re.search(r"jobdetails=(\d+)", parts.fragment, re.I)
            job_id = match.group(1) if match else ""
        partner_id = str(query.get("partnerid") or "")
        site_id = str(query.get("siteid") or "")
        candidates = []
        if job_id and partner_id and site_id:
            canonical_query = urlencode({
                "partnerid": partner_id,
                "siteid": site_id,
                "PageType": "JobDetails",
                "jobid": job_id,
            })
            candidates.append(urlunsplit((
                parts.scheme, parts.netloc,
                re.sub(r"/+$", "", parts.path), canonical_query, "",
            )))
        candidates.append(original)
        return list(dict.fromkeys(item for item in candidates if item))
    except Exception:
        return []


def brassring_job_closed(page) -> bool:
    """Return whether BrassRing explicitly reports an expired posting.

    Args:
        page: Playwright-compatible page.

    Returns:
        bool: true only for a known expired/filled job message. Never raises.
    """
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").lower()[:6000]
        return any(pattern in text for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def brassring_account_required(page) -> bool:
    """Return whether BrassRing is showing its username/password account gate.

    Args:
        page: Playwright-compatible page.

    Returns:
        bool: true only when both login and password controls are present, or
        the page title is Sign In with one credential control. Never raises.
    """
    try:
        login = page.query_selector("#loginField, input[name='loginField']")
        password = page.query_selector("#password, input[type='password']")
        if login is not None and password is not None:
            return True
        title = str(page.title() or "").strip().lower()
        return title == "sign in" and (login is not None or password is not None)
    except Exception:
        return False


def brassring_privacy_consent_required(page) -> bool:
    """Return whether employer privacy/attestation acceptance is required.

    Args:
        page: Playwright-compatible page.

    Returns:
        bool: true only for the explicit Agree privacy-policy gate. Nori never
        chooses it without a saved reviewed answer. Never raises.
    """
    try:
        if page.query_selector(BRASSRING_PRIVACY_SELECTOR) is not None:
            return True
    except Exception:
        pass
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").lower()[:12000]
        return ("privacy policy" in text and "you must agree" in text
                and "agree disagree" in text)
    except Exception:
        return False


def brassring_mark_privacy_review(page) -> bool:
    """Expose the Agree button as a required checkbox-like review field.

    Args:
        page: Playwright-compatible page at the BrassRing privacy gate.

    Returns:
        bool: true when the exact privacy control was tagged for Nori's form
        collector; false when it was absent or could not be tagged. Never
        clicks the control and never raises.
    """
    try:
        control = page.query_selector(BRASSRING_PRIVACY_SELECTOR)
        if control is None:
            return False
        control.evaluate("""el => {
          el.setAttribute('data-nori-field', 'brassring-privacy-consent');
          el.setAttribute('aria-required', 'true');
          (el.parentElement || el).setAttribute(
            'data-nori-brassring-privacy-scope', 'true');
        }""")
        return True
    except Exception:
        return False


def brassring_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture BrassRing-owned evidence after a submission attempt.

    Args:
        page: Playwright-compatible page after submit.
        timeout_ms: maximum wait budget in milliseconds.

    Returns:
        dict: structured receipt. A generic gratitude message is accepted only
        when paired with a confirmation URL/hash/title; an ATS-owned selector
        is sufficient on its own. Never raises.
    """
    receipt = {
        "confirmed": False,
        "ats": "brassring",
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
    for selector in BRASSRING_CONFIRM_SELECTORS:
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
    title = ""
    try:
        title = str(page.title() or "")
    except Exception:
        pass
    confirmation_context = bool(re.search(
        r"(?:application)?confirmation|application(?:submitted|complete)",
        receipt["url"] + " " + title, re.I))
    if confirmation_context:
        for pattern in _CONFIRM_PATTERNS:
            match = pattern.search(body_text)
            if match:
                receipt["signals"].append({"kind": "context+text",
                                           "value": match.group(0)})
                if not receipt["confirmationText"]:
                    start = max(0, match.start() - 120)
                    receipt["confirmationText"] = body_text[
                        start:match.end() + 240].strip()[:2000]
                break
    receipt_match = re.search(
        r"(?:confirmation|application|reference)\s*(?:id|number|#)\s*[:#-]?\s*([A-Z0-9-]{5,40})",
        receipt["confirmationText"], re.I)
    if receipt_match:
        receipt["confirmationId"] = receipt_match.group(1)
    receipt["confirmed"] = bool(receipt["signals"])
    return receipt
