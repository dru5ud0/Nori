"""tsenta_linkedin — LinkedIn apply-URL resolution (port of the recovered engine).

Python port of the recovered Tsenta LinkedIn resolver
(`resolveLinkedInApplyUrl` in extension/background.js, the `linkedin-rsc.js`
flight parser, and the overlay's `Tt()`/`on()` URL decoders).

Algorithm (ported verbatim):
1. `linkedin_resolve_apply_url(job_id)`: GET https://www.linkedin.com/jobs/view/{id}/
   (session cookies optional — pass li_at via cookies=), then:
   a. LD+JSON `JobPosting.description` (>=100 chars, <=10000, tags stripped)
   b. RSC-flight parser: `JobCardFrameworkImpl…State_(\\d+)` markers +
      `safety/go/?url=` links, positional jobId correlation, first
      non-LinkedIn URL wins
   c. HTML fallbacks: safety/go hrefs, JSON apply keys
      (offsiteApplyUrl|companyApplyUrl|externalApplyUrl|applyUrl), nearby-text
      href heuristic, jobs-apply-button-id window
2. `linkedin_decode_safety_go(url)`: unescape -> up to 3x decodeURIComponent
   -> recursive safety/go unwrap -> reject final host ending linkedin.com.
  3. `linkedin_extract_job_id(url)`: /jobs/view/(\\d+) or currentJobId= param.

All public functions return strings/dicts and catch exceptions internally.
"""

from __future__ import annotations

import html
import json
import re
import urllib.request
from urllib.parse import parse_qs, unquote, urlsplit

_FLIGHT_MARKER_RE = re.compile(
    r"JobCardFrameworkImpl(?:Footer|Saved|Tracking|Logo|Insights|Top)?State_(\d+)"
)
_SAFETY_GO_RE = re.compile(r"https://www\.linkedin\.com/safety/go/\?url=[^\"\\\s]+")
_SAFETY_GO_HREF_RE = re.compile(
    r"href=([\"'])(https?://www\.linkedin\.com/safety/go/\?url=[^\"'<>]+)\1", re.IGNORECASE
)
_APPLY_URL_KEYS_RE = re.compile(
    r"\"(?:offsiteApplyUrl|companyApplyUrl|externalApplyUrl|applyUrl)\"\s*:\s*\"([^\"]+)\""
)
_NEARBY_APPLY_RE = re.compile(
    r"apply|offsite_apply|company website|apply on|jobdetails_apply|jobs-apply", re.IGNORECASE
)
_JOBS_APPLY_BUTTON_RE = re.compile(r"id=([\"'])jobs-apply-button-id\1", re.IGNORECASE)
_JSON_APPLY_URL_RE = re.compile(
    r"\"[^\"]*(?:offsite|external|company|apply)[^\"]*(?:url|uri|link)\"\s*:\s*\"([^\"]+)\"",
    re.IGNORECASE,
)
_ENCODED_URL_RE = re.compile(r"url=(https?%3A%2F%2F[^\"'&<>\s]+)", re.IGNORECASE)
_GENERIC_URL_RE = re.compile(r"https?://[^\s\"'<>\\]+", re.IGNORECASE)
_JOBS_VIEW_RE = re.compile(r"/jobs/view/(?:[a-zA-Z0-9\-_]+-)?(\d+)(?:/|\?|$)")
_CURRENT_JOB_ID_RE = re.compile(r"currentJobId=(\d+)")

_TITLE_REJECT = re.compile(
    r"^(viewed|saved|easy apply|posted|promoted|be an early|company alumni|featured|new$)",
    re.IGNORECASE,
)
_TITLE_CURRENCY_RE = re.compile(r"^\$")
_TITLE_AGE_RE = re.compile(r"^\d+\s+(days?|hours?|weeks?|months?|year|min)", re.IGNORECASE)
_TITLE_PROTO_RE = re.compile(r"^[\w$]+\.[\w$]+(\.[\w$]+)+")

_MAX_JD_CHARS = 10000
_MIN_JD_CHARS = 100
_TITLE_WINDOW = 5000


def _unescape_rsc(text: str) -> str:
    """3-pass RSC-flight string unescape (\\u0026 -> &, \\/ -> /, \\" -> \")."""
    current = text
    for _ in range(3):
        repaired = (
            current.replace("\\u0026", "&")
            .replace("\\u0025", "%")
            .replace("\\/", "/")
            .replace('\\"', '"')
        )
        if repaired == current:
            break
        current = repaired
    return current


