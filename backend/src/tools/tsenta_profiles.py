"""tsenta_profiles — candidate profile model (M1).

Python port of the recovered Tsenta universal candidate model
(internal_api_map.md §3 "Profile (universal candidate model)" and the
application_detail_jefferies.json optimizedProfile leaf shapes).

Schema sections (all optional, matching the recovered API):
projects[], education[], resumeStyles{fitToOnePage}, certifications[],
customSections[], hiddenSections[], workExperience[], backgroundCheck{},
skillCategories[], workPreferences{}, hiddenHeaderLinks[], workAuthorization{},
personalInformation{}, diversityEquityInclusion{}, relevantCoursework{courses[]},
resumeFormat, hasDocx, bulletPreservation{}.

Public functions return strings or dicts and catch exceptions internally.
"""

from __future__ import annotations

import json
import re

# EEO-safe default answers (recovered trace semantics: decline veteran/disability,
# no sponsorship, authorized to work, no disclosure of gender/ethnicity).
EEO_SAFE_DEFAULTS = {
    "diversityEquityInclusion": {
        "gender": "",
        "ethnicity": "",
        "isVeteran": False,
        "hasDisability": False,
        "isTransgender": False,
        "sexualOrientation": "",
    },
    "workAuthorization": {
        "visaType": None,
        "optStatus": None,
        "needsSponsorship": False,
        "isAuthorizedToWork": True,
        "workAuthorizations": [
            {
                "visaType": None,
                "optStatus": None,
                "visaStatus": None,
                "countryCode": "US",
                "needsSponsorship": False,
                "authorizationBasis": "citizen",
                "isAuthorizedToWork": True,
            }
        ],
        "citizenshipCountries": ["US"],
    },
}

# Server-side profile completeness gate (recovered contract: applications POST
# 400s with missingFields[{field,label,section}] until these are complete).
REQUIRED_FIELDS = [
    {"field": "firstName", "label": "First Name", "section": "personalInformation"},
    {"field": "lastName", "label": "Last Name", "section": "personalInformation"},
    {"field": "email", "label": "Email", "section": "personalInformation"},
    {"field": "phone", "label": "Phone", "section": "personalInformation"},
    {"field": "address", "label": "Address", "section": "personalInformation"},
    {"field": "city", "label": "City", "section": "personalInformation"},
    {"field": "state", "label": "State", "section": "personalInformation"},
    {"field": "zipCode", "label": "Zip Code", "section": "personalInformation"},
    {"field": "country", "label": "Country", "section": "personalInformation"},
    {"field": "isAuthorizedToWork", "label": "Authorized to Work", "section": "workAuthorization"},
    {"field": "needsSponsorship", "label": "Needs Sponsorship", "section": "workAuthorization"},
    {"field": "resumeFormat", "label": "Resume Format", "section": "resume"},
]

_EMPTY_PROFILE = {
    "projects": [],
    "education": [],
    "resumeStyles": {"fitToOnePage": True},
    "certifications": [],
    "customSections": [],
    "hiddenSections": [],
    "workExperience": [],
    "backgroundCheck": {
        "hasGovernmentTies": None,
        "hasGovernmentClearance": None,
        "hasWorkedForCompanyBefore": None,
    },
    "skillCategories": [],
    "workPreferences": {
        "canRelocate": None,
        "canWorkInPerson": None,
        "hasAccommodations": None,
        "hasTransportation": None,
        "canStartImmediately": None,
        "expectedAnnualSalary": None,
        "expectedHourlySalary": None,
        "howDidYouHearAboutRole": None,
        "referrerName": None,
        "availableStartDate": None,
        "noticePeriod": None,
        "noticePeriodDays": None,
        "servingNoticePeriod": None,
        "currentCTC": None,
        "expectedCTC": None,
        "currency": None,
        "preferredLocations": [],
        "isNegotiableCTC": None,
        "autoAcceptDisclosures": None,
        "autoAcceptTerms": None,
    },
    "hiddenHeaderLinks": [],
    "workAuthorization": {
        "visaType": None,
        "optStatus": None,
        "needsSponsorship": None,
        "isAuthorizedToWork": None,
        "workAuthorizations": [],
        "citizenshipCountries": [],
    },
    "personalInformation": {
        "city": "",
        "email": "",
        "phone": "",
        "state": "",
        "title": "",
        "address": "",
        "county": "",
        "country": "",
        "website": "",
        "summary": "",
        "zipCode": "",
        "isOver18": None,
        "lastName": "",
        "firstName": "",
        "githubUrl": "",
        "dateOfBirth": "",
        "linkedinUrl": "",
    },
    "diversityEquityInclusion": {
        "gender": "",
        "ethnicity": "",
        "isVeteran": None,
        "hasDisability": None,
        "isTransgender": None,
        "sexualOrientation": "",
    },
    "relevantCoursework": {"courses": []},
    "resumeFormat": "",
    "coverLetterText": "",
    "hasDocx": False,
    "bulletPreservation": {},
}

