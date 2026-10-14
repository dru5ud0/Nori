"""Jobvite URL, consent-gate, form, closed-job, and receipt helpers."""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit


JOBVITE_APPLY_LINK_SELECTOR = (
    "a.jv-button-primary[href*='/job/'][href$='/apply'], "
    "a[href*='jobs.jobvite.com/'][href*='/job/'][href$='/apply'], "
    "a:has-text('Apply')"
)

JOBVITE_CONSENT_SELECTOR = (
    "form[name='consentForm'], form[action*='acceptUrl'], "
    "select#jv-country-select[ng-model='consentPolicyId']"
)

JOBVITE_FORM_SELECTOR = (
    "form[name='applyForm'], form#jv-apply-form, form.jv-apply-form, "
    "input[name='firstName'], input[name='candidate.firstName'], "
    "input#jv-field-firstName, input[type='email'][required], "
    "input[type='file'][name*='resume' i]"
)

JOBVITE_CONFIRM_SELECTORS = (
    "[data-testid='application-success']",
    "#jv-application-submitted",
    ".jv-application-success",
    ".jv-page-apply-success",
    "[aria-label='Application submitted']",
)

_CONFIRM_PATTERNS = (
    re.compile(r"\byour application has been submitted\b", re.I),
    re.compile(r"\bwe (?:have )?received your application\b", re.I),
    re.compile(r"\bthank you for applying\b", re.I),
    re.compile(r"\bapplication submitted successfully\b", re.I),
)

_CLOSED_PATTERNS = (
    "the job listing no longer exists",
    "this job is no longer available",
    "this position has been filled",
    "no longer accepting applications",
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


def jobvite_url_candidates(url: str) -> list:
    """Return normalized Jobvite posting and apply URLs.

    Args:
        url: possible Jobvite job or application URL.

    Returns:
        list: unique safe candidates, preferring the supplied URL and then the
        canonical ``/apply`` route. Invalid inputs return an empty list.
    """
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return []
        original = urlunsplit(parts)
        if not parts.hostname.lower().endswith("jobvite.com"):
            return [original]
        path = re.sub(r"/+$", "", parts.path)
        clean = urlunsplit((parts.scheme, parts.netloc, path, "", ""))
        candidates = [original, clean]
        if re.search(r"/job/[^/]+$", path, re.I):
            candidates.append(urlunsplit(
                (parts.scheme, parts.netloc, path + "/apply", "", "")))
        return list(dict.fromkeys(item for item in candidates if item))
    except Exception:
        return []


def jobvite_apply_url(page) -> str:
    """Return the Jobvite-owned application URL exposed by a posting page.

    Args:
        page: Playwright-compatible page object.

    Returns:
        str: absolute HTTPS Jobvite application URL, or ``""`` when absent.
    """
    try:
        link = page.query_selector(JOBVITE_APPLY_LINK_SELECTOR)
        href = (link.get_attribute("href") or "").strip() if link else ""
        absolute = urljoin(str(getattr(page, "url", "") or ""), href)
        parts = urlsplit(absolute)
        if (parts.scheme == "https" and parts.hostname
                and parts.hostname.lower().endswith("jobvite.com")
                and re.search(r"/job/[^/]+/apply/?$", parts.path, re.I)):
            return absolute
    except Exception:
        pass
    return ""


def jobvite_data_consent_required(page) -> bool:
    """Return whether Jobvite is waiting for applicant privacy consent.

    Args:
        page: Playwright-compatible page object.

    Returns:
        bool: true only for the Jobvite Data Consent gate. The adapter never
        accepts this legal/privacy choice automatically.
    """
    try:
        node = page.query_selector(JOBVITE_CONSENT_SELECTOR)
        if node is not None and (not hasattr(node, "is_visible") or node.is_visible()):
            return True
    except Exception:
        pass
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").lower()[:3000]
        return "data consent" in text and "location of residence" in text
    except Exception:
        return False


def jobvite_job_closed(page) -> bool:
    """Return whether a Jobvite posting explicitly says it is closed.

    Args:
        page: Playwright-compatible page object.

    Returns:
        bool: true for known closed-posting messages; false on uncertainty.
    """
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").lower()[:5000]
        return any(pattern in text for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def jobvite_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture Jobvite-owned application completion evidence.

    Args:
        page: Playwright-compatible page after a submit click.
        timeout_ms: maximum wait budget in milliseconds.

    Returns:
        dict: structured confirmation evidence. Bare generic thanks text is
        insufficient; errors return an unconfirmed receipt.
    """
    receipt = {
        "confirmed": False,
        "ats": "jobvite",
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
    for selector in JOBVITE_CONFIRM_SELECTORS:
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
