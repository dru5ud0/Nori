"""Indeed job routing, identity checkpoints, form semantics, and receipts.

Indeed exposes two materially different apply paths: a hosted SmartApply flow
and an employer-site handoff.  Both can require an Indeed account before the
application is exposed.  This adapter keeps those states distinct so Nori
never treats a sign-in page or an external landing page as a completed draft.
"""

from __future__ import annotations

import re
import time
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit


INDEED_FORM_SELECTOR = (
    "form input:not([type='hidden']), form select, form textarea, "
    "[data-testid*='resume' i] input[type='file'], "
    "[data-testid*='question' i] input, [data-testid*='question' i] textarea"
)

INDEED_AUTH_SELECTOR = (
    "input[type='email'], input[autocomplete='email'], "
    "button:has-text('Continue with Google'), button:has-text('Continue with Apple')"
)

INDEED_CONFIRM_SELECTORS = (
    ".ia-ConfirmationPage",
    "[data-testid*='application-confirmation' i]",
    "[data-testid*='application-success' i]",
    "[class*='application-confirmation' i]",
)

_CLOSED_PATTERNS = (
    "this job is no longer available",
    "this job has expired",
    "this position is no longer available",
    "this job is no longer accepting applications",
    "the employer is no longer accepting applications",
)

_CONFIRM_PATTERNS = (
    re.compile(r"\byour application has been (?:received|submitted)\b", re.I),
    re.compile(r"\bwe (?:have )?received your application\b", re.I),
    re.compile(r"\bapplication (?:was |has been )?submitted successfully\b", re.I),
    re.compile(r"\byou applied (?:on|to)\b", re.I),
)

