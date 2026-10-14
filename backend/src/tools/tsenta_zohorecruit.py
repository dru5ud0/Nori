"""Zoho Recruit public career form routing and markup normalization."""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlsplit, urlunsplit


ZOHORECRUIT_APPLY_BUTTON_SELECTOR = "button:has-text(\"I'm interested\")"

ZOHORECRUIT_FORM_SELECTOR = (
    "form crux-text-component, form crux-picklist-component, "
    "form input[type='file'], form button:has-text('Submit Application')"
)

ZOHORECRUIT_CONFIRM_SELECTORS = (
    "[class*='application-success' i]",
    "[class*='application-confirmation' i]",
    "[data-zcqa*='application-success' i]",
)

_CLOSED_PATTERNS = (
    "this job is no longer available",
    "this position is no longer available",
    "this job has been closed",
    "we are no longer accepting applications",
)

_CONFIRM_PATTERNS = (
    re.compile(r"\byour application has been submitted\b", re.I),
    re.compile(r"\bapplication submitted successfully\b", re.I),
    re.compile(r"\bthank you for applying\b", re.I),
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


def zohorecruit_url_candidates(url: str) -> list:
    """Return canonical HTTPS Zoho Recruit career URL candidates.

    Args:
        url: Zoho Recruit career posting URL.

    Returns:
        list: fragment-free canonical URL and original when distinct. Invalid
        or unrelated URLs return an empty list. Never raises.
    """
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        if (parts.scheme != "https" or
                not (host == "zohorecruit.com" or host.endswith(".zohorecruit.com"))):
            return []
        original = urlunsplit(parts)
        canonical = urlunsplit((parts.scheme, parts.netloc, parts.path,
                                parts.query, ""))
        return list(dict.fromkeys(item for item in (canonical, original) if item))
    except Exception:
        return []


def zohorecruit_decline_optional_cookies(page) -> bool:
    """Choose Zoho's exact non-essential-cookie decline action when shown."""
    try:
        buttons = page.query_selector_all("button")
        for button in buttons:
            try:
                if ((button.inner_text() or "").strip().lower()
                        != "decline non-essential" or not button.is_visible()):
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


def zohorecruit_job_closed(page) -> bool:
    """Return whether Zoho explicitly reports the posting as closed."""
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").lower()[:8000]
        return any(pattern in text for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def zohorecruit_prepare_form(page) -> int:
    """Expose stable labels, required flags, and ids on Zoho custom controls.

    Args:
        page: Playwright-compatible page showing the Zoho application form.

    Returns:
        int: number of tagged controls. DOM attributes are accessibility
        metadata only; values, choices, and consent controls are untouched.
    """
    try:
        return int(page.evaluate(r"""() => {
          let tagged = 0;
          const rows = Array.from(document.querySelectorAll(
            '.crc-form-row:not(.crc-form-sec)'));
          for (const row of rows) {
            const labelNode = row.querySelector(
              ':scope > .crm-from-label .crc-label-text, :scope > .crm-from-label, .crc-label-text');
            const label = (labelNode?.innerText || '').replace(/\s*[*✱]\s*$/, '').trim();
            if (!label) continue;
            const required = Boolean(row.querySelector('.crc-form-mandatory'));
            const component = row.querySelector('crux-text-component, crux-picklist-component, crux-date-component, crux-currency-component, crux-phone-component');
            const rowKey = (component?.id ||
              (row.className.match(/crc-(rec-form_[A-Za-z0-9_-]+)/) || [])[1] ||
              ('zohorecruit-' + tagged)).replace(/[^A-Za-z0-9_.:-]/g, '-');
            const controls = Array.from(row.querySelectorAll('input:not([type="hidden"]):not([type="button"]):not([type="submit"]), textarea, [role="combobox"][aria-haspopup="listbox"]'))
              .filter(control => control.id !== 'inputId');
            controls.forEach((control, index) => {
              const isCheckbox = (control.getAttribute('type') || '').toLowerCase() === 'checkbox';
              const isPhoneCountry = /phone/i.test(label) &&
                control.getAttribute('role') === 'combobox';
              const detail = isCheckbox ?
                (control.closest('.crc-custom-cheackbox')?.querySelector('.crc-terms-text')
                  ?.innerText || '').trim() : '';
              const controlLabel = isPhoneCountry ? 'Country calling code' :
                (detail ? label + ': ' + detail : label);
              control.setAttribute('aria-label', controlLabel);
              control.setAttribute('data-nori-field', isPhoneCountry ?
                'candidate.phone.country' : (index ? rowKey + '-' + index : rowKey));
              if (required) control.setAttribute('aria-required', 'true');
              if (isCheckbox) {
                control.setAttribute('data-nori-single-checkbox', 'true');
              }
              tagged += 1;
            });
          }
          const easyResume = document.querySelector('input[name="rec-easyresume_file"]');
          if (easyResume && !easyResume.getAttribute('data-nori-field')) {
            easyResume.setAttribute('data-nori-field', 'zohorecruit-optional-resume-autofill');
            easyResume.setAttribute('aria-label', 'Optional supplemental resume autofill');
            tagged += 1;
          }
          return tagged;
        }""") or 0)
    except Exception:
        return 0


def zohorecruit_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture strict Zoho Recruit evidence after an explicit submission."""
    receipt = {
        "confirmed": False,
        "ats": "zohorecruit",
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
    for selector in ZOHORECRUIT_CONFIRM_SELECTORS:
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
        r"application[-_/]?(?:confirmation|complete|submitted)|thank-you",
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