_LINKEDIN_INTERNAL_DOMAINS = (
    "linkedin.com",
    "licdn.com",
    "lnkd.in",
    "linkedin.cn",
)

_STATIC_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".ico", ".css", ".js", ".woff", ".woff2", ".ttf", ".eot",
)


def is_linkedin_internal_host(host: str) -> bool:
    """Return True if host belongs to LinkedIn internal/CDN domains."""
    host = (host or "").lower().strip()
    return any(host == d or host.endswith("." + d) for d in _LINKEDIN_INTERNAL_DOMAINS)


def linkedin_decode_safety_go(url: str) -> str | None:
    """Decode a LinkedIn safety/go redirect to its real destination (port of Tt).

    Unescapes RSC strings, applies up to 3 decodeURIComponent passes, then
    recursively unwraps nested safety/go links. Returns None when the final
    destination is still on linkedin.com / licdn.com (Easy Apply / internal)
    or the input is malformed or points to a static media/asset URL.

    Args:
        url: raw URL string (safety/go link, encoded value, or plain URL).

    Returns:
        str: decoded destination URL, or None when not resolvable.
    """
    try:
        current = _unescape_rsc(url).replace("&amp;", "&").replace("&quot;", '"').strip()
        for _ in range(3):
            try:
                decoded = unquote(current)
            except Exception:
                break
            if decoded == current:
                break
            current = decoded
        if not current:
            return None
        if re.match(r"^https?://", current, re.IGNORECASE):
            try:
                parts = urlsplit(current)
                host = (parts.hostname or "").lower()
                if (host == "linkedin.com" or host.endswith(".linkedin.com")) and parts.path.startswith("/safety/go"):
                    query = parse_qs(parts.query)
                    target = query.get("url", [None])[0]
                    return linkedin_decode_safety_go(target) if target else None
                if is_linkedin_internal_host(host):
                    return None
                path_lower = (parts.path or "").lower()
                if any(path_lower.endswith(ext) for ext in _STATIC_EXTENSIONS):
                    return None
                return parts.geturl()
            except Exception:
                return None
        match = _GENERIC_URL_RE.search(current)
        if match:
            return linkedin_decode_safety_go(match.group(0))
        return None
    except Exception:
        return None


def _looks_like_title(text: str) -> bool:
    """Heuristic title validation (port of tt())."""
    title = re.sub(r"\s+", " ", text).strip()
    if len(title) < 8 or len(title) > 150 or " " not in title:
        return False
    if _TITLE_REJECT.match(title) or _TITLE_CURRENCY_RE.match(title):
        return False
    if _TITLE_AGE_RE.match(title):
        return False
    if "proto.sdui" in title or "JobCardFramework" in title:
        return False
    if _TITLE_PROTO_RE.match(title):
        return False
    return True


def linkedin_parse_flight(html_text: str) -> list:
    """Parse an RSC flight payload (page HTML or feed response) for job cards.

    Args:
        html_text: raw HTML/RSC text containing JobCardFramework markers and
            safety/go URLs.

    Returns:
        list of {"jobId": str, "title": str, "url": str} entries (nearest
        preceding marker + title window heuristics). Never raises.
    """
    if not html_text or len(html_text) < 100 or "safety/go" not in html_text:
        return []
    try:
        text = _unescape_rsc(html_text)
        markers = [(m.start(), m.group(1)) for m in _FLIGHT_MARKER_RE.finditer(text)]
        entries = []
        for match in _SAFETY_GO_RE.finditer(text):
            pos = match.start()
            raw_url = match.group(0)
            decoded = linkedin_decode_safety_go(raw_url)
            if not decoded:
                continue
            job_id = ""
            for marker_pos, marker_id in reversed(markers):
                if marker_pos < pos:
                    job_id = marker_id
                    break
            title = ""
            window = text[max(0, pos - _TITLE_WINDOW):pos]
            for tmatch in re.finditer(r'"text":"(.*?)"', window, re.DOTALL):
                candidate = tmatch.group(1)[:200]
                if _looks_like_title(candidate):
                    title = candidate
            entries.append({"jobId": job_id, "title": title, "url": decoded})
        return entries
    except Exception:
        return []


