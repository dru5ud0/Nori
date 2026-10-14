"""Greenhouse-specific URL, form, and confirmation helpers."""

from __future__ import annotations

import re
import time
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit


GREENHOUSE_FORM_SELECTOR = (
    "form#application_form, form#application-form, "
    "form[action*='/applications'], [data-testid='application-form'], "
    "input[name*='job_application[first_name]'], "
    "input[autocomplete='given-name']"
)

GREENHOUSE_CONFIRM_SELECTORS = (
    "#application_confirmation",
    "[data-testid='application-success']",
    "[data-testid='application-confirmation']",
    ".application-confirmation",
    "[class*='ApplicationConfirmation']",
)

_CONFIRM_PATTERNS = (
    re.compile(r"\bthank you for applying\b", re.I),
    re.compile(r"\bthank you for your application\b", re.I),
    re.compile(r"\byour application has been submitted\b", re.I),
    re.compile(r"\bwe (?:have )?received your application\b", re.I),
    re.compile(r"\bapplication submitted successfully\b", re.I),
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


# Map of known company hostnames/domains -> their Greenhouse board slug.
# Resolves embed URLs when a company hosts careers on their own site
# with ?gh_jid= but the board slug cannot be inferred from the URL path.
_DOMAIN_TO_BOARD: dict[str, str] = {
    # Primary target companies
    "rubrik.com": "rubrik",
    "okta.com": "okta",
    "zscaler.com": "zscaler",
    "gitlab.com": "gitlab",
    "coinbase.com": "coinbase",
    "stripe.com": "stripe",
    "databricks.com": "databricks",
    "hashicorp.com": "hashicorp",
    "lacework.com": "lacework",
    "orca.security": "orcasecurity",
    "wiz.io": "wizsecurity",
    "snyk.io": "snyk",
    "crowdstrike.com": "crowdstrike",
    "paloaltonetworks.com": "paloaltonetworks",
    "sentinelone.com": "sentinelone",
    "darktrace.com": "darktrace",
    "cyberark.com": "cyberark",
    "sailpoint.com": "sailpoint",
    "saviynt.com": "saviynt",
    "beyondtrust.com": "beyondtrust",
    "pingidentity.com": "pingidentity",
    "ping.com": "pingidentity",
    "forgerock.com": "forgerock",
    "onelogin.com": "onelogin",
    "duo.com": "duo",
    "cisco.com": "cisco",
    "cloudflare.com": "cloudflare",
    "fastly.com": "fastly",
    "datadog.com": "datadoghq",
    "elastic.co": "elastic",
    "mongodb.com": "mongodb",
    "figma.com": "figma",
    "notion.so": "notion",
    "linear.app": "linear",
    "vercel.com": "vercel",
    "netlify.com": "netlify",
    "supabase.com": "supabase",
    "cockroachlabs.com": "cockroachlabs",
    "neon.tech": "neon",
    # India / Bangalore targets
    "meesho.com": "meesho",
    "razorpay.com": "razorpay",
    "freshworks.com": "freshworks",
    "flipkart.com": "flipkart",
    "phonepe.com": "phonepe",
    "browserstack.com": "browserstack",
    "hasura.io": "hasura",
    "chargebee.com": "chargebee",
    "postman.com": "postman",
    "clevertap.com": "clevertap",
    "moengage.com": "moengage",
    "sharechat.com": "sharechat",
    "smallcase.com": "smallcase",
    "groww.in": "groww",
    "kreditbee.com": "kreditbee",
    "cuemath.com": "cuemath",
    "unacademy.com": "unacademy",
    "licious.in": "licious",
    "ninjacart.in": "ninjacart",
    "delhivery.com": "delhivery",
    "shiprocket.in": "shiprocket",
}


def _board_from_hostname(hostname: str) -> str:
    """Look up the Greenhouse board slug for a known company hostname."""
    hostname = (hostname or "").lower().lstrip("www.")
    if hostname in _DOMAIN_TO_BOARD:
        return _DOMAIN_TO_BOARD[hostname]
    # Try apex domain match (last two parts)
    parts = hostname.split(".")
    if len(parts) >= 2:
        apex = ".".join(parts[-2:])
        if apex in _DOMAIN_TO_BOARD:
            return _DOMAIN_TO_BOARD[apex]
    return ""


def greenhouse_url_candidates(url: str) -> list:
    """Return normalized Greenhouse job/apply URLs, embed URL prioritized first.

    Supports modern and classic board URLs plus embedded ``for``/``token``
    query shapes. For company-hosted pages with only ``gh_jid``, uses
    ``_DOMAIN_TO_BOARD`` to resolve the board slug when possible so we can
    build a direct embed URL that bypasses company-site bot guards.
    """
    try:
        value = _decode(url).strip()
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return []
        candidates = [urlunsplit(parts)]
        query = parse_qs(parts.query)
        segments = [segment for segment in parts.path.split("/") if segment]
        board = ""
        job_id = ""
        if parts.hostname.lower() in ("boards.greenhouse.io", "job-boards.greenhouse.io"):
            if segments and segments[0] not in ("embed", "job_app"):
                board = segments[0]
            if "jobs" in segments:
                index = segments.index("jobs")
                if index + 1 < len(segments):
                    job_id = segments[index + 1]
        board = str((query.get("for") or [board])[0] or board)
        job_id = str((query.get("token") or query.get("gh_jid")
                      or query.get("greenhouse_jid") or [job_id])[0] or job_id)
        # If we have job_id but no board, try domain lookup table
        if job_id and job_id.isdigit() and not board:
            board = _board_from_hostname(parts.hostname or "")
        if board and job_id and job_id.isdigit():
            candidates.extend([
                # Embed URL first — bypasses company-site bot detection (403s)
                f"https://boards.greenhouse.io/embed/job_app?for={board}&token={job_id}",
                f"https://job-boards.greenhouse.io/{board}/jobs/{job_id}",
                f"https://boards.greenhouse.io/{board}/jobs/{job_id}",
            ])
        return list(dict.fromkeys(item.rstrip("/") for item in candidates if item))
    except Exception:
        return []


def greenhouse_confirmation_receipt(page, timeout_ms: int = 10000) -> dict:
    """Capture Greenhouse-owned submission evidence from the resulting page."""
    receipt = {
        "confirmed": False,
        "ats": "greenhouse",
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
    for selector in GREENHOUSE_CONFIRM_SELECTORS:
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
        body_text = (page.locator("body").inner_text(timeout=min(timeout_ms, 5000)) or "").strip()
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
