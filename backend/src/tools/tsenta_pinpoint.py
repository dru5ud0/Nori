"""Pinpoint posting/apply routing, public-form normalization, and receipts."""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlsplit, urlunsplit


PINPOINT_FORM_SELECTOR = (
    "form[action*='/applications'] input[name*='first_name'], "
    "form input[id*='application_form_application_first_name']"
)

PINPOINT_CONFIRM_SELECTORS = (
    "[data-testid*='application-success' i]",
    "[class*='application-confirmation' i]",
    "[class*='application-success' i]",
)

_CLOSED_PATTERNS = (
    "this job is no longer available",
    "this position is no longer available",
    "this posting is no longer available",
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


def pinpoint_url_candidates(url: str) -> list:
    """Return the canonical public Pinpoint application URL.

    Args:
        url: Pinpoint posting or ``applications/new`` URL.

    Returns:
        list: Application URL first, then the normalized original when
        distinct. Invalid/non-Pinpoint/insecure input returns ``[]``. Never
        raises.
    """
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        if (parts.scheme != "https" or not host.endswith(".pinpointhq.com")
                or "/postings/" not in parts.path.lower()):
            return []
        path = parts.path.rstrip("/")
        if not path.lower().endswith("/applications/new"):
            posting = re.match(r"(.*/postings/[^/]+)", path, re.I)
            if posting is None:
                return []
            apply_path = posting.group(1) + "/applications/new"
        else:
            apply_path = path
        apply_url = urlunsplit((parts.scheme, parts.netloc, apply_path, "", ""))
        original = urlunsplit((parts.scheme, parts.netloc, parts.path,
                               parts.query, ""))
        return list(dict.fromkeys(item for item in (apply_url, original) if item))
    except Exception:
        return []


def pinpoint_reject_optional_cookies(page) -> bool:
    """Click Pinpoint's exact ``Reject all`` cookie action when visible.

    Args:
        page: Playwright-compatible page.

    Returns:
        bool: Whether the reject action was clicked. Never raises. It never
        clicks ``Accept all``.
    """
    try:
        for button in page.query_selector_all("button"):
            try:
                if ((button.inner_text() or "").strip().lower() != "reject all"
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


def pinpoint_job_closed(page) -> bool:
    """Return whether Pinpoint explicitly reports that the job is closed."""
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").lower()[:8000]
        return any(pattern in text for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def pinpoint_prepare_form(page) -> int:
    """Add stable semantic metadata to Pinpoint React controls.

    Args:
        page: Playwright-compatible page on the public application route.

    Returns:
        int: Number of tagged controls. Only accessibility/automation metadata
        changes; answers and consent choices are untouched. Never raises.
    """
    try:
        return int(page.evaluate(r"""() => {
          let tagged = 0;
          const mappings = [
            ['application_form[application][country]', 'personalInformation.country', 'Country'],
            ['address1', 'personalInformation.address', 'Street Address'],
            ['address2', 'personalInformation.city', 'City'],
            ['application_form[application][town]', 'personalInformation.state', 'State'],
            ['postcode', 'personalInformation.zipCode', 'Zipcode']
          ];
          for (const [id, field, label] of mappings) {
            const control = document.getElementById(id);
            if (!control) continue;
            control.setAttribute('data-nori-field', field);
            control.setAttribute('aria-label', label);
            const row = control.closest('.col-1-1, .col-md-1-1');
            if (row?.querySelector('.external-form__label--required')) {
              control.setAttribute('aria-required', 'true');
            }
            tagged += 1;
          }
          for (const radio of document.querySelectorAll(
              'input[type="radio"][name*="answers_attributes"]')) {
            const row = radio.closest('.pad-v-3');
            const title = (row?.querySelector('.external-form__label--title')
              ?.textContent || '').trim();
            if (!title) continue;
            if (row.querySelector('.external-form__label--required')) {
              radio.setAttribute('aria-required', 'true');
            }
            tagged += 1;
          }
          for (const control of document.querySelectorAll(
              'input.react-select__input, input[role="combobox"]')) {
            control.setAttribute('data-nori-lazy-options', 'true');
          }
          return tagged;
        }""") or 0)
    except Exception:
        return 0


def pinpoint_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture strict Pinpoint-owned evidence after explicit submission.

    Args:
        page: Playwright-compatible result page.
        timeout_ms: Maximum observation budget.

    Returns:
        dict: Receipt contract with ``confirmed`` true only for a Pinpoint
        confirmation surface or confirmation-route plus specific text. Never
        raises.
    """
    receipt = {
        "confirmed": False,
        "ats": "pinpoint",
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
    for selector in PINPOINT_CONFIRM_SELECTORS:
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
        body = page.locator("body").inner_text(timeout=min(timeout_ms, 4000)) or ""
        title = str(page.title() or "")
    except Exception:
        pass
    context = bool(re.search(
        r"applications/(?:confirmation|complete|submitted|thank)|"
        r"application[-_ ]confirmation",
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