def _extract_from_html(html_text: str) -> str | None:
    """HTML-level fallback extraction (port of extractFromHtml)."""
    try:
        text = _unescape_rsc(html_text)
        # 5a. Direct safety/go hrefs
        for match in _SAFETY_GO_HREF_RE.finditer(text):
            decoded = linkedin_decode_safety_go(match.group(2))
            if decoded:
                return decoded
        # 5b. JSON apply keys
        for match in _APPLY_URL_KEYS_RE.finditer(text):
            decoded = linkedin_decode_safety_go(match.group(1))
            if decoded:
                return decoded
        # 5c. Nearby-text href heuristic (±220 chars around apply-ish text)
        lower = text.lower()
        for match in re.finditer(r"https?://[^\"'\s<>]+", text):
            href = match.group(0)
            start = max(0, match.start() - 220)
            end = min(len(lower), match.end() + 220)
            if _NEARBY_APPLY_RE.search(lower[start:end]):
                decoded = linkedin_decode_safety_go(href)
                if decoded:
                    return decoded
        # 5d. jobs-apply-button-id window (-8000/+24000)
        for match in _JOBS_APPLY_BUTTON_RE.finditer(text):
            start = max(0, match.start() - 8000)
            end = min(len(text), match.end() + 24000)
            window = text[start:end]
            for jmatch in _JSON_APPLY_URL_RE.finditer(window):
                decoded = linkedin_decode_safety_go(jmatch.group(1))
                if decoded:
                    return decoded
            for ematch in _ENCODED_URL_RE.finditer(window):
                decoded = linkedin_decode_safety_go(ematch.group(1))
                if decoded:
                    return decoded
            for umatch in _GENERIC_URL_RE.finditer(window):
                decoded = linkedin_decode_safety_go(umatch.group(0))
                if decoded:
                    return decoded
        return None
    except Exception:
        return None


def _clean_description(raw: str) -> str:
    """HTML-entity decode + tag strip + whitespace collapse (port of Oe/Re)."""
    try:
        text = html.unescape(raw)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text
    except Exception:
        return ""


def _extract_ld_json_description(html_text: str) -> str:
    """Extract the JobPosting description from application/ld+json blocks."""
    try:
        for block in re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', html_text, re.DOTALL
        ):
            try:
                data = json.loads(block)
            except Exception:
                continue
            candidates = data if isinstance(data, list) else [data]
            for entry in candidates:
                if not isinstance(entry, dict):
                    continue
                type_val = entry.get("@type")
                types = type_val if isinstance(type_val, list) else [type_val]
                if any(str(t).endswith("JobPosting") for t in types):
                    description = _clean_description(str(entry.get("description") or ""))
                    if len(description) >= _MIN_JD_CHARS:
                        return description[:_MAX_JD_CHARS]
    except Exception:
        pass
    return ""


def linkedin_extract_job_id(url: str) -> str:
    """Extract a numeric LinkedIn job id from a URL.

    Args:
        url: any LinkedIn job URL (jobs/view/123, feed link with
            currentJobId=, jobs/?jobId=).

    Returns:
        str: numeric job id, or "" when none is present. Never raises.
    """
    if not url:
        return ""
    try:
        view = _JOBS_VIEW_RE.search(url)
        if view:
            return view.group(1)
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        for key in ("currentJobId", "jobId"):
            if key in query and query[key]:
                value = query[key][0]
                if value.isdigit():
                    return value
        return ""
    except Exception:
        return ""


