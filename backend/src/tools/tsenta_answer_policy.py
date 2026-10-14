"""Shared safety policy for high-impact application answers.

This module deliberately keeps legal consent and country-scoped work
authorization out of generic LLM/fallback answering.
"""

from __future__ import annotations

import re


_COUNTRY_PATTERNS = (
    ("US", r"\b(?:united states(?: of america)?|u\.s\.a?\.?|usa|american)\b"),
    ("CA", r"\b(?:canada|canadian)\b"),
    ("GB", r"\b(?:united kingdom|u\.k\.?|great britain|england|scotland|wales|british)\b"),
    ("AU", r"\b(?:australia|australian)\b"),
    ("IN", r"\b(?:india|indian|bharat)\b"),
    ("IE", r"\b(?:ireland|irish)\b"),
    ("DE", r"\b(?:germany|german)\b"),
    ("FR", r"\b(?:france|french)\b"),
    ("NL", r"\b(?:netherlands|holland|dutch)\b"),
    ("SG", r"\b(?:singapore|singaporean)\b"),
)

_COUNTRY_NAMES = {
    "US": "US", "USA": "US", "UNITEDSTATES": "US", "UNITEDSTATESOFAMERICA": "US",
    "CA": "CA", "CANADA": "CA", "GB": "GB", "UK": "GB", "UNITEDKINGDOM": "GB",
    "AU": "AU", "AUSTRALIA": "AU", "IN": "IN", "INDIA": "IN",
    "IE": "IE", "IRELAND": "IE", "DE": "DE", "GERMANY": "DE",
    "FR": "FR", "FRANCE": "FR", "NL": "NL", "NETHERLANDS": "NL",
    "SG": "SG", "SINGAPORE": "SG",
}

_COUNTRY_OPTION_LABELS = {
    "US": ("united states of america", "united states", "+1", "united states (+1)", "usa (+1)", "us (+1)"),
    "CA": ("canada", "+1", "canada (+1)"),
    "GB": ("united kingdom", "great britain", "+44", "united kingdom (+44)", "uk (+44)"),
    "AU": ("australia", "+61", "australia (+61)"),
    "IN": ("india", "+91", "india (+91)", "india - 91", "+91 india", "in (+91)", "ind (+91)", "+91 (india)"),
    "IE": ("ireland", "+353", "ireland (+353)"),
    "DE": ("germany", "+49", "germany (+49)"),
    "FR": ("france", "+33", "france (+33)"),
    "NL": ("netherlands", "+31", "netherlands (+31)"),
    "SG": ("singapore", "+65", "singapore (+65)"),
}

US_STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
    "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}

IN_STATE_NAMES = {
    "KA": "Karnataka", "MH": "Maharashtra", "TS": "Telangana", "TG": "Telangana",
    "TN": "Tamil Nadu", "DL": "Delhi", "HR": "Haryana", "UP": "Uttar Pradesh",
    "GJ": "Gujarat", "WB": "West Bengal", "KL": "Kerala", "AP": "Andhra Pradesh",
    "RJ": "Rajasthan", "PB": "Punjab", "MP": "Madhya Pradesh", "OR": "Odisha",
    "OD": "Odisha", "BR": "Bihar", "AS": "Assam", "GA": "Goa", "UT": "Uttarakhand",
    "UK": "Uttarakhand", "JH": "Jharkhand", "CG": "Chhattisgarh", "HP": "Himachal Pradesh",
    "JK": "Jammu and Kashmir", "CH": "Chandigarh", "PY": "Puducherry",
}

_CONSENT_TERMS = (
    "consent", "privacy", "opt-in", "opt in", "marketing", "terms and conditions",
    "terms of use", "certify", "attest", "electronic signature", "background check",
    "authorize the company", "authorize processing", "agree to",
    "acknowledge", "acknowledgement", "acknowledgment",
    "permission to text", "permission to contact", "receive text messages",
    "time-tracking software", "process your personal information",
    "the above statements are true", "material omissions may be cause",
    "false information or material omissions",
)


def _country_code(value: object) -> str:
    compact = re.sub(r"[^A-Z]", "", str(value or "").upper())
    return _COUNTRY_NAMES.get(compact, compact if len(compact) == 2 else "")


def question_country(label: str) -> str:
    """Return an ISO-like country code explicitly named by a question."""
    try:
        text = str(label or "").lower()
        # Ignore skip/exclusion clauses like "(Skip this question if you are applying to work in Canada or the UK)"
        text = re.sub(r"\(skip[^)]*\)", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\bif you are applying (?:to work )?in [^.)]*", "", text, flags=re.IGNORECASE)
        for code, pattern in _COUNTRY_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return code
        # Check Indian tech hubs/states when asked in context of authorization or sponsorship
        if any(w in text for w in ("authorized", "authorization", "sponsor", "sponsorship", "visa", "right to work", "legally", "legal")):
            if re.search(r"\b(?:bengaluru|bangalore|hyderabad|pune|mumbai|gurgaon|gurugram|noida|chennai|delhi|kolkata|karnataka|maharashtra|telangana|tamil nadu)\b", text, re.IGNORECASE):
                return "IN"
    except Exception:
        pass
    return ""


