"""Dover public-application routing, normalization, and receipt evidence."""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlsplit, urlunsplit


DOVER_FORM_SELECTOR = (
    "form input[name='firstName'], form input[name='email'], "
    "form button[type='submit']"
)

DOVER_CONFIRM_SELECTORS = (
    "[data-testid*='application-success' i]",
    "[role='alert'][data-status='success']",
    "[class*='application-success' i]",
    "[class*='application-confirmation' i]",
)

_CLOSED_PATTERNS = (
    "this job is no longer available",
    "this position is no longer available",
    "this job posting is no longer available",
    "this role is no longer accepting applications",
    "no longer accepting applications",
)

_CONFIRM_PATTERNS = (
    re.compile(r"\byour application has been (?:received|submitted)\b", re.I),
    re.compile(r"\bwe (?:have )?received your application\b", re.I),
    re.compile(r"\bapplication (?:was |has been )?submitted successfully\b", re.I),
    re.compile(r"\bthanks? for applying\b", re.I),
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


def dover_url_candidates(url: str) -> list:
    """Return one safe canonical Dover public-application URL.

    Args:
        url: Candidate URL expected to use ``app.dover.com/apply/<org>/<id>``.

    Returns:
        list: Canonical HTTPS URL with tracking query/fragment removed, or an
        empty list for an invalid, insecure, or non-Dover URL. Never raises.
    """
    try:
        parts = urlsplit(_decode(url).strip())
        host = (parts.hostname or "").lower()
        if (parts.scheme != "https" or host != "app.dover.com"
                or not re.fullmatch(
                    r"/apply/[^/?#]+/[0-9a-f]{8}-[0-9a-f-]{27,}",
                    parts.path.rstrip("/"), re.I)):
            return []
        return [urlunsplit(("https", parts.netloc, parts.path.rstrip("/"), "", ""))]
    except Exception:
        return []


def dover_job_closed(page) -> bool:
    """Return whether Dover explicitly reports that the posting is closed.

    Args:
        page: Playwright-compatible job page.

    Returns:
        bool: True only for a known closed-job message. Never raises.
    """
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").lower()[:10000]
        return any(pattern in text for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def dover_prepare_form(page) -> int:
    """Add stable semantics to Dover's generated React application fields.

    Dover uses UUID names for custom questions and omits HTML labels from
    several inputs. The first file control is an optional resume-parser action;
    it is ignored so Nori uploads only to the real Resume field.

    Args:
        page: Playwright-compatible page with the public form visible.

    Returns:
        int: Number of controls tagged. No values, consents, or submit controls
        are changed. Never raises.
    """
    try:
        return int(page.evaluate(r"""() => {
          const form = document.querySelector('form');
          if (!form) return 0;
          let tagged = 0;
          const clean = value => (value || '').replace(/\s+/g, ' ').trim();
          const known = {
            firstName: 'First Name',
            lastName: 'Last Name',
            email: 'Email',
            linkedinUrl: 'LinkedIn Profile URL',
            phoneNumber: 'Phone Number'
          };
          for (const control of form.querySelectorAll('input, select, textarea')) {
            if (control.type === 'hidden' || control.type === 'file') continue;
            let label = known[control.name] || '';
            if (!label && control.type === 'radio') {
              const group = control.closest('[role="radiogroup"]');
              label = clean(group?.parentElement?.previousElementSibling?.textContent);
              if (label) control.setAttribute('data-nori-question', label);
            }
            if (!label) {
              const field = control.closest('.MuiFormControl-root') || control.parentElement;
              label = clean(field?.previousElementSibling?.textContent);
            }
            if (label) {
              if (control.type !== 'radio') {
                control.setAttribute('aria-label', label.replace(/\s*\*\s*$/, ''));
              }
              tagged += 1;
            }
          }
          const files = Array.from(form.querySelectorAll('input[type="file"]'));
          if (files.length > 1) {
            files.slice(0, -1).forEach(input => {
              input.setAttribute('data-nori-ignore', 'true');
              input.setAttribute('aria-label', 'Resume parser (ignored)');
            });
          }
          const resume = files.at(-1);
          if (resume) {
            resume.setAttribute('data-nori-field', 'resume');
            resume.setAttribute('aria-label', 'Resume');
            resume.setAttribute('aria-required', 'true');
            tagged += 1;
          }
          return tagged;
        }""") or 0)
    except Exception:
        return 0


def dover_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture conservative Dover-owned submission confirmation evidence.

    Args:
        page: Playwright-compatible result page after an authorized submit.
        timeout_ms: Maximum observation budget in milliseconds.

    Returns:
        dict: Structured receipt. Confirmation requires application-specific
        text inside a success surface, or the same text together with a clear
        confirmation URL/title context. Generic page text alone is rejected.
        Never raises.
    """
    receipt = {
        "confirmed": False,
        "ats": "dover",
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
    for selector in DOVER_CONFIRM_SELECTORS:
        try:
            node = page.query_selector(selector)
            if node is None or (hasattr(node, "is_visible") and not node.is_visible()):
                continue
            text = (node.inner_text() or "").strip()
            if any(pattern.search(text) for pattern in _CONFIRM_PATTERNS):
                receipt["signals"].append({"kind": "selector+text", "value": selector})
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
