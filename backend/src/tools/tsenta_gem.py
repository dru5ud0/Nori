"""Gem ATS public-job routing, form normalization, and receipt evidence."""

from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlsplit, urlunsplit


GEM_FORM_SELECTOR = (
    "input[data-1p-ignore='true'], input[type='file'], "
    "button[type='submit']"
)

GEM_CONFIRM_SELECTORS = (
    "[data-testid*='application-success' i]",
    "[data-testid*='application-confirmation' i]",
    "[class*='application-success' i]",
    "[class*='application-confirmation' i]",
)

_CLOSED_PATTERNS = (
    "this job is no longer available",
    "this position is no longer available",
    "this job posting is no longer available",
    "this role is no longer accepting applications",
    "no longer accepting applications",
    "job post is no longer active",
)

_CONFIRM_PATTERNS = (
    re.compile(r"\byour application has been (?:received|submitted)\b", re.I),
    re.compile(r"\bwe (?:have )?received your application\b", re.I),
    re.compile(r"\bapplication (?:was |has been )?submitted successfully\b", re.I),
    re.compile(r"\bthanks? for applying\b", re.I),
)

_DIRECT_FIELDS = {
    "first name": ("firstName", "First Name", "text"),
    "last name": ("lastName", "Last Name", "text"),
    "email": ("email", "Email", "email"),
    "linkedin url": ("linkedinUrl", "LinkedIn URL", "url"),
    "linkedin profile url": ("linkedinUrl", "LinkedIn URL", "url"),
    "phone number": ("phone", "Phone Number", "tel"),
    # Gem asks for one free-form location. The profile's city is the most
    # conservative direct value; Nori never invents a street address here.
    "location": ("city", "City", "text"),
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


def gem_url_candidates(url: str) -> list:
    """Return one safe canonical Gem public-job URL.

    Args:
        url: Candidate URL expected to use ``jobs.gem.com/<board>/<job-id>``.

    Returns:
        list: Canonical HTTPS job URL with tracking query and fragment removed,
        or an empty list for an invalid, insecure, or non-Gem URL. Never raises.
    """
    try:
        parts = urlsplit(_decode(url).strip())
        host = (parts.hostname or "").lower()
        path = parts.path.rstrip("/")
        if (parts.scheme != "https" or host != "jobs.gem.com"
                or not re.fullmatch(r"/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+", path)):
            return []
        return [urlunsplit(("https", parts.netloc, path, "", ""))]
    except Exception:
        return []


def gem_job_closed(page) -> bool:
    """Return whether Gem explicitly reports that the posting is closed.

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


def gem_prepare_form(page) -> int:
    """Add stable semantics to Gem's generated React application controls.

    Gem's hosted form currently omits names and accessible labels from its
    identity inputs, and its sponsorship radios also omit a shared name/value.
    This function tags only the application surface, keeps voluntary EEO menus
    untouched, and does not click a submit or consent control.

    Args:
        page: Playwright-compatible Gem job page with the form rendered.

    Returns:
        int: Number of application controls tagged. Never raises.
    """
    try:
        direct = {key: list(value) for key, value in _DIRECT_FIELDS.items()}
        return int(page.evaluate(r"""direct => {
          const clean = value => (value || '').replace(/\s+/g, ' ').trim();
          const submit = Array.from(document.querySelectorAll('button[type="submit"]'))
            .find(button => /apply (?:and save|without saving)/i.test(clean(button.textContent)))
            || document.querySelector('button[type="submit"]');
          if (!submit) return 0;
          let root = submit.parentElement;
          while (root && root !== document.body) {
            const inputCount = root.querySelectorAll('input').length;
            if (inputCount >= 4 && root.querySelector('input[type="file"]')) break;
            root = root.parentElement;
          }
          if (!root || root === document.body) return 0;
          root.setAttribute('data-nori-scope', 'gem-application');
          let tagged = 0;
          let customIndex = 0;
          const labelFor = control => {
            let node = control.parentElement;
            for (let depth = 0; node && node !== root && depth < 8;
                 depth += 1, node = node.parentElement) {
              const child = Array.from(node.children).find(candidate => {
                if (candidate === control || candidate.contains(control)) return false;
                if (candidate.querySelector('input, textarea, select, button')) return false;
                const text = clean(candidate.textContent).replace(/\s*\*\s*$/, '');
                return text && text.length <= 180;
              });
              if (child) return clean(child.textContent).replace(/\s*\*\s*$/, '');
            }
            return '';
          };
          for (const control of root.querySelectorAll(
              'input:not([type="hidden"]):not([type="radio"]):not([type="file"]), textarea')) {
            const rawLabel = labelFor(control);
            if (!rawLabel) continue;
            const key = rawLabel.toLowerCase();
            const known = direct[key];
            const safe = rawLabel.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
            const fieldId = known?.[0] || `gem-${safe || 'custom'}-${customIndex++}`;
            const label = known?.[1] || rawLabel;
            const type = known?.[2] || (control.tagName === 'TEXTAREA' ? 'text' : control.type || 'text');
            control.setAttribute('data-nori-field', fieldId);
            control.setAttribute('aria-label', label);
            if (known && control.tagName === 'INPUT') control.setAttribute('type', type);
            const fieldText = clean(control.closest('[style*="flex-direction: column"]')?.textContent);
            if (/\*/.test(fieldText) || rawLabel.endsWith('*')) {
              control.setAttribute('aria-required', 'true');
            }
            tagged += 1;
          }
          const resume = root.querySelector('input[type="file"]');
          if (resume) {
            resume.setAttribute('data-nori-field', 'resume');
            resume.setAttribute('aria-label', 'Resume');
            resume.setAttribute('aria-required', 'true');
            tagged += 1;
          }
          const radios = Array.from(root.querySelectorAll('input[type="radio"]'));
          if (radios.length && /require sponsorship/i.test(clean(root.textContent))) {
            const question = 'Will you now or in the future require sponsorship for employment visa status in the United States?';
            radios.forEach(radio => {
              const option = clean(document.querySelector(`label[for="${CSS.escape(radio.id)}"]`)?.textContent);
              radio.setAttribute('data-nori-field', 'needsSponsorship');
              radio.setAttribute('data-nori-question', question);
              radio.setAttribute('name', 'gem-sponsorship');
              radio.setAttribute('value', option || radio.value || '');
              radio.setAttribute('aria-required', 'true');
              tagged += 1;
            });
          }
          return tagged;
        }""", direct) or 0)
    except Exception:
        return 0


def gem_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture conservative Gem-owned submission confirmation evidence.

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
        "ats": "gem",
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
    for selector in GEM_CONFIRM_SELECTORS:
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
        r"(?:confirmation|application|reference|request)\s*"
        r"(?:id|number|#)\s*[:#-]?\s*([A-Z0-9-]{5,40})",
        receipt["confirmationText"], re.I)
    if reference:
        receipt["confirmationId"] = reference.group(1)
    receipt["confirmed"] = bool(receipt["signals"])
    return receipt