def _as_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "1"):
            return True
        if lowered in ("false", "no", "0"):
            return False
    return None


def declared_eligibility(profile: dict, label: str, key: str) -> bool | None:
    """Read a work-authorization answer only for the question's country.

    An explicit country must match a country-specific authorization record.
    Legacy top-level flags are accepted only when the candidate's profile
    country matches, or when the question does not name a country.
    """
    try:
        profile = profile if isinstance(profile, dict) else {}
        authorization = profile.get("workAuthorization") or {}
        target = question_country(label)
        records = authorization.get("workAuthorizations") or []
        if target and records:
            for record in records:
                if not isinstance(record, dict):
                    continue
                code = _country_code(record.get("countryCode") or record.get("country")
                                     or record.get("countryName"))
                if code == target:
                    return _as_bool(record.get(key))
            return None
        if not target and records:
            if len(records) == 1 and isinstance(records[0], dict):
                value = _as_bool(records[0].get(key))
                if value is not None:
                    return value
            # If all records agree on the authorization value (e.g., candidate is authorized
            # in all declared countries and requires sponsorship in none), return that consensus.
            valid_vals = [_as_bool(r.get(key)) for r in records if isinstance(r, dict) and r.get(key) is not None]
            if valid_vals and all(v == valid_vals[0] for v in valid_vals):
                return valid_vals[0]
        if target:
            home = _country_code((profile.get("personalInformation") or {}).get("country"))
            if home != target:
                return None
        return _as_bool(authorization.get(key))
    except Exception:
        return None


def requires_human_consent(label: str) -> bool:
    """Return True when a field records consent, an attestation, or terms."""
    try:
        text = str(label or "").strip().lower()
        return any(term in text for term in _CONSENT_TERMS)
    except Exception:
        return False


def country_option_aliases(value: object) -> tuple:
    """Return unambiguous option-label aliases for a declared country.

    Args:
        value: Country name or common two/three-letter country code.

    Returns:
        tuple: Lowercase names suitable for matching a native select. Short
        ambiguous fragments such as ``"us"`` are omitted. Never raises.
    """
    try:
        text = str(value or "").strip().lower()
        code = _country_code(value)
        aliases = list(_COUNTRY_OPTION_LABELS.get(code, ()))
        if text and len(text) > 3:
            aliases.append(text)
        return tuple(dict.fromkeys(aliases))
    except Exception:
        return ()


def source_option_aliases(value: object) -> tuple:
    """Return truthful parent categories for a declared application source.

    Args:
        value: Candidate-declared source such as LinkedIn or HiringCafe.

    Returns:
        tuple: Exact source followed by a matching parent category used by
        multi-level ATS controls. Never raises.
    """
    try:
        text = str(value or "").strip().lower()
        if not text:
            return ()
        aliases = [text]
        if any(term in text for term in (
                "linkedin", "indeed", "glassdoor", "ziprecruiter",
                "hiringcafe", "hiring cafe", "naukri", "built in",
                "handshake", "job board")):
            aliases.extend(["job boards", "job board"])
        elif any(term in text for term in (
                "company website", "company site", "careers site", "career site", "career page", "website")):
            aliases.extend(["career site", "company website", "careers site", "website"])
        elif any(term in text for term in (
                "facebook", "instagram", "twitter", "social media")):
            aliases.append("social media")
        elif any(term in text for term in ("university", "college", "campus")):
            aliases.append("through my university")
        return tuple(dict.fromkeys(aliases))
    except Exception:
        return ()


def state_option_aliases(value: object) -> tuple:
    """Return exact state-name aliases for a declared U.S. or Indian state.

    Args:
        value: Two-letter state code or full state name.

    Returns:
        tuple: Full state name first when known, then a non-ambiguous declared
        name. Two-letter fragments are never used for substring matching.
        Never raises.
    """
    try:
        text = str(value or "").strip()
        upper = text.upper()
        aliases = []
        canonical_us = US_STATE_NAMES.get(upper, "")
        if canonical_us:
            aliases.append(canonical_us.lower())
        canonical_in = IN_STATE_NAMES.get(upper, "")
        if canonical_in:
            aliases.append(canonical_in.lower())
        lower_text = text.lower()
        for code, name in list(US_STATE_NAMES.items()) + list(IN_STATE_NAMES.items()):
            if name.lower() == lower_text:
                aliases.append(name.lower())
                aliases.append(code.lower())
        if len(text) == 2:
            aliases.append(text.lower())
        if len(text) > 2:
            aliases.append(text.lower())
        return tuple(dict.fromkeys(item for item in aliases if item))
    except Exception:
        return ()