def linkedin_resolve_apply_url(job_id: str, cookies: str | None = None,
                               timeout: int = 30) -> str:
    """Resolve a LinkedIn job id to its external apply URL (port of
    resolveLinkedInApplyUrl).

    Fetches https://www.linkedin.com/jobs/view/{id}/ with the given cookies
    (pass li_at=...; JSESSIONID=... from the user's browser session — required
    for logged-in job pages), then runs: LD+JSON description extraction,
    RSC-flight URL resolution, then HTML fallbacks.

    Args:
        job_id: numeric LinkedIn job id (string or int).
        cookies: optional cookie header string (e.g. "li_at=abc; JSESSIONID=xyz").
        timeout: HTTP fetch timeout in seconds.

    Returns:
        str: JSON of {"ok": bool, "url": str, "jobDescription": str,
        "error": str | None}. Never raises.
    """
    result = {"ok": False, "url": "", "jobDescription": "", "error": None}
    try:
        if not str(job_id).isdigit():
            result["error"] = "invalid-job-id"
            return json.dumps(result)
        url = f"https://www.linkedin.com/jobs/view/{job_id}/"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if cookies:
            headers["Cookie"] = cookies
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            html_text = response.read().decode("utf-8", errors="replace")

        description = _extract_ld_json_description(html_text)
        if description:
            result["jobDescription"] = description

        # RSC-flight resolution: first non-LinkedIn URL wins.
        for entry in linkedin_parse_flight(html_text):
            target = entry.get("url") or ""
            target_host = (urlsplit(target).hostname or "").lower()
            if target and not is_linkedin_internal_host(target_host):
                result["ok"] = True
                result["url"] = target
                return json.dumps(result)

        # HTML fallback.
        fallback = _extract_from_html(html_text)
        if fallback:
            fallback_host = (urlsplit(fallback).hostname or "").lower()
            if not is_linkedin_internal_host(fallback_host):
                result["ok"] = True
                result["url"] = fallback
                return json.dumps(result)

        result["error"] = "no-external-apply-url"
        return json.dumps(result)
    except Exception as exc:
        result["error"] = str(exc) or type(exc).__name__
        return json.dumps(result)


def linkedin_resolve_from_url(url: str, cookies: str | None = None,
                              timeout: int = 30) -> str:
    """Resolve any LinkedIn job URL (page or feed link) to an apply URL.

    Args:
        url: LinkedIn job URL containing /jobs/view/{id} or currentJobId=.
        cookies: optional cookie header string (li_at etc.).
        timeout: HTTP fetch timeout in seconds.

    Returns:
        str: JSON of {"ok", "url", "jobDescription", "error", "jobId"}.
        Never raises.
    """
    job_id = linkedin_extract_job_id(url)
    if not job_id:
        return json.dumps({"ok": False, "url": "", "jobDescription": "",
                           "error": "no-job-id", "jobId": ""})
    result = json.loads(linkedin_resolve_apply_url(job_id, cookies=cookies,
                                                   timeout=timeout))
    result["jobId"] = job_id
    return json.dumps(result)


# ---- Guest-mode harvest (no login required) ----


_BASE = "https://www.linkedin.com"
_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_CARD_RE = re.compile(r'<div class="base-card[^"]*job-search-card[^"]*"([^>]*)>')
_CARD_LINK_RE = re.compile(r'href="(https?://[^"]*/jobs/view/[^"]+)"')
_CARD_TITLE_RE = re.compile(r'class="base-search-card__title"[^>]*>\s*([^<]+?)\s*<')
_CARD_COMPANY_RE = re.compile(
    r'class="base-search-card__subtitle"[^>]*>\s*(?:<a[^>]*>)?([^<]+?)\s*<'
)
_CARD_LOCATION_RE = re.compile(r'class="job-search-card__location"[^>]*>\s*([^<]+?)\s*<')
_CARD_POSTED_RE = re.compile(r'class="job-search-card__listdate"[^>]*datetime="([^"]+)"')
_URN_RE = re.compile(r'data-entity-urn="urn:li:jobPosting:(\d+)"')
_DETAIL_TITLE_RE = re.compile(
    r'<h2 class="top-card-layout__title[^"]*"[^>]*>\s*([^<]+?)\s*<'
)
_DETAIL_COMPANY_RE = re.compile(
    r'<a class="topcard__org-name-link[^"]*"[^>]*>\s*([^<]+?)\s*<'
)
_DETAIL_LOCATION_RE = re.compile(
    r'<span class="topcard__flavor topcard__flavor--bullet">\s*([^<]+?)\s*<'
)
_DETAIL_POSTED_RE = re.compile(
    r'<span class="posted-time-ago__text[^"]*"[^>]*>\s*([^<]+?)\s*<'
)
_DETAIL_DESC_RE = re.compile(
    r'<div class="show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>', re.DOTALL
)
_EASY_APPLY_RE = re.compile(r'class="jobs-apply-button[^"]*"')
_OFFSITE_RE = re.compile(r'class="jobs-apply-button[^"]*jobs-apply-button--offsite[^"]*"')


