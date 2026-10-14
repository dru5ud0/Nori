"""tsenta_ats — ATS detection engine (M0).

Python port of the recovered Tsenta Chrome-extension detection engine
(extension/background.js, functions Ue/We/$e/Me/Be, plus the qe status map).

Detection semantics (ported verbatim):
- `ats_detect(url)`: ordered fingerprinting over hostname + path + query + hash,
  first-match-wins, 34 signatures (greenhouse, lever, workday, ashby, workable,
  rippling, bamboohr, breezyhr, jazzhr, jobvite, paylocity, smartrecruiters,
  icims, brassring, oraclecloud, recruitee, pinpoint, teamtailor, polymer,
  dayforce, successfactors, join, hireology, naukri, indeed, avature, phenom,
  ultipro, zohorecruit, adp, paycom, dover, gem, bullhorn).
- `ats_extract_candidates(url)`: extracts candidate URLs from query params and
  decoded/nested URLs (up to 3 decode passes), cracking redirect chains such as
  linkedin safety/go, ATS redirect links and embed URLs.
- `ats_detect_chain(url)`: BFS recursion over candidates, depth 4, returning the
  first detected ATS in the redirect chain (port of Be()).

Every public function returns strings/dicts and catches exceptions internally.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit, urlunsplit

_ATS_ORDER = [
    "greenhouse", "lever", "workday", "ashby", "workable", "rippling",
    "bamboohr", "breezyhr", "jazzhr", "jobvite", "paylocity",
    "smartrecruiters", "icims", "brassring", "oraclecloud", "recruitee",
    "pinpoint", "teamtailor", "polymer", "dayforce", "successfactors", "join",
    "hireology", "naukri", "indeed", "avature", "phenom",
    "ultipro", "zohorecruit", "adp", "paycom", "dover", "gem", "bullhorn",
    "eightfold",
]

# Display-name catalog recovered from the extension's supported-ATS list.
ATS_CATALOG = {
    "greenhouse": {"name": "Greenhouse", "url_patterns": ["greenhouse.io", "boards.greenhouse.io", "gh_jid=", "greenhouse_jid="]},
    "workday": {"name": "Workday", "url_patterns": ["myworkdayjobs.com", "myworkdaysite.com", "workday.com"]},
    "naukri": {"name": "Naukri", "url_patterns": ["naukri.com"]},
    "indeed": {"name": "Indeed", "url_patterns": ["indeed.com"]},
    "lever": {"name": "Lever", "url_patterns": ["lever.co"]},
    "ashby": {"name": "Ashby", "url_patterns": ["ashbyhq.com", "ashby_jid="]},
    "rippling": {"name": "Rippling", "url_patterns": ["rippling-ats.com", "ats.rippling.com"]},
    "icims": {"name": "iCIMS", "url_patterns": ["icims.com", "jibeapply.com"]},
    "brassring": {"name": "BrassRing", "url_patterns": ["brassring.com/tgnewui/search/home/", "jobs.ubs.com/tgnewui/search/home/"]},
    "bamboohr": {"name": "BambooHR", "url_patterns": [".bamboohr.com"]},
    "workable": {"name": "Workable", "url_patterns": ["workable.com"]},
    "jazzhr": {"name": "JazzHR", "url_patterns": [".applytojob.com"]},
    "jobvite": {"name": "Jobvite", "url_patterns": ["jobs.jobvite.com", "jobvite.com"]},
    "breezyhr": {"name": "BreezyHR", "url_patterns": [".breezy.hr"]},
    "oraclecloud": {"name": "Oracle Recruiting", "url_patterns": [".oraclecloud.com", "taleo.net"]},
    "paylocity": {"name": "Paylocity", "url_patterns": [".paylocity.com/recruiting"]},
    "smartrecruiters": {"name": "SmartRecruiters", "url_patterns": ["jobs.smartrecruiters.com"]},
    "ultipro": {"name": "UltiPro / UKG", "url_patterns": ["recruiting2.ultipro.com", "recruiting.ultipro.com", ".ultipro.ca", ".rec.pro.ukg.net"]},
    "zohorecruit": {"name": "Zoho Recruit", "url_patterns": [".zohorecruit."]},
    "adp": {"name": "ADP", "url_patterns": ["workforcenow.adp.com", "myjobs.adp.com"]},
    "paycom": {"name": "Paycom", "url_patterns": ["paycomonline.net/v4/ats"]},
    "dover": {"name": "Dover", "url_patterns": ["app.dover.com/apply/"]},
    "gem": {"name": "Gem", "url_patterns": ["jobs.gem.com"]},
    "successfactors": {"name": "SAP SuccessFactors", "url_patterns": [".successfactors.com", ".successfactors.eu", ".sapsf.com", ".sapsf.eu", ".ns2cloud.com", "jobs.hr.cloud.sap"]},
    "recruitee": {"name": "Recruitee", "url_patterns": [".recruitee.com"]},
    "pinpoint": {"name": "Pinpoint", "url_patterns": [".pinpointhq.com"]},
    "teamtailor": {"name": "Teamtailor", "url_patterns": [".teamtailor.com"]},
    "polymer": {"name": "Polymer", "url_patterns": ["jobs.polymer.co"]},
    "phenom": {"name": "Phenom", "url_patterns": [".phenompeople.com", "careers.phenom.com", "jobseqno="]},
    "dayforce": {"name": "Dayforce", "url_patterns": ["dayforcehcm.com"]},
    "join": {"name": "Join", "url_patterns": ["join.com/companies/"]},
    "hireology": {"name": "Hireology", "url_patterns": ["careers.hireology.com"]},
    "avature": {"name": "Avature", "url_patterns": ["avature.net"]},
    "bullhorn": {"name": "Bullhorn", "url_patterns": ["bullhornstaffing.com"]},
    "eightfold": {"name": "Eightfold.ai", "url_patterns": ["eightfold.ai", "vscdn.net", "/careers/apply?pid=", "/careers/job/"]},
}

# ATSes with browser/extension automation support in the recovered engine.
SUPPORTED_ATS = {
    "greenhouse", "lever", "workday", "naukri", "indeed", "ashby", "icims",
    "brassring", "workable", "rippling", "bamboohr", "breezyhr", "jazzhr",
    "jobvite", "paylocity", "oraclecloud", "smartrecruiters", "recruitee",
    "pinpoint", "teamtailor", "polymer", "phenom", "dayforce",
    "successfactors", "join", "hireology", "paycom",
}

# Runtime-registered signatures (register_ats_signature). Each entry:
# {"ats_id", "name", "url_patterns": [str], "predicate": callable|None}.
# Checked AFTER the 27 built-in fingerprints, so custom rules can never
# shadow recovered detection, but new ATSes can be added without editing
# this module.
_EXTRA_RULES = []

_UNKNOWN = {"ats_id": "unknown", "confidence": 0.0, "rule": "no-match"}

_URL_REGEX = re.compile(r"https?://[^\s\"'<>\\]+", re.IGNORECASE)
_BRASSRING_HASH = re.compile(r"^#jobdetails=\d+", re.IGNORECASE)
_ORACLE_SITES = re.compile(r"/sites/cx(?:_[\w-]+)?/(?:jobs?|requisitions)\b", re.IGNORECASE)
_PHENOM_PATH = re.compile(r"/[a-z]{2}/[a-z]{2}/(?:job/[\w-]+|apply)\b", re.IGNORECASE)

# Recovered status pipeline map (extension `qe`), used by later milestones.
_STATUS_MAP = {
    "OPTIMIZING": "queued", "OPTIMIZING_RESUME": "queued", "OPTIMIZING_CL": "queued",
    "READY": "queued", "PENDING": "queued", "QUEUED": "queued", "CREATED": "queued",
    "PENDING_REVIEW": "review", "PENDING_RESUME_REVIEW": "review",
    "PENDING_CL_REVIEW": "review", "REVIEW_REQUIRED": "review",
    "NEEDS_REVIEW": "review", "AWAITING_REVIEW": "review", "REVIEW": "review",
    "RUNNING": "running", "IN_PROGRESS": "running", "STARTED": "running",
    "COMPLETED": "applied", "APPLIED": "applied", "SUCCESS": "applied",
    "SUBMITTED": "applied", "FAILED": "failed", "ERROR": "failed",
    "CANCELLED": "failed", "SKIPPED": "failed", "PAUSED": "paused",
}


def ats_display_name(ats_id: str) -> str:
    """Return the human-readable ATS name for an ats_id (unknown-safe)."""
    entry = ATS_CATALOG.get(ats_id)
    return entry["name"] if entry else ats_id.capitalize()


def ats_normalize_hint(value: str) -> str:
    """Normalize trusted feed ATS labels to a built-in Nori identifier.

    Args:
        value: ATS label from a normalized, exact-match feed record.

    Returns:
        str: a key present in :data:`ATS_CATALOG`, or ``"unknown"``. This
        helper does not inspect arbitrary page content and never raises.
    """
    try:
        hint = re.sub(r"[^a-z0-9]+", "", str(value or "").lower())
        aliases = {
            "adprecruiting": "adp",
            "icims2": "icims",
            "oracle": "oraclecloud",
            "sap": "successfactors",
            "sapsuccessfactors": "successfactors",
            "ukg": "ultipro",
        }
        normalized = aliases.get(hint, hint)
        return normalized if normalized in ATS_CATALOG else "unknown"
    except Exception:
        return "unknown"


def register_ats_signature(ats_id: str, name: str = "",
                           url_patterns: list | None = None,
                           predicate: callable | None = None) -> bool:
    """Register a custom ATS fingerprint checked after the built-in 27.

    Args:
        ats_id: unique id, e.g. "mycompany-ats" (non-empty string).
        name: display name; defaults to ats_id.
        url_patterns: substrings; a URL containing any of them (on the deeply
            decoded host+path+query, like the built-ins) matches the rule.
        predicate: optional callable(parts) -> bool for custom checks, where
            parts is {"host", "path", "query", "fragment", "decoded"}.
            When given, the rule matches if predicate(parts) is True.

    Returns:
        bool: True when registered, False on invalid input. Never raises.
        Registering an existing ats_id replaces its rule.
    """
    try:
        if not isinstance(ats_id, str) or not ats_id.strip():
            return False
        ats_id = ats_id.strip()
        patterns = [p for p in (url_patterns or []) if isinstance(p, str) and p]
        if not patterns and predicate is None:
            return False
        entry = {"ats_id": ats_id, "name": (name or ats_id).strip() or ats_id,
                 "url_patterns": patterns, "predicate": predicate}
        for index, existing in enumerate(_EXTRA_RULES):
            if existing["ats_id"] == ats_id:
                _EXTRA_RULES[index] = entry
                break
        else:
            _EXTRA_RULES.append(entry)
        ATS_CATALOG.setdefault(ats_id, {"name": entry["name"],
                                        "url_patterns": patterns})
        SUPPORTED_ATS.add(ats_id)
        return True
    except Exception:
        return False


def unregister_ats_signature(ats_id: str) -> bool:
    """Remove a previously registered custom signature.

    Args:
        ats_id: id passed to register_ats_signature().

    Returns:
        bool: True when removed, False when not registered. Never raises.
    """
    for index, existing in enumerate(_EXTRA_RULES):
        if existing["ats_id"] == ats_id:
            del _EXTRA_RULES[index]
            return True
    return False


def registered_ats() -> list:
    """List of ats_ids from runtime-registered signatures (never raises)."""
    return [entry["ats_id"] for entry in _EXTRA_RULES]


def status_normalize(status: str) -> str:
    """Map an upstream application status string to a pipeline bucket.

    Returns one of: queued | review | running | applied | failed | paused
    (defaults to "queued" for unknown/empty input, like the extension Fe()).
    """
    if not status:
        return "queued"
    key = status.upper().replace("-", "_").replace(" ", "_")
    return _STATUS_MAP.get(key, "queued")


def _decode_deep(value: str, passes: int = 3) -> str:
    """Repeatedly percent-decode up to `passes` times until stable (port of Me)."""
    current = value
    for _ in range(passes):
        try:
            from urllib.parse import unquote
            decoded = unquote(current)
        except Exception:
            break
        if decoded == current:
            break
        current = decoded
    return current


def _split(url: str):
    """Lowercased host/path/query/hash components; returns None if malformed."""
    try:
        parts = urlsplit(url)
    except Exception:
        return None
    fragment = ("#" + parts.fragment) if parts.fragment else ""
    return (
        parts.hostname.lower() if parts.hostname else "",
        parts.path.lower() or "",
        parts.query.lower() or "",
        fragment.lower(),
    )


def _detect_components(host: str, path: str, query: str, fragment: str):
    """Ordered fingerprint check (port of Ue). Returns (ats_id, rule, confidence) or None."""
    haystack = host + path + query
    try:
        decoded = _decode_deep(haystack)
    except Exception:
        decoded = haystack
    contains_any = lambda *tokens: any(tok in decoded for tok in tokens)

    # greenhouse
    if (
        "greenhouse" in host
        or query.startswith("gh_jid=") or "gh_jid=" in query
        or query.startswith("gh_src=") or "gh_src=" in query
        or query.startswith("greenhouse_jid=") or "greenhouse_jid=" in query
        or contains_any("boards.greenhouse.io", "job-boards.greenhouse.io", "greenhouse.io",
                        "gh_jid=", "greenhouse_jid=", "/embed/job_app", "/job_app")
    ):
        return "greenhouse", "greenhouse: hostname contains 'greenhouse' or gh_jid/gh_src/greenhouse_jid params or boards.greenhouse.io path", 0.9
    # lever
    if host.endswith("lever.co") or "lever.co/" in decoded:
        return "lever", "lever: host ends .lever.co or URL contains lever.co/", 0.95
    # workday
    if (
        host.endswith("myworkdayjobs.com")
        or host.endswith("myworkdayjobs-impl.com")
        or host.endswith("myworkdaysite.com")
        or contains_any("myworkdayjobs.com", "myworkdayjobs-impl.com", "myworkdaysite.com")
    ):
        return "workday", "workday: host ends .myworkdayjobs.com/.myworkdayjobs-impl.com/.myworkdaysite.com", 0.95
    # ashby
    if host.endswith("ashbyhq.com") or "ashbyhq.com" in decoded:
        return "ashby", "ashby: host ends .ashbyhq.com or URL contains ashbyhq.com", 0.95
    # workable
    if host.endswith("workable.com"):
        return "workable", "workable: host ends .workable.com", 0.95
    # rippling
    if host.endswith("rippling-ats.com") or host == "ats.rippling.com" or host.endswith(".ats.rippling.com"):
        return "rippling", "rippling: host ends .rippling-ats.com or equals/sub of ats.rippling.com", 0.95
    # bamboohr
    if host.endswith(".bamboohr.com"):
        return "bamboohr", "bamboohr: host ends .bamboohr.com", 0.95
    # breezyhr
    if host.endswith(".breezy.hr"):
        return "breezyhr", "breezyhr: host ends .breezy.hr", 0.95
    # jazzhr
    if host.endswith(".applytojob.com"):
        return "jazzhr", "jazzhr: host ends .applytojob.com", 0.95
    # jobvite
    if host == "jobs.jobvite.com" or host.endswith(".jobvite.com"):
        return "jobvite", "jobvite: host is jobs.jobvite.com or ends .jobvite.com", 0.95
    # paylocity
    if "paylocity.com" in host and "/recruiting" in path:
        return "paylocity", "paylocity: host contains paylocity.com and path contains /recruiting", 0.95
    # smartrecruiters
    if host == "jobs.smartrecruiters.com":
        return "smartrecruiters", "smartrecruiters: host is jobs.smartrecruiters.com", 0.95
    # icims
    if (
        host == "icims.com" or host.endswith(".icims.com")
        or host == "jibeapply.com" or host.endswith(".jibeapply.com")
    ):
        return "icims", "icims: host is icims.com/.icims.com or jibeapply.com/.jibeapply.com", 0.95
    # brassring
    if (
        (host == "brassring.com" or host.endswith(".brassring.com") or host == "jobs.ubs.com")
        and "/tgnewui/search/home/" in path
        and ("jobid" in parse_qs(query) or _BRASSRING_HASH.match(fragment))
    ):
        return "brassring", "brassring: brassring/ubs host + /tgnewui/search/home/ path + jobid param or #jobdetails hash", 0.95
    # oraclecloud
    if (
        (host.endswith(".oraclecloud.com") and "candidateexperience" in haystack)
        or "/candidateexperience/" in path
        or _ORACLE_SITES.search(path)
        or host.endswith("taleo.net")
    ):
        return "oraclecloud", "oraclecloud: .oraclecloud.com candidateexperience, /sites/cx_*/jobs path, or .taleo.net host", 0.9
    # recruitee
    if host.endswith(".recruitee.com"):
        return "recruitee", "recruitee: host ends .recruitee.com", 0.95
    # pinpoint
    if host.endswith(".pinpointhq.com"):
        return "pinpoint", "pinpoint: host ends .pinpointhq.com", 0.95
    # teamtailor
    if host.endswith(".teamtailor.com"):
        return "teamtailor", "teamtailor: host ends .teamtailor.com", 0.95
    # polymer
    if host == "jobs.polymer.co":
        return "polymer", "polymer: host is jobs.polymer.co", 0.95
    # dayforce
    if host.endswith("dayforcehcm.com"):
        return "dayforce", "dayforce: host ends dayforcehcm.com", 0.95
    # successfactors
    if (
        host.endswith(".successfactors.com") or host.endswith(".successfactors.eu")
        or host.endswith(".sapsf.com") or host.endswith(".sapsf.eu")
        or host.endswith(".ns2cloud.com")
        or host == "jobs.hr.cloud.sap" or host.endswith(".jobs.hr.cloud.sap")
    ):
        return "successfactors", "successfactors: .successfactors(.eu)/.sapsf(.eu)/.ns2cloud.com/jobs.hr.cloud.sap host", 0.95
    # join (only when path starts /companies/)
    if (host == "join.com" or host == "www.join.com") and path.startswith("/companies/"):
        return "join", "join: host join.com and path starts /companies/", 0.9
    # hireology
    if host == "careers.hireology.com":
        return "hireology", "hireology: host is careers.hireology.com", 0.95
    # naukri
    if host == "naukri.com" or host.endswith(".naukri.com"):
        return "naukri", "naukri: host is naukri.com or ends .naukri.com", 0.95
    # indeed
    if host == "indeed.com" or host.endswith(".indeed.com"):
        return "indeed", "indeed: host is indeed.com or ends .indeed.com", 0.95
    # avature
    if host.endswith(".avature.net"):
        return "avature", "avature: host ends .avature.net", 0.95
    # phenom
    if (
        host.endswith(".phenompeople.com")
        or host == "careers.phenom.com"
        or "jobseqno=" in query
        or _PHENOM_PATH.search(path)
    ):
        return "phenom", "phenom: .phenompeople.com/careers.phenom.com host, jobseqno= param, or /xx/xx/(job/...|apply) path", 0.85
    # ultipro / UKG
    if (
        host == "recruiting2.ultipro.com"
        or host.endswith(".recruiting2.ultipro.com")
        or host == "recruiting.ultipro.com"
        or host.endswith(".recruiting.ultipro.com")
        or host.endswith(".ultipro.ca")
        or host.endswith(".rec.pro.ukg.net")
    ):
        return "ultipro", "ultipro: host ends recruiting2.ultipro.com/recruiting.ultipro.com/.ultipro.ca/.rec.pro.ukg.net", 0.95
    # zoho recruit
    if ".zohorecruit." in host:
        return "zohorecruit", "zohorecruit: host contains .zohorecruit.", 0.95
    # adp
    if host in ("workforcenow.adp.com", "myjobs.adp.com"):
        return "adp", "adp: host is workforcenow.adp.com or myjobs.adp.com", 0.95
    # paycom
    if ((host == "paycomonline.net" or host.endswith(".paycomonline.net"))
            and "/v4/ats/" in path):
        return "paycom", "paycom: paycomonline.net host and /v4/ats/ path", 0.95
    # dover
    if host == "app.dover.com" and path.startswith("/apply/"):
        return "dover", "dover: host is app.dover.com and path starts /apply/", 0.95
    # gem
    if host == "jobs.gem.com":
        return "gem", "gem: host is jobs.gem.com", 0.95
    # bullhorn
    if host.endswith(".bullhornstaffing.com"):
        return "bullhorn", "bullhorn: host ends .bullhornstaffing.com", 0.95
    # eightfold
    if (
        host.endswith("eightfold.ai") or ".eightfold.ai" in host
        or "vscdn.net" in host or "vscdn.net" in decoded
        or "eightfold.ai" in decoded
        or ("/careers/apply" in path and "pid=" in query)
        or ("/careers/job/" in path and re.search(r"/\d+$", path))
    ):
        return "eightfold", "eightfold: eightfold.ai/vscdn.net or /careers/apply?pid= path", 0.95
    # Runtime-registered signatures (never shadow the 27 built-ins above).
    for entry in _EXTRA_RULES:
        try:
            if entry["predicate"] is not None:
                parts = {"host": host, "path": path, "query": query,
                         "fragment": fragment, "decoded": decoded}
                if entry["predicate"](parts):
                    return entry["ats_id"], f"{entry['ats_id']}: registered predicate rule", 0.85
            elif any(p and p in decoded for p in entry["url_patterns"]):
                return entry["ats_id"], f"{entry['ats_id']}: registered URL pattern", 0.85
        except Exception:
            continue
    return None


def ats_detect(url: str) -> dict:
    """Detect the ATS behind a job/apply URL.

    Args:
        url: any http(s) URL (job posting, apply page, embed, redirect link).

    Returns:
        dict: {"ats_id": str, "confidence": float 0..1, "rule": str}
        ats_id is one of the 34 detected ids or "unknown"; confidence 0.0 and
        rule "no-match" when nothing matches. Never raises.
    """
    if not url:
        return dict(_UNKNOWN)
    parts = _split(url)
    if parts is None:
        return dict(_UNKNOWN)
    result = _detect_components(*parts)
    if result is None:
        return dict(_UNKNOWN)
    ats_id, rule, confidence = result
    return {"ats_id": ats_id, "confidence": confidence, "rule": rule}


def _canonical_url(value: str):
    """Validate + canonicalize an http(s) URL string (port of $e)."""
    candidate = value.strip()
    candidate = re.sub(r"[)\],.;]+$", "", candidate)
    if not candidate or not re.match(r"^https?://", candidate, re.IGNORECASE):
        return None
    try:
        parts = urlsplit(candidate)
        return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, parts.fragment))
    except Exception:
        return None


def ats_extract_candidates(url: str) -> list:
    """Extract candidate ATS URLs embedded in a URL (port of We).

    Args:
        url: any URL string.

    Returns:
        list of canonical http(s) URLs found in query-param values (raw and up
        to 3x-decoded), the href itself, and regex-extracted URLs in the raw
        and decoded href/search strings. Empty list when nothing found or the
        input is malformed. Never raises.
    """
    candidates = set()
    try:
        parts = urlsplit(url)
    except Exception:
        return []
    for value in parse_qs(parts.query).values():
        for raw in value:
            decoded = _decode_deep(raw)
            for candidate in (raw, decoded):
                canonical = _canonical_url(candidate)
                if canonical:
                    candidates.add(canonical)
    haystacks = [url, _decode_deep(url), parts.query, _decode_deep(parts.query)]
    for haystack in haystacks:
        if not haystack:
            continue
        for match in _URL_REGEX.findall(haystack):
            canonical = _canonical_url(match)
            if canonical:
                candidates.add(canonical)
    return sorted(candidates)


def ats_detect_chain(url: str, max_depth: int = 4) -> dict:
    """Recursively detect ATS across redirect chains (port of Be, depth 4).

    Args:
        url: starting URL (may be a redirect wrapper such as LinkedIn
            safety/go links).
        max_depth: total number of URLs examined (original + candidates),
            BFS order. The recovered engine uses 4; deeper chains return
            unknown, which is faithful to the JS behavior.

    Returns:
        dict: {"ats_id", "confidence", "rule"} — same shape as ats_detect(),
        where the rule names the URL at which the ATS was found. "unknown" when
        nothing matches within the depth budget. Never raises.
    """
    if not url:
        return dict(_UNKNOWN)
    queue = [url]
    visited = set()
    examined = 0
    while queue and examined < max_depth:
        current = queue.pop(0)
        if not current or current in visited:
            continue
        visited.add(current)
        result = ats_detect(current)
        if result["ats_id"] != "unknown":
            if current != url:
                result["rule"] = f"{result['rule']} (via {current})"
            return result
        for candidate in ats_extract_candidates(current):
            if candidate not in visited:
                queue.append(candidate)
        examined += 1
    return dict(_UNKNOWN)
