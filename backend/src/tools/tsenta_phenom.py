"""Phenom branded-career routing, form normalization, and receipts."""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit


PHENOM_APPLY_BUTTON_SELECTOR = (
    "a[href*='/apply'][href*='jobSeqNo=' i], "
    "a[href*='/apply'][class*='apply' i]"
)

PHENOM_FORM_SELECTOR = (
    "input[name='cntryFields.firstName'], "
    "input#email[name='email'], "
    "input#stepNum[value='1']"
)

PHENOM_CONFIRM_SELECTORS = (
    "[class*='application-confirmation' i]",
    "[class*='application-success' i]",
    "[class*='thank-you' i]",
)

_PHENOM_HOSTS = (".phenompeople.com", "careers.phenom.com")

_CLOSED_PATTERNS = (
    "does not exist or is no longer open",
    "this job is no longer available",
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


def _is_phenom_url(parts) -> bool:
    host = (parts.hostname or "").lower()
    path = parts.path or ""
    hosted = host == "careers.phenom.com" or any(
        host.endswith(suffix) for suffix in _PHENOM_HOSTS[:1]
    )
    branded = bool(
        re.search(r"/[a-z]{2}/[a-z]{2}/(?:job/[^/?#]+|apply)\b", path, re.I)
        or re.search(r"(?:^|&)jobseqno=", parts.query, re.I)
    )
    return hosted or branded


def phenom_url_candidates(url: str) -> list:
    """Return safe normalized Phenom posting/application URL candidates.

    Args:
        url: Phenom-hosted or branded career posting/application URL.

    Returns:
        list: The normalized HTTPS URL, or ``[]`` for invalid/non-Phenom
        input. Fragments are removed and the original query is preserved.
        Never raises.
    """
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        if parts.scheme != "https" or not parts.hostname or not _is_phenom_url(parts):
            return []
        return [urlunsplit((parts.scheme, parts.netloc, parts.path,
                           parts.query, ""))]
    except Exception:
        return []


def phenom_apply_url(page, source_url: str) -> str:
    """Return a safe same-origin Phenom apply link exposed by a posting.

    Args:
        page: Playwright-compatible Phenom posting page.
        source_url: Posting URL used to constrain the apply link origin.

    Returns:
        str: Absolute HTTPS apply URL, or ``""`` when no safe link exists.
        Never raises.
    """
    try:
        source = urlsplit(str(source_url or getattr(page, "url", "") or ""))
        for link in page.query_selector_all(PHENOM_APPLY_BUTTON_SELECTOR):
            try:
                if hasattr(link, "is_visible") and not link.is_visible():
                    continue
                href = urljoin(str(getattr(page, "url", "") or source_url),
                               link.get_attribute("href") or "")
                candidate = urlsplit(href)
                if (candidate.scheme == "https" and candidate.hostname
                        and candidate.hostname.lower() == (source.hostname or "").lower()
                        and ("/apply" in candidate.path.lower()
                             or "jobseqno=" in candidate.query.lower())):
                    return href
            except Exception:
                continue
    except Exception:
        pass
    return ""


def phenom_reject_optional_cookies(page) -> bool:
    """Click Phenom's exact ``Deny`` cookie action when visible.

    Args:
        page: Playwright-compatible page.

    Returns:
        bool: Whether the cookie denial action was clicked. The helper never
        clicks ``Allow`` and never raises.
    """
    try:
        body = (page.locator("body").inner_text(timeout=2000) or "").lower()[:2500]
        if "cookie" not in body:
            return False
        for button in page.query_selector_all("button"):
            try:
                if ((button.inner_text() or "").strip().lower() != "deny"
                        or not button.is_visible()):
                    continue
                try:
                    button.click(timeout=3000)
                except TypeError:
                    button.click()
                return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def phenom_job_closed(page) -> bool:
    """Return whether Phenom explicitly reports that the posting is closed."""
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").lower()[:8000]
        return any(pattern in text for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def phenom_prepare_form(page) -> int:
    """Add stable semantics to Phenom's native multi-stage form controls.

    Args:
        page: Playwright-compatible page on a Phenom application route.

    Returns:
        int: Number of controls tagged. Only accessibility/automation metadata
        is changed; no answer, consent, or attestation is selected. Never
        raises.
    """
    try:
        return int(page.evaluate(r"""() => {
          let tagged = 0;
          const resume = document.querySelector('.resume-upload-wrapper input[type="file"], input[type="file"]');
          if (resume) {
            resume.setAttribute('data-nori-field', 'phenom.resume');
            resume.setAttribute('aria-label', 'Resume');
            resume.setAttribute('aria-required', 'true');
            tagged += 1;
          }
          for (const control of document.querySelectorAll('select')) {
            const id = control.id || '';
            const label = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
            const text = (label?.textContent || '').replace(/\s+/g, ' ').replace(/\*$/, '').trim();
            if (text && !control.getAttribute('aria-label')) {
              control.setAttribute('aria-label', text);
              tagged += 1;
            }
          }
          const phoneCountry = document.getElementById('phoneWidget.countryPhoneCode');
          if (phoneCountry) {
            phoneCountry.setAttribute('data-nori-field', 'candidate.phone.country');
          }
          for (const control of document.querySelectorAll('input[type="checkbox"]')) {
            const copy = Array.from(control.labels || [])
              .map(label => label.textContent || '').join(' ')
              .replace(/\s+/g, ' ').replace(/^\*\s*/, '').trim();
            if (copy) control.setAttribute('aria-label', copy.slice(0, 1800));
            control.setAttribute('data-nori-single-checkbox', 'true');
            tagged += 1;
          }
          for (const radio of document.querySelectorAll('input[type="radio"]')) {
            const group = radio.closest('[role="radiogroup"]');
            const label = group?.getAttribute('aria-label') ||
              document.getElementById(group?.getAttribute('aria-labelledby') || '')?.textContent || '';
            if (/employed by .+ in the past/i.test(label)) {
              radio.setAttribute('data-nori-question', 'Have you worked for us before?');
            }
            tagged += 1;
          }
          return tagged;
        }""") or 0)
    except Exception:
        return 0


def phenom_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture conservative Phenom-owned post-submission evidence.

    Args:
        page: Playwright-compatible result page.
        timeout_ms: Maximum observation budget.

    Returns:
        dict: Structured receipt. ``confirmed`` is true only when a Phenom
        confirmation surface is visible, or confirmation-route context and
        specific submission text occur together. Never raises.
    """
    receipt = {
        "confirmed": False,
        "ats": "phenom",
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
    for selector in PHENOM_CONFIRM_SELECTORS:
        try:
            node = page.query_selector(selector)
            if node is not None and (not hasattr(node, "is_visible") or node.is_visible()):
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
        r"(?:stepname|step)=?(?:confirmation|complete|submitted|thank)|"
        r"application[-_ ](?:confirmation|complete|submitted)|thank[-_ ]you",
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