# Dot-path -> section map used to normalize arbitrary payloads into the schema.
_SECTION_KEYS = {
    "projects", "education", "resumeStyles", "certifications", "customSections",
    "hiddenSections", "workExperience", "backgroundCheck", "skillCategories",
    "workPreferences", "hiddenHeaderLinks", "workAuthorization",
    "personalInformation", "diversityEquityInclusion", "relevantCoursework",
    "resumeFormat", "coverLetterText", "hasDocx", "bulletPreservation",
}


def empty_profile() -> dict:
    """Return a fresh profile dict with every recovered schema section.

    Returns:
        dict matching the Tsenta universal candidate model; all sections
        present, values empty/None. Never raises.
    """
    return json.loads(json.dumps(_EMPTY_PROFILE))


def profile_from_json(text: str) -> dict:
    """Parse a JSON profile string into a schema-complete dict.

    Args:
        text: JSON string (the recovered API profile payload, or any
            superset/subset of it).

    Returns:
        dict: parsed profile merged over the empty schema (unknown sections
        dropped, missing sections defaulted). Malformed input yields the empty
        profile. Never raises.
    """
    profile = empty_profile()
    if not text:
        return profile
    try:
        data = json.loads(text)
    except Exception:
        return profile
    if not isinstance(data, dict):
        return profile
    for key, value in data.items():
        if key in _SECTION_KEYS:
            profile[key] = value
    return profile


