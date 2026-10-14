"""JOIN public-job routing, authentication checkpoints, and receipts."""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlsplit, urlunsplit


JOIN_EMAIL_SELECTOR = "input#email[name='email']"
JOIN_FORM_SELECTOR = (
    "input[name='firstName'], input[name='lastName'], input[type='file'], "
    "textarea[name], select[name]"
)

JOIN_CONFIRM_SELECTORS = (
    "[data-testid*='application-success' i]",
    "[class*='application-confirmation' i]",
    "[class*='application-success' i]",
)

_CLOSED_PATTERNS = (
    "this job is no longer available",
    "was archived or the deadline has passed",
    "this position is no longer available",
    "no longer accepting applications",
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


def join_url_candidates(url: str) -> list:
    """Return a safe normalized JOIN job/application URL.

    Args:
        url: Public JOIN company/job or application URL.

    Returns:
        list: One normalized HTTPS JOIN URL, or ``[]`` for invalid input.
        Query parameters are preserved and fragments removed. Never raises.
    """
    try:
        parts = urlsplit(_decode(url).strip())
        if (parts.scheme != "https" or (parts.hostname or "").lower() != "join.com"
                or not parts.path.lower().startswith("/companies/")):
            return []
        return [urlunsplit((parts.scheme, parts.netloc, parts.path,
                           parts.query, ""))]
    except Exception:
        return []


def join_job_closed(page) -> bool:
    """Return whether JOIN explicitly reports that the posting is archived."""
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").lower()[:8000]
        return any(pattern in text for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def join_email_verification_required(page) -> bool:
    """Return whether JOIN is waiting at its email authentication checkpoint."""
    try:
        path = urlsplit(str(getattr(page, "url", "") or "")).path.lower()
        email = page.query_selector(JOIN_EMAIL_SELECTOR)
        return ("/apply/authentication" in path and email is not None
                and (not hasattr(email, "is_visible") or email.is_visible()))
    except Exception:
        return False


def join_application_surface_visible(page) -> bool:
    """Return whether JOIN exposes a visible email checkpoint or real form.

    Args:
        page: Playwright-compatible JOIN job/application page.

    Returns:
        bool: True only when at least one matching field is visible. JOIN job
        pages can pre-render hidden application inputs, so DOM existence alone
        is not sufficient. Never raises.
    """
    try:
        nodes = page.query_selector_all(
            f"{JOIN_EMAIL_SELECTOR}, {JOIN_FORM_SELECTOR}")
        return any(not hasattr(node, "is_visible") or node.is_visible()
                   for node in nodes)
    except Exception:
        return False


def join_prepare_checkpoint(page) -> int:
    """Tag JOIN email/form controls without sending a verification message.

    Args:
        page: Playwright-compatible JOIN application/checkpoint page.

    Returns:
        int: Number of controls tagged. This helper never clicks Continue,
        requests a magic link, solves CAPTCHA, or submits. Never raises.
    """
    try:
        return int(page.evaluate(r"""() => {
          let tagged = 0;
          const email = document.querySelector('input#email[name="email"]');
          if (email) {
            email.setAttribute('aria-label', 'Email');
            email.setAttribute('aria-required', 'true');
            tagged += 1;
          }
          for (const control of document.querySelectorAll('input, select, textarea')) {
            if (control === email) continue;
            const id = control.id || '';
            const label = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
            const copy = (label?.textContent || control.getAttribute('aria-label') || '')
              .replace(/\s+/g, ' ').trim();
            if (copy) control.setAttribute('aria-label', copy);
            if (/\*|required/i.test(copy)) control.setAttribute('aria-required', 'true');
            if (control.type === 'checkbox') {
              control.setAttribute('data-nori-single-checkbox', 'true');
            }
            tagged += 1;
          }
          return tagged;
        }""") or 0)
    except Exception:
        return 0


def join_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture strict JOIN-owned post-submission evidence.

    Args:
        page: Playwright-compatible result page.
        timeout_ms: Maximum observation budget.

    Returns:
        dict: Structured receipt confirmed only by specific text in a JOIN
        confirmation surface, or confirmation context plus text. Never raises.
    """
    receipt = {
        "confirmed": False,
        "ats": "join",
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
    for selector in JOIN_CONFIRM_SELECTORS:
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
        r"/apply/(?:confirmation|complete|submitted|success)\b|"
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
