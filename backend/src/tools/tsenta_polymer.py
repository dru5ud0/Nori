"""Polymer hosted-job routing, form normalization, and receipt evidence."""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlsplit, urlunsplit


POLYMER_FORM_SELECTOR = (
    "#apply input:not([type='hidden']), #apply textarea, "
    "#apply button[type='submit']"
)

POLYMER_CONFIRM_SELECTORS = (
    "#apply [role='alert']",
    "[data-testid*='application-success' i]",
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

_DIRECT_FIELDS = {
    "name": ("fullName", "Full Name", "text"),
    "full name": ("fullName", "Full Name", "text"),
    "email": ("email", "Email", "email"),
    "email address": ("email", "Email", "email"),
    "phone": ("phone", "Phone Number", "tel"),
    "phone number": ("phone", "Phone Number", "tel"),
    "location": ("city", "City", "text"),
    "linkedin profile": ("linkedinUrl", "LinkedIn URL", "url"),
    "linkedin profile url": ("linkedinUrl", "LinkedIn URL", "url"),
}


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


def polymer_url_candidates(url: str) -> list:
    """Return one safe canonical Polymer public-job URL.

    Args:
        url: Candidate URL expected to use ``jobs.polymer.co/<board>/<job-id>``.

    Returns:
        list: Canonical HTTPS job URL with tracking query and fragment removed,
        or an empty list for an invalid, insecure, or non-Polymer URL. Never
        raises.
    """
    try:
        parts = urlsplit(_decode(url).strip())
        host = (parts.hostname or "").lower()
        path = parts.path.rstrip("/")
        if (parts.scheme != "https" or host != "jobs.polymer.co"
                or not re.fullmatch(r"/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+", path)):
            return []
        return [urlunsplit(("https", parts.netloc, path, "", ""))]
    except Exception:
        return []


def polymer_job_closed(page) -> bool:
    """Return whether Polymer explicitly reports that the posting is closed.

    Args:
        page: Playwright-compatible public job page.

    Returns:
        bool: True only for a known closed-job message. Never raises.
    """
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").lower()[:12000]
        return any(pattern in text for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def polymer_prepare_form(page) -> int:
    """Normalize Polymer's inline accountless application form.

    The form is anchored at ``#apply`` and can contain employer-specific
    required long-form questions. Identity fields are mapped to stable profile
    keys; custom questions retain their full visible labels for truthful LLM or
    review handling. reCAPTCHA controls and the submit button are untouched.

    Args:
        page: Playwright-compatible Polymer job page with the form visible.

    Returns:
        int: Number of application controls tagged. Never raises.
    """
    try:
        direct = {key: list(value) for key, value in _DIRECT_FIELDS.items()}
        return int(page.evaluate(r"""direct => {
          const clean = value => (value || '').replace(/\s+/g, ' ').trim();
          const submit = Array.from(document.querySelectorAll('button[type="submit"]'))
            .find(button => /submit application/i.test(clean(button.textContent)))
            || document.querySelector('button[type="submit"]');
          let root = document.querySelector('#apply') || submit?.closest('form');
          if (!root && submit) {
            root = submit.parentElement;
            while (root && root !== document.body) {
              if (root.querySelector('input[type="file"]') && root.querySelector('textarea, input[type="email"]')) break;
              root = root.parentElement;
            }
          }
          if (!root || root === document.body) return 0;
          root.setAttribute('data-nori-scope', 'polymer-application');
          root.querySelectorAll(
            '[name="g-recaptcha-response"], [name="h-captcha-response"], [name="cf-turnstile-response"]'
          ).forEach(control => control.setAttribute('data-nori-ignore', 'true'));
          let tagged = 0;
          let customIndex = 0;
          const labelFor = control => {
            const labelled = clean(Array.from(control.labels || [])
              .map(label => label.textContent || '').join(' '));
            if (labelled) return labelled.replace(/\s*\(\s*required\s*\)\s*$/i, '');
            const aria = clean(control.getAttribute('aria-label'));
            if (aria) return aria;
            let node = control.parentElement;
            for (let depth = 0; node && node !== root && depth < 7;
                 depth += 1, node = node.parentElement) {
              const candidate = Array.from(node.children).find(child => {
                if (child === control || child.contains(control)) return false;
                if (child.querySelector('input, textarea, select, button')) return false;
                const text = clean(child.textContent);
                return text && text.length <= 500 && !/^\(\s*required\s*\)$/i.test(text);
              });
              if (candidate) return clean(candidate.textContent);
            }
            return '';
          };
          const controls = root.querySelectorAll(
            'input:not([type="hidden"]):not([type="submit"]):not([type="button"]), textarea');
          for (const control of controls) {
            if (control.type === 'file') {
              control.setAttribute('data-nori-field', 'resume');
              control.setAttribute('aria-label', 'Resume');
              control.setAttribute('aria-required', 'true');
              tagged += 1;
              continue;
            }
            const rawLabel = labelFor(control);
            if (!rawLabel) continue;
            const normalized = rawLabel.replace(/\s*\(\s*required\s*\)\s*$/i, '').trim();
            const known = direct[normalized.toLowerCase()];
            const safe = normalized.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
            const fieldId = known?.[0] || control.id || control.name || `polymer-${safe || 'custom'}-${customIndex++}`;
            const label = known?.[1] || normalized;
            control.setAttribute('data-nori-field', fieldId);
            control.setAttribute('aria-label', label);
            if (known && control.tagName === 'INPUT') control.setAttribute('type', known[2]);
            const ownLabels = clean(Array.from(control.labels || [])
              .map(label => label.textContent || '').join(' '));
            const context = `${ownLabels} ${clean(control.parentElement?.textContent)}`;
            if (control.required || control.getAttribute('aria-required') === 'true'
                || /\(\s*required\s*\)/i.test(context)) {
              control.setAttribute('aria-required', 'true');
            }
            tagged += 1;
          }
          return tagged;
        }""", direct) or 0)
    except Exception:
        return 0


def polymer_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture conservative Polymer-owned submission confirmation evidence.

    Args:
        page: Playwright-compatible result page after an authorized submit.
        timeout_ms: Maximum observation budget in milliseconds.

    Returns:
        dict: Structured receipt. Confirmation requires application-specific
        text in a success surface, or the same text with clear confirmation
        URL/title context. Generic thanks text alone is rejected. Never raises.
    """
    receipt = {
        "confirmed": False,
        "ats": "polymer",
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
    for selector in POLYMER_CONFIRM_SELECTORS:
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
        r"(?:confirmation|application|reference)\s*(?:id|number|#)\s*"
        r"[:#-]?\s*([A-Z0-9-]{5,40})", receipt["confirmationText"], re.I)
    if reference:
        receipt["confirmationId"] = reference.group(1)
    receipt["confirmed"] = bool(receipt["signals"])
    return receipt
