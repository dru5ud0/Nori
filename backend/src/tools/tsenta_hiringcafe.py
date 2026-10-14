"""HiringCafe discovery and explainable local match ranking for Nori AI.

The adapter reads HiringCafe's public Next.js search payload in a short-lived
Playwright browser, normalizes direct employer apply URLs, and ranks results
against the local candidate profile. It never calls Tsenta's backend.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from hashlib import sha1

try:
    from backend.src.tools.tsenta_ats import ats_detect_chain, ats_extract_candidates
except ImportError:
    from tsenta_ats import ats_detect_chain, ats_extract_candidates


BASE_URL = "https://hiringcafe.com/"
_STOP_WORDS = {
    "a", "an", "and", "at", "for", "in", "job", "jobs", "of", "on",
    "or", "role", "the", "to", "with",
}
_ATS_PRIORITY = {
    "greenhouse": 8, "lever": 7, "ashby": 6, "workable": 5,
    "workday": 4, "smartrecruiters": 3,
}


def _search_url(query: str, page: int, saved_search_url: str = '') -> str:
    native = {}
    if saved_search_url:
        parsed = urllib.parse.urlsplit(saved_search_url)
        if parsed.scheme != 'https' or parsed.hostname not in ('hiringcafe.com', 'www.hiringcafe.com', 'hiring.cafe', 'www.hiring.cafe'):
            raise ValueError('Use an HTTPS HiringCafe search URL')
        raw = urllib.parse.parse_qs(parsed.query).get('searchState', ['{}'])[0]
        native = json.loads(raw)
        if not isinstance(native, dict):
            raise ValueError('HiringCafe searchState must be an object')
    if query:
        native['searchQuery'] = query
    state = json.dumps(native, separators=(",", ":"))
    return BASE_URL + "?" + urllib.parse.urlencode({"searchState": state, "page": page})


def _canonical_url(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(str(value or ""))
        if parsed.scheme != "https" or not parsed.hostname:
            return ""
        kept = [
            (key, item) for key, item in urllib.parse.parse_qsl(parsed.query)
            if not key.lower().startswith("utm_")
            and key.lower() not in {"source", "ref", "referrer", "trk"}
        ]
        return urllib.parse.urlunsplit((
            "https", parsed.netloc.lower(), parsed.path.rstrip("/"),
            urllib.parse.urlencode(kept), "",
        ))
    except Exception:
        return ""


def _direct_apply_url(value: str) -> str:
    url = _canonical_url(value)
    if not url:
        return ""
    direct = [candidate for candidate in ats_extract_candidates(url)
              if ats_detect_chain(candidate).get("ats_id") != "unknown"]
    if direct:
        return _canonical_url(direct[0])
    return url


def _text_list(value) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item.get('name') or item.get('label') or '') if isinstance(item, dict)
            else str(item).strip() for item in value if item]


def _signature(value: str, company: bool = False) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
    if company:
        normalized = re.sub(
            r"\s+(?:usa|us|inc|llc|ltd|corp|corporation|company)$", "", normalized,
        ).strip()
    return normalized


def _normalize_hit(hit: dict) -> dict | None:
    if not isinstance(hit, dict) or hit.get("is_expired") is True:
        return None
    info = hit.get("job_information") or {}
    processed = hit.get("v5_processed_job_data") or {}
    url = _direct_apply_url(hit.get("apply_url") or "")
    title = str(info.get("title") or info.get("job_title_raw") or "").strip()
    company = str(processed.get("company_name") or "").strip()
    if not (url and title and company):
        return None
    detection = ats_detect_chain(url)
    ats_id = detection.get("ats_id", "unknown")
    workplace = str(processed.get("workplace_type") or "")
    description_parts = [processed.get("requirements_summary") or ""]
    description_parts.extend(_text_list(processed.get("role_activities")))
    description_parts.extend(_text_list(processed.get("technical_tools")))
    domain = str(processed.get("company_website") or processed.get("company_domain") or "")
    if domain.startswith("http"):
        domain = urllib.parse.urlsplit(domain).hostname or ""
    job_id = str(hit.get("objectID") or hit.get("id") or "")
    if not job_id:
        job_id = "hc_" + sha1(url.encode("utf-8")).hexdigest()[:12]
    return {
        "id": job_id,
        "title": title,
        "url": url,
        "location": str(processed.get("formatted_workplace_location") or "").strip(),
        "updated_at": str(processed.get("estimated_publish_date") or ""),
        "companyName": company,
        "companyDomain": domain.strip().lower(),
        "logoUrl": "",
        "atsType": ats_id if ats_id != "unknown" else str(hit.get("source") or "unknown"),
        "source": "hiringcafe",
        "remote": workplace.lower() == "remote"
                  or processed.get("is_workplace_worldwide_ok") is True,
        "country": ", ".join(_text_list(processed.get("workplace_countries"))),
        "salaryMin": processed.get("yearly_min_compensation"),
        "salaryMax": processed.get("yearly_max_compensation"),
        "currency": processed.get("listed_compensation_currency") or "",
        "experienceLevel": str(processed.get("seniority_level") or ""),
        "skills": _text_list(processed.get("technical_tools"))
                  + _text_list(processed.get("licenses_or_certifications")),
        "description": "\n".join(part for part in description_parts if part).strip(),
    }


def _normalize_hits(hits: list) -> list[dict]:
    by_signature: dict[tuple[str, str], dict] = {}
    for hit in hits or []:
        try:
            job = _normalize_hit(hit)
            if not job:
                continue
            key = (_signature(job["title"]), _signature(job["companyName"], company=True))
            current = by_signature.get(key)
            if current is None or _ATS_PRIORITY.get(job["atsType"], 1) > _ATS_PRIORITY.get(
                    current.get("atsType"), 1):
                by_signature[key] = job
        except Exception:
            continue
    return list(by_signature.values())


def _tokens(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9+#.]+", str(value or "").lower())
        if len(token) > 1 and token not in _STOP_WORDS
    }


_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

_SECURITY_CERTS = {
    "cissp": r"\bcissp\b|certified information systems security professional",
    "cisa": r"\bcisa\b|certified information systems auditor",
    "cism": r"\bcism\b|certified information security manager",
    "security+": r"security\s*\+|comptia security plus",
    "gcih": r"\bgcih\b",
    "gcia": r"\bgcia\b",
    "gcfa": r"\bgcfa\b",
    "ceh": r"\bceh\b|certified ethical hacker",
    "oscp": r"\boscp\b",
}


def _profile_years(profile: dict) -> int | None:
    """Return explicitly stated candidate years of experience, if present."""
    try:
        info = profile.get("personalInformation") or {}
        text = " ".join(str(info.get(key) or "") for key in ("summary", "title"))
        match = re.search(
            r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s*\+?\s+years?\b",
            text, re.I)
        if not match:
            return None
        token = match.group(1).lower()
        return int(token) if token.isdigit() else _NUMBER_WORDS.get(token)
    except Exception:
        return None


def _requirement_fit(job: dict, profile: dict) -> tuple[int, list[str]]:
    """Return a conservative penalty and explicit hard-requirement warnings."""
    try:
        text = " ".join(str(job.get(key) or "") for key in
                        ("title", "description", "experienceLevel")).lower()
        penalty = 0
        warnings = []
        background = profile.get("backgroundCheck") or {}
        authorization = profile.get("workAuthorization") or {}

        clearance = bool(re.search(
            r"\b(?:active\s+)?(?:security|public trust|secret|top secret|ts[/ ]sci|"
            r"government|federal security)\s+clearance\b",
            text))
        ability_to_obtain = bool(re.search(
            r"\b(?:ability|eligible) to obtain(?: and maintain)?\b.{0,45}\bclearance\b|"
            r"\bclearance\b.{0,65}\b(?:ability|eligible) to obtain(?: and maintain)?\b",
            text))
        if clearance and background.get("hasGovernmentClearance") is not True:
            if ability_to_obtain:
                penalty += 8
                warnings.append("Security clearance eligibility needs review")
            else:
                penalty += 28
                warnings.append("Active security clearance appears required")

        if re.search(r"\bu\.?s\.? citizenship (?:is )?required\b|\bmust be (?:a )?u\.?s\.? citizen\b",
                     text):
            countries = {str(value or "").strip().upper() for value in
                         authorization.get("citizenshipCountries") or []}
            if not countries.intersection({"US", "USA", "UNITED STATES"}):
                penalty += 22
                warnings.append("U.S. citizenship requirement is not confirmed in profile")

        candidate_years = _profile_years(profile)
        experience_values = [int(value) for value in re.findall(
            r"\b(\d{1,2})\s*(?:\+|[-–—]\s*\d{1,2})?\s+years?"
            r"(?:\s+of)?\s+[^.;\n]{0,45}?\bexperience\b", text)]
        required_years = max(experience_values) if experience_values else None
        if (candidate_years is not None and required_years is not None and
                required_years > candidate_years):
            gap = required_years - candidate_years
            penalty += min(24, 8 * gap)
            warnings.append(
                f"Posting asks for {required_years}+ years; profile states {candidate_years}")

        profile_certs = " ".join(
            str(item.get("name") or "") if isinstance(item, dict) else str(item or "")
            for item in profile.get("certifications") or []).lower()
        strict_sentences = [sentence for sentence in re.split(r"[.;\n]+", text)
                            if re.search(r"\b(?:required|must have|at least one|one of the following)\b",
                                         sentence)]
        for sentence in strict_sentences:
            mentioned = [name for name, pattern in _SECURITY_CERTS.items()
                         if re.search(pattern, sentence, re.I)]
            if mentioned and not any(re.search(_SECURITY_CERTS[name], profile_certs, re.I)
                                     for name in mentioned):
                penalty += 18
                warnings.append("Required certification not found in profile: " +
                                " / ".join(name.upper() for name in mentioned))
                break
        return penalty, list(dict.fromkeys(warnings))
    except Exception:
        return 0, []


def standing_instruction_exclusions(instructions: str) -> list:
    """Extract only explicit exclusion lists from standing instructions.

    Args:
        instructions: free-form user instructions. Only lines beginning with
            ``avoid:``, ``exclude:``, ``skip:``, or ``never apply to:`` are
            treated as exclusions; other prose cannot accidentally filter jobs.

    Returns:
        list: normalized exclusion phrases. Never raises.
    """
    try:
        exclusions = []
        pattern = re.compile(r"^\s*(?:avoid|exclude|skip|never\s+apply\s+to)\s*[:\-]\s*(.+)$", re.I)
        for line in str(instructions or "").splitlines():
            match = pattern.match(line)
            if not match:
                continue
            for value in re.split(r",|\s+or\s+", match.group(1), flags=re.I):
                phrase = re.sub(r"\s+", " ", value).strip(" .;:-").lower()
                if phrase and len(phrase) >= 2:
                    exclusions.append(phrase)
        return list(dict.fromkeys(exclusions))
    except Exception:
        return []


def job_matches_standing_instructions(job: dict, instructions: str) -> bool:
    """Return whether a job survives explicit standing-instruction exclusions.

    Args:
        job: normalized HiringCafe job dictionary.
        instructions: user-authored standing instructions.

    Returns:
        bool: false only when an explicit exclusion phrase matches title,
        company, location, or description. Never raises.
    """
    try:
        if not isinstance(job, dict):
            return False
        haystack = " ".join(str(job.get(key) or "") for key in (
            "title", "companyName", "location", "description")).lower()
        terms = standing_instruction_exclusions(instructions)
        variants = [variant for term in terms for variant in (
            term, term[:-1] if term.endswith('s') and len(term) > 3 else term)]
        return not any(term in haystack for term in variants)
    except Exception:
        return True


def rank_hiringcafe_jobs(jobs: list, profile: dict, query: str = "",
                         location: str = "", remote_only: bool = False,
                         preferences: dict | None = None) -> list:
    """Rank normalized HiringCafe jobs against a local profile.

    Args:
        jobs: normalized job dictionaries.
        profile: local candidate profile dictionary.
        query: desired role or keywords.
        location: preferred location text.
        remote_only: exclude jobs not marked remote when true.
        preferences: excludedTitles, minimumSalary, and strictLocation filters.

    Returns:
        list: jobs sorted by matchScore with concise matchReasons. Invalid
        inputs produce an empty list and individual malformed jobs are skipped.
    """
    try:
        prefs = preferences or {}
        personal = profile.get("personalInformation", {}) if isinstance(profile, dict) else {}
        profile_title = str(personal.get("title") or "")
        profile_location = " ".join(
            str(personal.get(key) or "") for key in ("city", "state", "country")
        ).strip()
        skill_phrases = []
        experience_roles = []
        for role in profile.get("workExperience", []) if isinstance(profile, dict) else []:
            if isinstance(role, dict):
                experience_roles.append(str(role.get("role") or "").lower())
        for category in profile.get("skillCategories", []) if isinstance(profile, dict) else []:
            if isinstance(category, dict):
                skill_phrases.extend(str(item).strip().lower()
                                     for item in category.get("skills", []) if item)
        role_tokens = _tokens(query or profile_title)
        preferred_tokens = _tokens(location or profile_location)
        ranked = []
        for item in jobs if isinstance(jobs, list) else []:
            if not isinstance(item, dict):
                continue
            job = dict(item)
            # Re-resolve the ATS when ranking saved jobs. This upgrades older
            # feed rows after a detector improvement (for example ADP's newer
            # myjobs host) without mutating or re-fetching the persisted feed.
            detected_ats = ats_detect_chain(str(job.get("url") or "")).get(
                "ats_id", "unknown")
            if detected_ats != "unknown":
                job["atsType"] = detected_ats
            if remote_only and not bool(job.get("remote")):
                continue
            title = str(job.get("title") or "").lower()
            location_text = str(job.get("location") or "").lower()
            excluded = [term.strip().lower() for term in str(prefs.get('excludedTitles') or '').split(',') if term.strip()]
            if any(term in title for term in excluded):
                continue
            minimum = int(prefs.get('minimumSalary') or 0)
            if minimum and job.get('salaryMax') and float(job['salaryMax']) < minimum:
                continue
            if prefs.get('strictLocation') and location and not job.get('remote'):
                city = location.split(',')[0].strip().lower()
                if city not in location_text:
                    continue
            haystack = " ".join((title, str(job.get("description") or "").lower(),
                                  " ".join(str(v).lower() for v in job.get("skills", []))))
            title_tokens = _tokens(title)
            body_tokens = _tokens(haystack)
            query_title_hits = role_tokens & title_tokens
            query_body_hits = role_tokens & body_tokens
            skill_hits = [skill for skill in skill_phrases if skill and skill in haystack]
            score = min(50, len(query_title_hits) * 15 + len(query_body_hits) * 4)
            reasons = []
            if query_title_hits:
                reasons.append("Role match: " + ", ".join(sorted(query_title_hits)[:4]))
            if skill_hits:
                score += min(30, len(skill_hits) * 4)
                reasons.append(f"{len(skill_hits)} profile skill match" + ("es" if len(skill_hits) != 1 else ""))
            if job.get("remote"):
                score += 12
                reasons.append("Remote")
            elif preferred_tokens and preferred_tokens & _tokens(location_text):
                score += 15
                reasons.append("Preferred location")
            if job.get("atsType") and job.get("atsType") != "unknown":
                score += 5
                reasons.append("Recognized apply system")
            leadership_profile = re.search(
                r"\b(?:manager|director|lead|head|vice president|vp|chief)\b",
                " ".join([profile_title.lower(), *experience_roles]),
            )
            if re.search(r"\b(?:director|vice president|vp|chief)\b", title):
                score -= 18
                reasons.append("Leadership-level stretch")
            elif re.search(r"\b(?:manager|head of)\b", title) and not leadership_profile:
                score -= 14
                reasons.append("Management-level stretch")
            if re.search(r"\b(?:intern|internship|student)\b", title):
                score -= 35 if len(experience_roles) >= 2 else 20
                reasons.append("Early-career level mismatch")
            if (re.search(r"\b(?:adjunct|professor|faculty|instructor)\b", title)
                    and not re.search(r"\b(?:adjunct|professor|faculty|instructor)\b",
                                      profile_title.lower())):
                score -= 30
                reasons.append("Teaching-role mismatch")
            requirement_penalty, requirement_warnings = _requirement_fit(job, profile)
            score -= requirement_penalty
            job["matchScore"] = max(0, min(100, score))
            job["matchReasons"] = reasons[:4] or ["HiringCafe result — review fit"]
            job["matchWarnings"] = requirement_warnings
            if job["matchScore"] >= 75:
                job["matchQuality"] = "excellent"
            elif job["matchScore"] >= 60:
                job["matchQuality"] = "strong"
            elif job["matchScore"] >= 45:
                job["matchQuality"] = "good"
            else:
                job["matchQuality"] = "stretch"
            ranked.append(job)
        ranked.sort(key=lambda row: (row.get("matchScore", 0), row.get("updated_at", "")),
                    reverse=True)
        return ranked
    except Exception:
        return []


def search_hiringcafe(query: str, profile: dict | None = None, limit: int = 50,
                      location: str = "", remote_only: bool = False,
                      page_limit: int = 2, preferences: dict | None = None) -> dict:
    """Search HiringCafe and return normalized, ranked jobs.

    Args:
        query: role or keyword query (1-200 characters).
        profile: local candidate profile used for ranking.
        limit: maximum normalized results returned (1-150).
        location: preferred location used for ranking.
        remote_only: return only jobs marked remote.
        page_limit: HiringCafe result pages to inspect (1-3).
        preferences: savedSearchUrl preserves HiringCafe native filters;
            other preferences are applied before limiting ranked results.

    Returns:
        dict: {ok, count, jobs, error}; errors are caught and returned rather
        than raised. A visible Chromium fallback may briefly appear if
        HiringCafe challenges the headless request.
    """
    query = str(query or "").strip()
    if not query or len(query) > 200:
        return {"ok": False, "count": 0, "jobs": [], "error": "query-must-be-1-to-200-characters"}
    try:
        preferences = preferences or {}
        saved_url = str(preferences.get('savedSearchUrl') or '')
        limit = max(1, min(int(limit), 150))
        page_limit = max(1, min(int(page_limit), 3))
        from playwright.sync_api import sync_playwright

        hits = []
        with sync_playwright() as playwright:
            browser = None
            page = None
            first_payload = None
            try:
                for headless in (True, False):
                    if browser is not None:
                        browser.close()
                    try:
                        browser = playwright.chromium.launch(headless=headless, channel="chrome")
                    except Exception:
                        browser = playwright.chromium.launch(headless=headless)
                    page = browser.new_page()
                    response = page.goto(_search_url(query, 0, saved_url), wait_until="domcontentloaded",
                                         timeout=60000)
                    if response is not None and response.status == 200 \
                            and page.locator("#__NEXT_DATA__").count():
                        first_payload = json.loads(page.locator("#__NEXT_DATA__").text_content())
                        break
                if first_payload is None:
                    return {"ok": False, "count": 0, "jobs": [],
                            "error": "hiringcafe-browser-search-blocked"}
                for page_number in range(page_limit):
                    if page_number:
                        response = page.goto(_search_url(query, page_number, saved_url),
                                             wait_until="domcontentloaded", timeout=60000)
                        if response is None or response.status != 200:
                            break
                        page.wait_for_selector("#__NEXT_DATA__", state="attached", timeout=30000)
                        payload = json.loads(page.locator("#__NEXT_DATA__").text_content())
                    else:
                        payload = first_payload
                    props = payload.get("props", {}).get("pageProps", {})
                    batch = props.get("ssrHits")
                    if not isinstance(batch, list):
                        return {"ok": False, "count": 0, "jobs": [],
                                "error": "hiringcafe-response-missing-results"}
                    hits.extend(batch)
                    if props.get("ssrIsLastPage") is True:
                        break
            finally:
                if browser is not None:
                    browser.close()
        jobs = rank_hiringcafe_jobs(_normalize_hits(hits), profile or {}, query,
                                    location, remote_only, preferences)[:limit]
        return {"ok": True, "count": len(jobs), "jobs": jobs, "error": ""}
    except Exception as exc:
        return {"ok": False, "count": 0, "jobs": [],
                "error": str(exc) or "hiringcafe-search-failed"}