def _http_get(url: str, timeout: int = 25) -> tuple[int, str]:
    """GET a URL with browser UA. Returns (status, body)."""
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", "replace")


def linkedin_guest_search(
    keywords: str,
    location: str = "",
    pages: int = 1,
    delay: float = 2.0,
    timeout: int = 25,
) -> str:
    """Search LinkedIn jobs via the guest API (no login required).

    Args:
        keywords: search query string.
        location: location filter (default "").
        pages: number of 25-card pages to fetch (default 1).
        delay: seconds to wait between pages.
        timeout: HTTP fetch timeout in seconds.

    Returns:
        str: JSON of {"ok": bool, "cards": [{"jobId", "title", "company",
        "location", "posted", "url"}, ...], "error": str | None}. Never raises.
    """
    result = {"ok": False, "cards": [], "error": None}
    try:
        cards = []
        for page in range(pages):
            start = page * 25
            params = urllib.parse.urlencode(
                {"keywords": keywords, "location": location, "start": str(start)}
            )
            url = f"{_BASE}/jobs-guest/jobs/api/seeMoreJobPostings/search?{params}"
            _status, body = _http_get(url, timeout=timeout)
            page_cards = []
            for m in _CARD_RE.finditer(body):
                attrs = m.group(1)
                urn = _URN_RE.search(attrs)
                if not urn:
                    continue
                jid = urn.group(1)
                link = _CARD_LINK_RE.search(body[m.start():])
                title = _CARD_TITLE_RE.search(body[m.start():])
                company = _CARD_COMPANY_RE.search(body[m.start():])
                location_m = _CARD_LOCATION_RE.search(body[m.start():])
                posted = _CARD_POSTED_RE.search(body[m.start():])
                page_cards.append(
                    {
                        "jobId": jid,
                        "title": html.unescape(title.group(1)).strip() if title else None,
                        "company": html.unescape(company.group(1)).strip() if company else None,
                        "location": html.unescape(location_m.group(1)).strip()
                        if location_m
                        else None,
                        "posted": posted.group(1) if posted else None,
                        "url": (
                            html.unescape(link.group(1)).split("?")[0]
                            if link
                            else f"{_BASE}/jobs/view/{jid}"
                        ),
                    }
                )
            cards.extend(page_cards)
            if page < pages - 1 and delay > 0:
                import time as _time

                _time.sleep(delay)
        result["ok"] = True
        result["cards"] = cards
        return json.dumps(result)
    except Exception as exc:
        result["error"] = str(exc) or type(exc).__name__
        return json.dumps(result)


def linkedin_guest_detail(job_id: str, timeout: int = 25) -> str:
    """Fetch a single LinkedIn job detail page via the guest API.

    Args:
        job_id: numeric LinkedIn job posting id.
        timeout: HTTP fetch timeout in seconds.

    Returns:
        str: JSON of {"ok": bool, "job": {"jobId", "title", "company",
        "location", "posted", "posted_text", "description", "easy_apply",
        "external_apply", "apply_url_gated"}, "error": str | None}. Never raises.
    """
    result = {"ok": False, "job": {"jobId": str(job_id)}, "error": None}
    try:
        _status, body = _http_get(
            f"{_BASE}/jobs-guest/jobs/api/jobPosting/{job_id}", timeout=timeout
        )
        job = result["job"]
        job["title"] = _first_match(_DETAIL_TITLE_RE, body) or job.get("title")
        job["company"] = _first_match(_DETAIL_COMPANY_RE, body)
        job["location"] = _first_match(_DETAIL_LOCATION_RE, body)
        job["posted_text"] = _first_match(_DETAIL_POSTED_RE, body)
        dm = _DETAIL_DESC_RE.search(body)
        if dm:
            job["description"] = _clean_description(dm.group(1))
        job["easy_apply"] = bool(_EASY_APPLY_RE.search(body))
        job["external_apply"] = bool(_OFFSITE_RE.search(body))
        job["apply_url_gated"] = True
        result["ok"] = True
        return json.dumps(result)
    except Exception as exc:
        result["error"] = str(exc) or type(exc).__name__
        return json.dumps(result)


def _first_match(pattern: re.Pattern, text: str) -> str | None:
    """Return the first regex capture group match, stripped. Returns None on miss."""
    m = pattern.search(text)
    return html.unescape(m.group(1)).strip() if m else None