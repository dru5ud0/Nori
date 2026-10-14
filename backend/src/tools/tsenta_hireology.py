"""Hireology public-form routing, normalization, and receipts."""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlsplit, urlunsplit


HIREOLOGY_APPLY_BUTTON_SELECTOR = (
    "button#apply-now-button, button.careers-apply__now"
)

HIREOLOGY_FORM_SELECTOR = (
    "input[id^='first_name-'], input[id^='email_address-'], "
    "button#submit.careers-submit-button"
)

HIREOLOGY_CONFIRM_SELECTORS = (
    ".careers-apply-form__success",
    "[class*='application-confirmation' i]",
    "[class*='application-success' i]",
)

_CLOSED_PATTERNS = (
    "this job is no longer available",
    "this position is no longer available",
    "this job posting has expired",
    "no longer accepting applications",
    "position has been filled",
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


def hireology_url_candidates(url: str) -> list:
    """Return a safe normalized Hireology public-job URL.

    Args:
        url: Public job URL on ``careers.hireology.com``.

    Returns:
        list: One normalized HTTPS URL with its query preserved and fragment
        removed, or ``[]`` for invalid/non-Hireology input. Never raises.
    """
    try:
        parts = urlsplit(_decode(url).strip())
        if (parts.scheme != "https"
                or (parts.hostname or "").lower() != "careers.hireology.com"
                or not re.search(r"/[^/]+/\d+/(?:description|apply)?/?$",
                                 parts.path, re.I)):
            return []
        return [urlunsplit((parts.scheme, parts.netloc, parts.path,
                           parts.query, ""))]
    except Exception:
        return []


def hireology_job_closed(page) -> bool:
    """Return whether Hireology explicitly reports that the posting closed."""
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").lower()[:8000]
        return any(pattern in text for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def hireology_prepare_form(page) -> int:
    """Normalize Hireology's label-driven accountless application controls.

    Args:
        page: Playwright-compatible page after the Apply form is visible.

    Returns:
        int: Number of tagged controls. Optional SMS starts as an explicit
        editable field; this function itself does not choose any answer,
        consent, demographic value, or submission action. Never raises.
    """
    try:
        return int(page.evaluate(r"""() => {
          let tagged = 0;
          for (const control of document.querySelectorAll('input, select, textarea')) {
            const id = control.id || '';
            const label = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
            const copy = (label?.textContent || '').replace(/\s+/g, ' ').trim();
            if (copy && !control.getAttribute('aria-label')) {
              control.setAttribute('aria-label', copy);
              tagged += 1;
            }
            if (/\(required\)/i.test(copy) ||
                (control.tagName === 'TEXTAREA' && copy && !/\(optional\)/i.test(copy))) {
              control.setAttribute('aria-required', 'true');
            }
            if (control.type === 'checkbox') {
              control.setAttribute('data-nori-single-checkbox', 'true');
            }
          }
          const resume = document.querySelector('input[id^="resume-"][type="file"]');
          if (resume) {
            resume.setAttribute('aria-label', 'Resume');
            resume.setAttribute('aria-required', 'true');
            tagged += 1;
          }
          const cover = document.querySelector('input[id^="cover-"][type="file"]');
          if (cover) {
            cover.setAttribute('aria-label', 'Cover Letter (optional)');
            cover.setAttribute('aria-required', 'false');
            tagged += 1;
          }
          for (const radio of document.querySelectorAll('input[type="radio"]')) {
            const root = radio.parentElement?.closest('div[id^="candidate_referred-"]');
            const question = (root?.querySelector('.careers-radiobutton__component-label')
              ?.textContent || '').replace(/\s+/g, ' ').trim();
            if (question) radio.setAttribute('data-nori-question', question);
            tagged += 1;
          }
          return tagged;
        }""") or 0)
    except Exception:
        return 0


def hireology_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture strict Hireology-owned evidence after explicit submission.

    Args:
        page: Playwright-compatible result page.
        timeout_ms: Maximum observation budget.

    Returns:
        dict: Structured receipt with ``confirmed`` true only for specific
        Hireology confirmation text inside a confirmation surface, or matching
        confirmation route context plus text. Never raises.
    """
    receipt = {
        "confirmed": False,
        "ats": "hireology",
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
    for selector in HIREOLOGY_CONFIRM_SELECTORS:
        try:
            node = page.query_selector(selector)
            if node is None or (hasattr(node, "is_visible") and not node.is_visible()):
                continue
            text = (node.inner_text() or "").strip()
            if any(pattern.search(text) for pattern in _CONFIRM_PATTERNS):
                receipt["signals"].append({"kind": "selector+text",
                                           "value": selector})
                receipt["confirmationText"] = text[:2000]
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
        r"/(?:confirmation|complete|submitted|thank[-_]?you)\b|"
        r"application[-_ ](?:confirmation|complete|submitted)",
        receipt["url"] + " " + title, re.I))
    if context and not receipt["signals"]:
        for pattern in _CONFIRM_PATTERNS:
            match = pattern.search(body)
            if match:
                receipt["signals"].append({"kind": "context+text",
                                           "value": match.group(0)})
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
