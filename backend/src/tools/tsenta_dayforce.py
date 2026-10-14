"""Dayforce apply-flow, consent-gate, closed-job, and receipt helpers."""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlsplit, urlunsplit


DAYFORCE_FORM_SELECTOR = (
    "form input[type='file'], input[name*='firstName' i], "
    "input[test-id*='first-name' i], input[test-id*='firstname' i], "
    "input[test-id*='resume' i]"
)

DAYFORCE_APPLY_BUTTON_SELECTOR = (
    "button[test-id='apply-button'], button[aria-label^='Apply for '], "
    "button:has-text('Apply')"
)

DAYFORCE_ACCOUNTLESS_SELECTOR = (
    "button[test-id='apply-without-account'], "
    "button:has-text('Apply without an Account')"
)

DAYFORCE_PRIVACY_SELECTOR = (
    "input[type='checkbox'][name*='privacy' i], "
    "input[type='checkbox'][test-id*='privacy' i], "
    "input[type='checkbox'][aria-label*='Privacy Statement' i]"
)

DAYFORCE_CONFIRM_SELECTORS = (
    "[test-id='application-submitted']",
    "[data-testid='application-submitted']",
    "[aria-label='Application submitted']",
    ".application-submitted",
)

_CONFIRM_PATTERNS = (
    re.compile(r"\byour application has been submitted\b", re.I),
    re.compile(r"\bwe (?:have )?received your application\b", re.I),
    re.compile(r"\bthank you for (?:your )?application\b", re.I),
    re.compile(r"\bapplication submitted successfully\b", re.I),
)

_CLOSED_PATTERNS = (
    "this job posting is no longer available",
    "this job is no longer available",
    "this position is no longer available",
    "this job is no longer accepting applications",
)


def dayforce_prepare_form(page) -> int:
    """Tag stable Dayforce controls and ignore irrelevant optional inputs.

    Args:
        page: Playwright-compatible page on the manual application route.

    Returns:
        int: Number of controls tagged or ignored; ``0`` on failure. Never
        raises.
    """
    try:
        value = page.evaluate("""() => {
          let tagged = 0;
          const ignoreSelectors = [
            '#lang-select',
            '#jobPostingApplication_personalInfo_prefixId',
            '#jobPostingApplication_personalInfo_suffixId',
            '[test-id="personal-info-middlename-form-item"] input',
            '[test-id="personal-info-home-phone-form-item"] input',
            '[test-id="personal-info-fax-form-item"] input',
            '[test-id="personal-info-pager-form-item"] input',
            '[test-id="personal-info-address2-form-item"] input',
            '[test-id="personal-info-county-form-item"] input',
            '#jobPostingApplication_files_additionalDocument'
          ];
          document.querySelectorAll(ignoreSelectors.join(',')).forEach(node => {
            if (node.getAttribute('data-nori-ignore') !== 'true') {
              node.setAttribute('data-nori-ignore', 'true');
              tagged += 1;
            }
          });
          const mobile = document.querySelector(
            '[test-id="personal-info-mobile-phone-form-item"]');
          if (mobile) {
            mobile.querySelectorAll('input[role="combobox"]').forEach(node => {
              if (node.getAttribute('data-nori-field') !== 'candidate.phone.country') {
                node.setAttribute('data-nori-field', 'candidate.phone.country');
                tagged += 1;
              }
            });
          }
          return tagged;
        }""")
        return int(value or 0)
    except Exception:
        return 0


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


def dayforce_url_candidates(url: str) -> list:
    """Return a Dayforce posting URL and its account-choice apply route.

    Args:
        url: possible Dayforce job or application URL.

    Returns:
        list: normalized safe candidates; invalid input returns an empty list.
    """
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return []
        original = urlunsplit(parts)
        if parts.hostname.lower() != "jobs.dayforcehcm.com":
            return [original]
        path = re.sub(r"/+$", "", parts.path)
        clean = urlunsplit((parts.scheme, parts.netloc, path, "", ""))
        candidates = [original, clean]
        match = re.search(r"^(.*?/jobs/\d+)(?:/apply(?:/.*)?)?$", path, re.I)
        if match:
            posting_path = match.group(1)
            candidates.append(urlunsplit(
                (parts.scheme, parts.netloc, posting_path, "", "")))
            candidates.append(urlunsplit(
                (parts.scheme, parts.netloc, posting_path + "/apply", "flowSelection=true", "")))
        return list(dict.fromkeys(item for item in candidates if item))
    except Exception:
        return []


def dayforce_privacy_consent_required(page) -> bool:
    """Return whether Dayforce is waiting for employer privacy consent.

    Args:
        page: Playwright-compatible page.

    Returns:
        bool: true only for the privacy-policy acknowledgement step. Nori never
        checks this box automatically.
    """
    try:
        if page.query_selector(DAYFORCE_PRIVACY_SELECTOR) is not None:
            return True
    except Exception:
        pass
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").lower()[:6000]
        return (any(term in text for term in ("privacy policy", "privacy statement"))
                and "i agree to the privacy statement" in text
                and ("acknowledge and consent" in text or "please review the policy" in text))
    except Exception:
        return False


def dayforce_job_closed(page) -> bool:
    """Return whether Dayforce explicitly reports the posting closed.

    Args:
        page: Playwright-compatible page.

    Returns:
        bool: true only for a known closed-job message.
    """
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").lower()[:5000]
        return any(pattern in text for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def dayforce_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture Dayforce-owned evidence after a submission attempt.

    Args:
        page: Playwright-compatible page after submit.
        timeout_ms: maximum wait budget in milliseconds.

    Returns:
        dict: structured receipt. Generic gratitude alone is insufficient.
    """
    receipt = {
        "confirmed": False,
        "ats": "dayforce",
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
    for selector in DAYFORCE_CONFIRM_SELECTORS:
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