def profile_to_json(profile: dict) -> str:
    """Serialize a profile dict to compact JSON (recovered API style).

    Args:
        profile: profile dict (any section subset is fine).

    Returns:
        str: compact JSON of the input profile; "{}" on failure. Never raises.
    """
    if not isinstance(profile, dict):
        return "{}"
    try:
        return json.dumps(profile, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return "{}"


def _section(profile: dict, section: str) -> dict:
    value = profile.get(section) if isinstance(profile, dict) else None
    return value if isinstance(value, dict) else {}


def profile_get(profile: dict, dotted_path: str) -> str:
    """Look up a value in the profile via a dotted path (for the answerer).

    Args:
        profile: profile dict.
        dotted_path: e.g. "personalInformation.firstName" or
            "workAuthorization.citizenshipCountries.0".

    Returns:
        str: string form of the value ("" when missing/empty/None — the
        answerer's "no data" signal). Arrays are joined with ", ". Never
        raises.
    """
    current = profile if isinstance(profile, dict) else None
    for part in dotted_path.split("."):
        if current is None:
            return ""
        if part.isdigit() and isinstance(current, list):
            index = int(part)
            current = current[index] if index < len(current) else None
            continue
        if isinstance(current, dict):
            current = current.get(part)
            continue
        current = None
    if current is None:
        return ""
    if isinstance(current, bool):
        return "true" if current else "false"
    if isinstance(current, (list, tuple)):
        return ", ".join(str(item) for item in current if item is not None)
    return str(current)


def validate_profile(profile: dict) -> dict:
    """Check profile completeness against the recovered server-side gate.

    Args:
        profile: profile dict.

    Returns:
        dict: {"valid": bool, "missing": [{"field","label","section"}, ...]}
        mirroring the recovered `missingFields` contract. Never raises.
    """
    missing = []
    if not isinstance(profile, dict):
        return {"valid": False, "missing": [dict(f) for f in REQUIRED_FIELDS]}
    for entry in REQUIRED_FIELDS:
        section = entry.get("section", "")
        path = f"{section}.{entry['field']}" if section and section != "resume" else entry["field"]
        if not profile_get(profile, path):
            missing.append(dict(entry))
    return {"valid": not missing, "missing": missing}


def profile_has_resume(profile: dict) -> bool:
    """Whether the profile carries a resume (resumeFormat present, e.g. PDF).

    Args:
        profile: profile dict.

    Returns:
        bool: True when resumeFormat is a non-empty string like "pdf".
        Never raises.
    """
    return bool(profile_get(profile, "resumeFormat"))


def work_authorization_summary(profile: dict) -> str:
    """Human summary of the candidate's work authorization (for LLM prompts).

    Args:
        profile: profile dict.

    Returns:
        str: e.g. "authorized:true needsSponsorship:false countries:US" or
        "unknown" when the profile has no authorization data. Never raises.
    """
    auth = _section(profile, "workAuthorization")
    if not auth:
        return "unknown"
    authorized = profile_get(profile, "workAuthorization.isAuthorizedToWork")
    sponsorship = profile_get(profile, "workAuthorization.needsSponsorship")
    countries = profile_get(profile, "workAuthorization.citizenshipCountries")
    if not authorized and not sponsorship and not countries:
        return "unknown"
    return (
        "authorized:" + (authorized or "unknown")
        + " needsSponsorship:" + (sponsorship or "unknown")
        + " countries:" + (countries or "unknown")
    )


def skills_flat(profile: dict) -> str:
    """Flatten all skills across skillCategories into one comma string.

    Args:
        profile: profile dict.

    Returns:
        str: comma-separated skill names ("" when none). Never raises.
    """
    skills = []
    categories = profile.get("skillCategories") if isinstance(profile, dict) else None
    if isinstance(categories, list):
        for category in categories:
            if isinstance(category, dict) and isinstance(category.get("skills"), list):
                skills.extend(str(skill) for skill in category["skills"] if skill)
    return ", ".join(skills)


def experience_bullets(profile: dict, limit: int = 50) -> str:
    """Flatten work-experience bullets (role: company — bullets) for LLM use.

    Args:
        profile: profile dict.
        limit: maximum number of bullets to include (protects context size).

    Returns:
        str: "Role at Company (dates): bullet1 | bullet2" lines, "" when none.
        Never raises.
    """
    lines = []
    count = 0
    entries = profile.get("workExperience") if isinstance(profile, dict) else None
    if not isinstance(entries, list):
        return ""
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role") or ""
        company = entry.get("company") or ""
        start = entry.get("startDate") or ""
        end = entry.get("endDate") or ""
        header = f"{role} at {company}".strip(" at")
        if start or end:
            header += f" ({start} - {end})"
        bullets = entry.get("responsibilities") or []
        if isinstance(bullets, list):
            picked = bullets[: limit - count]
            count += len(picked)
            lines.append(header + ": " + " | ".join(str(b) for b in picked))
        if count >= limit:
            break
    return "\n".join(lines)


def _extract_month(value) -> str:
    raw = str(value or "").strip()
    if not raw or raw.lower() in ("present", "current"):
        return ""
    m = re.search(r"(?:19|20)\d{2}-(\d{1,2})", raw)
    if m:
        month_num = int(m.group(1))
        names = ["January", "February", "March", "April", "May", "June",
                 "July", "August", "September", "October", "November", "December"]
        if 1 <= month_num <= 12:
            return names[month_num - 1]
    m2 = re.search(r"(?i)\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b", raw)
    if m2:
        prefix = m2.group(1)[:3].lower()
        mapping = {
            "jan": "January", "feb": "February", "mar": "March", "apr": "April",
            "may": "May", "jun": "June", "jul": "July", "aug": "August",
            "sep": "September", "oct": "October", "nov": "November", "dec": "December"
        }
        return mapping.get(prefix, "")
    return ""


def _extract_year(value) -> str:
    raw = str(value or "").strip()
    m = re.search(r"\b((?:19|20)\d{2})\b", raw)
    return m.group(1) if m else ""


def profile_history_value(profile: dict, field_id: str, label: str) -> str:
    """Resolve an indexed employment, education, or certification field.

    Avature, Dayforce, Workday, and Greenhouse forms encode repeatable
    résumé sections with IDs such as ``172-1-0`` (first employer),
    ``company-name-0``, ``school--0``, ``790-3-0`` (first university), and
    ``4522-5-0`` (first certification name). This function maps those fields
    to the matching profile item without asking an LLM to infer résumé facts.

    Args:
        profile: Candidate profile dictionary.
        field_id: ATS field ID.
        label: Human-readable field label.

    Returns:
        str: Exact profile value, ``Yes``/``No`` for declared booleans, or an
        empty string when the field is not recognized or data is unavailable.
        Never raises.
    """
    try:
        if not isinstance(profile, dict):
            return ""
        fid = str(field_id or "").strip().lower()
        text = str(label or "").strip().lower()

        if "have any certifications" in text:
            certifications = profile.get("certifications")
            if isinstance(certifications, list):
                return "Yes" if any(isinstance(item, dict) and item.get("name")
                                    for item in certifications) else "No"
            return ""

        dayforce_education = ("education-history-" in fid
                              or "educationhistory_" in fid)
        dayforce_work = ("work-history-" in fid or "workhistory_" in fid)
        greenhouse_work = any(k in fid for k in ("company-name", "title-", "start-date", "end-date", "employment", "current-role")) or ("company" in text and "name" in text)
        greenhouse_edu = any(k in fid for k in ("school-", "discipline-", "degree-", "education")) or ("school" in text)
        match = re.search(r"-+(\d+)$", fid)
        if "sample" in fid:
            return ""
        if match:
            index = int(match.group(1))
        elif dayforce_education or dayforce_work or greenhouse_work or greenhouse_edu:
            index = 0
        else:
            return ""

        if fid.startswith("172-") or dayforce_work or greenhouse_work:
            entries = profile.get("workExperience") or []
            if not isinstance(entries, list) or index >= len(entries):
                return ""
            entry = entries[index] if isinstance(entries[index], dict) else {}
            if "company" in text or "employer" in text or "company-name" in fid:
                return str(entry.get("company") or "")
            if "position title" in text or text.rstrip(" *") == "title" or "title" in fid:
                return str(entry.get("role") or entry.get("title") or "")
            if "current position" in text or "current job" in text or "current role" in text or "current" in fid:
                end = str(entry.get("endDate") or "").strip().lower()
                current = bool(entry.get("isCurrent") or entry.get("isCurrentRole")
                               or not end
                               or end in ("present", "current"))
                return "Yes" if current else "No"
            if "start date" in text or "start-date" in fid:
                value = entry.get("startDate")
                if "month" in text or "month" in fid:
                    return _extract_month(value)
                if "year" in text or "year" in fid:
                    return _extract_year(value)
                return (_history_date_value(value) if dayforce_work
                        else str(value or ""))
            if "end date" in text or "end-date" in fid:
                end = str(entry.get("endDate") or "")
                if not end:
                    return ""
                if end.strip().lower() in ("present", "current"):
                    if "month" in text or "month" in fid:
                        return "September"
                    if "year" in text or "year" in fid:
                        return "2026"
                    return ""
                if "month" in text or "month" in fid:
                    return _extract_month(end)
                if "year" in text or "year" in fid:
                    return _extract_year(end)
                return (_history_date_value(end) if dayforce_work else end)
            if "responsibil" in text or "duties" in text:
                value = (entry.get("responsibilities") or entry.get("bullets")
                         or entry.get("summary") or "")
                return "\n".join(str(item) for item in value) if isinstance(value, list) else str(value)
            if text.rstrip(" ?*") == "city":
                return _history_location_part(entry.get("location"), "city")
            if "state" in text or "province" in text:
                return _history_location_part(entry.get("location"), "state")

        if fid.startswith("790-") or dayforce_education or greenhouse_edu:
            entries = profile.get("education") or []
            if not isinstance(entries, list) or index >= len(entries):
                return ""
            entry = entries[index] if isinstance(entries[index], dict) else {}
            if "type of degree" in text or text.rstrip(" *") == "degree" or "degree" in fid:
                return str(entry.get("degree") or "")
            if "field of study" in text or "major" in text or "discipline" in text or "discipline" in fid:
                return str(entry.get("major") or entry.get("fieldOfStudy") or "")
            if "minor" in text:
                return str(entry.get("minor") or "")
            if "university" in text or "school" in text or "school" in fid:
                return str(entry.get("university") or entry.get("school")
                           or entry.get("institution") or "")
            if "start date" in text:
                value = entry.get("startDate")
                if "month" in text or "month" in fid:
                    return _extract_month(value)
                if "year" in text or "year" in fid:
                    return _extract_year(value)
                return (_history_date_value(value) if dayforce_education
                        else str(value or ""))
            if "end date" in text or "year received" in text or "graduation year" in text or "end-date" in fid:
                value = str(entry.get("endDate") or "")
                if "year" in text or "year" in fid or "year received" in text or "graduation year" in text:
                    return _extract_year(value)
                if "month" in text or "month" in fid:
                    return _extract_month(value)
                return (_history_date_value(value) if dayforce_education else value)
            if text.rstrip(" ?*") == "city":
                return _history_location_part(entry.get("location"), "city")
            if "state" in text or "province" in text:
                return _history_location_part(entry.get("location"), "state")
            if "g.p.a" in text or text.rstrip(" *") == "gpa":
                return str(entry.get("gpa") or "")

        if fid.startswith("4522-"):
            entries = profile.get("certifications") or []
            if not isinstance(entries, list) or index >= len(entries):
                return ""
            entry = entries[index] if isinstance(entries[index], dict) else {}
            if "name of certification" in text or text.rstrip(" *") == "certification":
                return str(entry.get("name") or "")
            if "certification number" in text or "credential id" in text:
                return str(entry.get("credentialId") or "")
            if "effective date" in text or "issue date" in text:
                return str(entry.get("issueDate") or "")
            if "expiration date" in text:
                return str(entry.get("expirationDate") or "")
        return ""
    except Exception:
        return ""


def _history_date_value(value) -> str:
    """Normalize a declared month-level résumé date for an HTML date field."""
    raw = str(value or "").strip()
    if not raw or raw.lower() in ("present", "current"):
        return ""
    iso_month = re.fullmatch(r"((?:19|20)\d{2})-(\d{1,2})", raw)
    if iso_month:
        return f"{iso_month.group(1)}-{int(iso_month.group(2)):02d}-01"
    named = re.fullmatch(
        r"(?i)(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
        r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|"
        r"nov(?:ember)?|dec(?:ember)?)\s+((?:19|20)\d{2})", raw)
    if named:
        months = {name: index for index, name in enumerate(
            ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug",
             "sep", "oct", "nov", "dec"), 1)}
        return f"{named.group(2)}-{months[named.group(1)[:3].lower()]:02d}-01"
    return raw