_DIRECT_FIELDS = {
    "first name": ("firstName", "First Name", "text"),
    "last name": ("lastName", "Last Name", "text"),
    "full name": ("fullName", "Full Name", "text"),
    "name": ("fullName", "Full Name", "text"),
    "email": ("email", "Email", "email"),
    "email address": ("email", "Email", "email"),
    "phone": ("phone", "Phone Number", "tel"),
    "phone number": ("phone", "Phone Number", "tel"),
    "city": ("city", "City", "text"),
    "location": ("location", "Current Location", "text"),
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


def _indeed_host(host: str) -> bool:
    value = str(host or "").lower().rstrip(".")
    return value == "indeed.com" or value.endswith(".indeed.com")


def indeed_owned_url(url: str) -> bool:
    """Return whether a URL belongs to an HTTPS Indeed-owned web host.

    Args:
        url: Absolute candidate URL.

    Returns:
        bool: True for HTTPS ``indeed.com`` hosts, including SmartApply and
        secure identity subdomains. Spoofed suffixes are rejected. Never
        raises.
    """
    try:
        parts = urlsplit(str(url or "").strip())
        return parts.scheme == "https" and _indeed_host(parts.hostname or "")
    except Exception:
        return False


def indeed_url_candidates(url: str) -> list:
    """Return a stable canonical Indeed job-detail URL.

    Args:
        url: Indeed ``viewjob`` URL containing a ``jk`` job identifier.

    Returns:
        list: One HTTPS job URL containing only the stable ``jk`` parameter,
        or an empty list for a search, auth, insecure, or spoofed URL. Never
        raises.
    """
    try:
        parts = urlsplit(_decode(url).strip())
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        job_key = str(query.get("jk") or "").strip()
        if (parts.scheme != "https" or not _indeed_host(parts.hostname or "")
                or parts.path.rstrip("/").lower() != "/viewjob"
                or not re.fullmatch(r"[A-Za-z0-9_-]{6,80}", job_key)):
            return []
        return [urlunsplit(("https", parts.netloc, "/viewjob",
                            urlencode({"jk": job_key}), ""))]
    except Exception:
        return []


def indeed_job_closed(page) -> bool:
    """Return whether Indeed explicitly reports that the posting is closed.

    Args:
        page: Playwright-compatible Indeed job page.

    Returns:
        bool: True only for a known closed-job message. Never raises.
    """
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").lower()[:10000]
        return any(pattern in text for pattern in _CLOSED_PATTERNS)
    except Exception:
        return False


def indeed_browser_blocked(page) -> bool:
    """Return whether Indeed blocked the isolated application browser.

    Args:
        page: Playwright-compatible Indeed page.

    Returns:
        bool: True only for Indeed's explicit Request Blocked surface or a
        human-verification page. Never attempts to bypass the control and
        never raises.
    """
    try:
        title = str(page.title() or "").lower()
        text = (page.locator("body").inner_text(timeout=2500) or "").lower()[:6000]
        return (("blocked" in title and "request blocked" in text
                 and "you have been blocked" in text)
                or "verify you are human" in text)
    except Exception:
        return False


def indeed_apply_target(page) -> str:
    """Return the visible Indeed apply control's absolute destination URL.

    Args:
        page: Playwright-compatible Indeed job page.

    Returns:
        str: HTTPS target for hosted SmartApply or employer handoff, otherwise
        an empty string. The function never clicks or raises.
    """
    try:
        selectors = (
            "a[href*='smartapply.indeed.com']",
            "a:has-text('Apply now')",
            "a:has-text('Apply on company site')",
            "a[data-testid*='apply' i]",
        )
        for selector in selectors:
            for node in page.query_selector_all(selector):
                try:
                    if hasattr(node, "is_visible") and not node.is_visible():
                        continue
                    href = str(node.get_attribute("href") or "").strip()
                    target = urljoin(str(getattr(page, "url", "") or ""), href)
                    parts = urlsplit(target)
                    if parts.scheme == "https" and parts.hostname:
                        return target
                except Exception:
                    continue
    except Exception:
        pass
    return ""


def indeed_account_required(page) -> bool:
    """Return whether Indeed is waiting for candidate sign-in/registration.

    Args:
        page: Playwright-compatible page after following an apply control.

    Returns:
        bool: True for Indeed's account gateway. This function never types,
        clicks a provider, creates an account, or raises.
    """
    try:
        parts = urlsplit(str(getattr(page, "url", "") or ""))
        if (parts.hostname or "").lower() != "secure.indeed.com":
            return False
        auth = page.query_selector(INDEED_AUTH_SELECTOR)
        text = (page.locator("body").inner_text(timeout=2500) or "").lower()[:4000]
        return (parts.path.lower().startswith("/auth") and auth is not None
                and ("create an account or sign in" in text
                     or "ready to take the next step" in text
                     or "continue with google" in text))
    except Exception:
        return False


def indeed_phone_verification_required(page) -> bool:
    """Return whether Indeed is waiting for a user-controlled phone check.

    Args:
        page: Playwright-compatible Indeed identity/application page.

    Returns:
        bool: True only when URL or visible copy identifies a phone/OTP
        verification step. The function never requests or enters a code.
    """
    try:
        url = str(getattr(page, "url", "") or "").lower()
        text = (page.locator("body").inner_text(timeout=2500) or "").lower()[:5000]
        url_gate = bool(re.search(r"phone[-_/]?(?:verify|verification)|verify[-_/]?phone", url))
        text_gate = bool(re.search(
            r"(?:verify|confirm) (?:your )?phone(?: number)?|"
            r"enter (?:the )?(?:verification|security) code", text))
        return url_gate or text_gate
    except Exception:
        return False


def indeed_application_surface_visible(page) -> bool:
    """Return whether an actual Indeed-hosted application form is visible.

    Args:
        page: Playwright-compatible Indeed or SmartApply page.

    Returns:
        bool: True only for visible non-auth application controls. Never
        raises.
    """
    try:
        if indeed_account_required(page) or indeed_phone_verification_required(page):
            return False
        parts = urlsplit(str(getattr(page, "url", "") or ""))
        host = (parts.hostname or "").lower()
        path = parts.path.lower()
        if host != "smartapply.indeed.com" and "indeedapply" not in path:
            return False
        nodes = page.query_selector_all(INDEED_FORM_SELECTOR)
        visible = [node for node in nodes if (
            not hasattr(node, "is_visible") or node.is_visible())]
        if not visible:
            return False
        text = (page.locator("body").inner_text(timeout=1800) or "").lower()[:6000]
        return bool("application" in text or "resume" in text or "contact information" in text)
    except Exception:
        return False


def indeed_prepare_form(page) -> int:
    """Add stable labels to an exposed Indeed-hosted application step.

    Args:
        page: Playwright-compatible SmartApply page with a real form visible.

    Returns:
        int: Number of controls tagged. CAPTCHA response fields are ignored;
        consent and employer questions remain visible for review. Never clicks
        Continue/Submit and never raises.
    """
    try:
        direct = {key: list(value) for key, value in _DIRECT_FIELDS.items()}
        return int(page.evaluate(r"""direct => {
          const clean = value => (value || '').replace(/\s+/g, ' ').trim();
          const visible = node => !!(node && (node.offsetWidth || node.offsetHeight || node.getClientRects().length));
          const forms = Array.from(document.querySelectorAll('form')).filter(visible);
          let root = forms.find(form => form.querySelector(
            'input[type="file"], input[autocomplete="given-name"], textarea, select'));
          if (!root) root = forms.find(form => form.querySelector('input:not([type="hidden"])'));
          if (!root) return 0;
          root.setAttribute('data-nori-scope', 'indeed-application');
          root.querySelectorAll(
            '[name="g-recaptcha-response"], [name="h-captcha-response"], [name="cf-turnstile-response"]'
          ).forEach(control => control.setAttribute('data-nori-ignore', 'true'));
          let tagged = 0;
          let customIndex = 0;
          const labelFor = control => {
            const labels = clean(Array.from(control.labels || [])
              .map(label => label.textContent || '').join(' '));
            if (labels) return labels;
            const aria = clean(control.getAttribute('aria-label'));
            if (aria) return aria;
            const labelledBy = clean((control.getAttribute('aria-labelledby') || '')
              .split(/\s+/).filter(Boolean)
              .map(id => document.getElementById(id)?.textContent || '').join(' '));
            if (labelledBy) return labelledBy;
            const placeholder = clean(control.getAttribute('placeholder'));
            if (placeholder) return placeholder;
            let node = control.parentElement;
            for (let depth = 0; node && node !== root && depth < 6;
                 depth += 1, node = node.parentElement) {
              const candidate = Array.from(node.children).find(child => {
                if (child === control || child.contains(control)) return false;
                if (child.querySelector('input, textarea, select, button')) return false;
                const text = clean(child.textContent);
                return text && text.length <= 500;
              });
              if (candidate) return clean(candidate.textContent);
            }
            return '';
          };
          for (const control of root.querySelectorAll(
              'input:not([type="hidden"]):not([type="submit"]):not([type="button"]), select, textarea')) {
            if (control.getAttribute('data-nori-ignore') === 'true') continue;
            const rawLabel = labelFor(control).replace(/\s*[*(]\s*(?:required)?\s*[*)]?\s*$/i, '').trim();
            const autocomplete = (control.getAttribute('autocomplete') || '').toLowerCase();
            let known = direct[rawLabel.toLowerCase()];
            if (!known && autocomplete === 'given-name') known = direct['first name'];
            if (!known && autocomplete === 'family-name') known = direct['last name'];
            if (!known && autocomplete === 'email') known = direct['email'];
            if (!known && autocomplete === 'tel') known = direct['phone'];
            if (control.type === 'file') known = ['resume', 'Resume', 'file'];
            const safe = rawLabel.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
            const fieldId = known?.[0] || control.id || control.name || `indeed-${safe || 'custom'}-${customIndex++}`;
            const label = known?.[1] || rawLabel || fieldId;
            control.setAttribute('data-nori-field', fieldId);
            control.setAttribute('aria-label', label);
            if (known && control.tagName === 'INPUT' && control.type !== 'file') {
              control.setAttribute('type', known[2]);
            }
            if (control.type === 'checkbox') {
              control.setAttribute('data-nori-single-checkbox', 'true');
            }
            const ownLabels = clean(Array.from(control.labels || [])
              .map(labelNode => labelNode.textContent || '').join(' '));
            if (control.required || control.getAttribute('aria-required') === 'true'
                || /\*|\brequired\b/i.test(ownLabels)) {
              control.setAttribute('aria-required', 'true');
            }
            tagged += 1;
          }
          return tagged;
        }""", direct) or 0)
    except Exception:
        return 0


def indeed_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture conservative Indeed-owned submission confirmation evidence.

    Args:
        page: Playwright-compatible result page after an authorized submit.
        timeout_ms: Maximum observation budget in milliseconds.

    Returns:
        dict: Structured receipt. Specific application text must appear in a
        success surface, or on an Indeed confirmation route. Generic thanks
        copy on a job page is rejected. Never raises.
    """
    receipt = {
        "confirmed": False,
        "ats": "indeed",
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
    for selector in INDEED_CONFIRM_SELECTORS:
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
    parts = urlsplit(receipt["url"])
    owned = _indeed_host(parts.hostname or "")
    context = owned and bool(re.search(
        r"/(?:apply|postapply|post-apply)/(?:confirmation|complete|submitted|success)\b|"
        r"application[-_ ](?:confirmation|complete|submitted)",
        receipt["url"] + " " + title, re.I))
    if context and not receipt["signals"]:
        for pattern in _CONFIRM_PATTERNS:
            match = pattern.search(body)
            if match:
                receipt["signals"].append({"kind": "context+text", "value": match.group(0)})
                start = max(0, match.start() - 120)
                receipt["confirmationText"] = body[start:match.end() + 240].strip()[:2000]
                break
    reference = re.search(
        r"(?:confirmation|application|reference)\s*(?:id|number|#)\s*[:#-]?\s*"
        r"([A-Z0-9-]{5,40})", receipt["confirmationText"], re.I)
    if reference:
        receipt["confirmationId"] = reference.group(1)
    receipt["confirmed"] = bool(receipt["signals"])
    return receipt