def _history_location_part(value, part: str) -> str:
    """Return the declared city or state/province from a résumé location."""
    pieces = [item.strip() for item in str(value or "").split(",") if item.strip()]
    if part == "city":
        return pieces[0] if len(pieces) >= 2 else ""
    if part == "state":
        return pieces[1] if len(pieces) >= 2 else ""
    return ""


def profile_date_part(value: str, label: str) -> str:
    """Return the requested day/month/year component of a declared date.

    Args:
        value: Profile date in ISO, U.S. numeric, or month-name format.
        label: ATS field label containing Day, Month, or Year.

    Returns:
        str: Day number, English month name, or four-digit year. Returns the
        original value when no component is requested and ``""`` when parsing
        fails. Never raises.
    """
    try:
        raw = str(value or "").strip()
        target = str(label or "").lower()
        if not raw:
            return ""
        months = {
            "jan": (1, "January"), "feb": (2, "February"),
            "mar": (3, "March"), "apr": (4, "April"),
            "may": (5, "May"), "jun": (6, "June"),
            "jul": (7, "July"), "aug": (8, "August"),
            "sep": (9, "September"), "oct": (10, "October"),
            "nov": (11, "November"), "dec": (12, "December"),
        }
        year = month = day = ""
        iso = re.search(r"\b((?:19|20)\d{2})[-/](\d{1,2})(?:[-/](\d{1,2}))?\b", raw)
        us = re.search(r"\b(\d{1,2})/(\d{1,2})/((?:19|20)\d{2})\b", raw)
        named = re.search(
            r"(?i)\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
            r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|"
            r"nov(?:ember)?|dec(?:ember)?)\s+(?:(\d{1,2}),?\s+)?((?:19|20)\d{2})\b",
            raw)
        if iso:
            year, month, day = iso.group(1), str(int(iso.group(2))), (
                str(int(iso.group(3))) if iso.group(3) else "")
        elif us:
            month, day, year = str(int(us.group(1))), str(int(us.group(2))), us.group(3)
        elif named:
            month = str(months[named.group(1)[:3].lower()][0])
            day = str(int(named.group(2))) if named.group(2) else ""
            year = named.group(3)
        else:
            return ""
        if re.search(r"\bday\b", target):
            return day
        if re.search(r"\bmonth\b", target):
            return next((name for number, name in months.values()
                         if number == int(month)), "")
        if re.search(r"\byear\b", target):
            return year
        return raw
    except Exception:
        return ""


def safe_eeo_profile(profile: dict) -> dict:
    """Return the profile with EEO fields replaced by safe defaults.

    Applies the recovered EEO-safe semantics (decline veteran/disability,
    no sponsorship, authorized to work, blank gender/ethnicity) for the
    diversityEquityInclusion + workAuthorization sections.

    Args:
        profile: profile dict.

    Returns:
        dict: copy of the profile with EEO sections set to EEO_SAFE_DEFAULTS.
        Never raises.
    """
    merged = profile_from_json(profile_to_json(profile if isinstance(profile, dict) else {}))
    merged["diversityEquityInclusion"] = json.loads(json.dumps(EEO_SAFE_DEFAULTS["diversityEquityInclusion"]))
    merged["workAuthorization"] = json.loads(json.dumps(EEO_SAFE_DEFAULTS["workAuthorization"]))
    return merged
