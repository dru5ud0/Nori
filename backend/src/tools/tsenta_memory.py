"""
tsenta_memory — Persistent Candidate Answer Memory Engine.

Remembers candidate answers across all 35 ATS platforms so the user never has
to answer or review the same question twice. Answers are stored in
loot/state/answers_memory.json and queried first before any heuristic or LLM fallback.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

_DEFAULT_MEMORY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "loot", "state", "answers_memory.json"
)


def default_memory_path() -> str:
    """Return absolute path to answers_memory.json."""
    return os.environ.get("TSENTA_MEMORY_PATH", os.path.abspath(_DEFAULT_MEMORY_PATH))


def normalize_question(label: str) -> str:
    """Normalize a question label for semantic matching."""
    text = str(label or "").lower()
    # Strip asterisks and common punctuation
    text = re.sub(r"[\*\?\:\!\(\)\[\]\"\'\.\,\;]", " ", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_memory(path: str | None = None) -> dict:
    """Load persistent answers memory."""
    target = path or default_memory_path()
    try:
        if os.path.isfile(target):
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception:
        pass
    return {"answers": {}, "patterns": {}}


def save_memory(memory: dict, path: str | None = None) -> bool:
    """Save memory atomically to disk."""
    target = path or default_memory_path()
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        tmp = target + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2, ensure_ascii=False)
        os.replace(tmp, target)
        return True
    except Exception:
        return False


def seed_default_memory(profile: dict, path: str | None = None) -> dict:
    """Seed memory with candidate's declared profile answers."""
    memory = load_memory(path)
    pi = profile.get("personalInformation") or {}
    wa = profile.get("workAuthorization") or {}
    full_name = f"{pi.get('firstName', '')} {pi.get('lastName', '')}".strip()
    state = str(pi.get("state") or "").strip()
    city = str(pi.get("city") or "").strip()

    # Core high-frequency patterns: Signatures and Referrals
    patterns = memory.setdefault("patterns", {})

    # 1. Signatures
    if full_name:
        patterns["electronic_signature"] = {
            "keywords": [
                "electronic signature", "signature", "please sign", "sign here",
                "type your full name", "typing your full name", "typing your name",
                "type your name", "full name below", "indicate your agreement by typing",
                "type your legal name", "signature:"
            ],
            "value": full_name,
            "kind": "text"
        }

    # 2. Referrals -> Candidate was not referred
    patterns["referral"] = {
        "keywords": ["referred by an", "employee referral", "if referred", "internal referral", "who referred you"],
        "value": "None",
        "kind": "text"
    }

    # 3. How did you hear -> LinkedIn
    source = (profile.get("workPreferences") or {}).get("howDidYouHearAboutRole") or "LinkedIn"
    patterns["source"] = {
        "keywords": ["how did you hear about", "where did you hear about", "how did you find this", "source"],
        "value": source,
        "aliases": ["linkedin", "other", "internet job board", "online"],
        "kind": "select"
    }

    # 4. Work authorization & Sponsorship
    needs_sponsor = wa.get("needsSponsorship", False)
    auth_val = "I require sponsorship now or in the future." if needs_sponsor else "I am legally authorized to work in this country for any employer."
    auth_aliases = ["i require sponsorship"] if needs_sponsor else [
        "i am legally authorized to work in this country for any employer",
        "legally authorized", "no", "authorized to work without sponsorship", "authorized"
    ]
    patterns["visa_sponsorship"] = {
        "keywords": ["require sponsorship", "visa sponsorship", "sponsorship for employment visa"],
        "value": auth_val,
        "aliases": auth_aliases,
        "kind": "select"
    }

    # 5. Alternate legal name
    patterns["alternate_legal_name"] = {
        "keywords": ["different than above", "different from above", "if different than", "other legal name"],
        "value": "None",
        "kind": "text"
    }

    # 6. Hub location / Relocation
    patterns["hub_relocation"] = {
        "keywords": ["hub location", "willing to relocate", "live in one of the following hubs"],
        "value": "I am willing to relocate to this job's location.",
        "aliases": ["willing to relocate", "yes", "i am willing to relocate to this job's location."],
        "kind": "select"
    }

    # 7. Current city, state, country summary
    patterns["current_city_state_country"] = {
        "keywords": ["current city state and country", "indicate your current city", "city state and country"],
        "value": f"{city}, {state}, United States" if (city and state) else (city or state or "United States"),
        "kind": "text"
    }

    # 8. Previous employment / Relative employee
    patterns["previous_employment"] = {
        "keywords": [
            "worked for this company before", "previous worker", "previously employed by this",
            "previously worked at", "previously worked for", "consulted for",
            "prior employment with", "ever worked for", "ever worked at",
            "ever been employed by", "ever been employed at", "ever been employed",
            "contracted to provide services", "contracted to provide services to",
            "currently or have you ever been employed", "former employee",
            "previously employed by", "previously employed at"
        ],
        "value": "No",
        "aliases": ["no", "false", "none", "never", "i have not"],
        "kind": "select"
    }

    patterns["restrictive_covenants"] = {
        "keywords": [
            "subject to any employment agreements", "post-employment restrictions",
            "non-compete", "non-solicitation", "restrictive covenant"
        ],
        "value": "No",
        "aliases": ["no", "false", "none", "not subject"],
        "kind": "select"
    }

    patterns["relative_employee"] = {
        "keywords": ["relative of an employee", "relative of a", "family member employed"],
        "value": "No",
        "aliases": ["no", "false"],
        "kind": "select"
    }

    patterns["over_18"] = {
        "keywords": ["at least 18", "age of 18", "are you 18"],
        "value": "Yes",
        "aliases": ["yes", "true"],
        "kind": "select"
    }

    wp = profile.get("workPreferences") or {}

    # 9. Notice Period
    np_val = wp.get("noticePeriod") or "30 days"
    np_days = wp.get("noticePeriodDays")
    if np_days is None:
        digits = re.findall(r"\d+", str(np_val))
        np_days = int(digits[0]) if digits else (0 if "immediate" in str(np_val).lower() else 30)

    patterns["notice_period"] = {
        "keywords": [
            "notice period", "notice period in days", "availability to join",
            "days required to join", "earliest start date", "how soon can you join",
            "days to join", "period of notice"
        ],
        "value": str(np_val),
        "aliases": [
            str(np_val).lower(), str(np_days), "30 days", "30", "1 month",
            "15 to 30 days", "30 to 45 days", "less than 30 days", "immediate to 30 days"
        ],
        "kind": "text"
    }

    # 10. Serving Notice Period
    serving = bool(wp.get("servingNoticePeriod", False))
    patterns["serving_notice"] = {
        "keywords": ["serving notice period", "currently serving notice", "serving a notice"],
        "value": "Yes" if serving else "No",
        "aliases": ["yes", "true"] if serving else ["no", "false"],
        "kind": "select"
    }

    # 11. Current CTC
    c_ctc = wp.get("currentCTC") or "12 LPA"
    patterns["current_ctc"] = {
        "keywords": ["current ctc", "present ctc", "current fixed ctc", "current compensation", "current salary"],
        "value": str(c_ctc),
        "aliases": [str(c_ctc).lower(), "12 lpa", "12 lakhs", "1200000", "10-15 lpa"],
        "kind": "text"
    }

    # 12. Expected CTC
    e_ctc = wp.get("expectedCTC") or (wp.get("expectedAnnualSalary") or "18 LPA")
    patterns["expected_ctc"] = {
        "keywords": ["expected ctc", "desired ctc", "expected compensation", "expected fixed ctc", "expected salary", "salary expectation"],
        "value": str(e_ctc),
        "aliases": [str(e_ctc).lower(), "18 lpa", "18 lakhs", "1800000", "15-20 lpa"],
        "kind": "text"
    }

    # 13. CTC Negotiable
    patterns["ctc_negotiable"] = {
        "keywords": ["ctc negotiable", "is your ctc negotiable", "negotiable on ctc", "flexibility on ctc"],
        "value": "Yes",
        "aliases": ["yes", "negotiable", "true", "flexible", "open to negotiate"],
        "kind": "select"
    }

    # 14. Preferred Location
    pref_locs = wp.get("preferredLocations") or ["Remote", "Bengaluru", "Bangalore", "Hyderabad", "Pune"]
    top_loc = pref_locs[0] if pref_locs else "Remote"
    patterns["preferred_location"] = {
        "keywords": ["preferred location", "preferred job location", "preferred work location", "preferred office location", "which location do you prefer"],
        "value": top_loc,
        "aliases": [str(l).lower() for l in pref_locs],
        "kind": "select"
    }

    # 14b. Remote Work
    patterns["remote_work"] = {
        "keywords": ["remote work", "work remotely", "open to remote", "remote position", "workplace preference", "work model", "are you looking for remote", "seeking remote", "remote role", "remote-first"],
        "value": "Yes",
        "aliases": ["remote", "yes", "true", "work remotely", "flexible/remote", "fully remote"],
        "kind": "select"
    }

    # 15. India Work Authorization
    patterns["india_work_auth"] = {
        "keywords": ["authorized to work in india", "right to work in india", "eligible to work in india", "work permit in india"],
        "value": "Yes",
        "aliases": ["yes", "true", "authorized", "citizen", "indian citizen"],
        "kind": "select"
    }

    # 16. India Sponsorship
    patterns["india_sponsorship"] = {
        "keywords": ["require sponsorship in india", "visa sponsorship in india", "sponsorship to work in india"],
        "value": "No",
        "aliases": ["no", "false", "not require", "do not require"],
        "kind": "select"
    }

    # 17. Rotational Shifts / Work From Office
    patterns["rotational_shifts"] = {
        "keywords": ["rotational shift", "rotational shifts", "comfortable with shifts", "night shift", "shift timings"],
        "value": "Yes",
        "aliases": ["yes", "true", "comfortable", "agree"],
        "kind": "select"
    }

    patterns["work_from_office"] = {
        "keywords": ["work from office", "willing to work from office", "in-person in bengaluru", "in-person in bangalore", "hybrid model in"],
        "value": "Yes",
        "aliases": ["yes", "true", "agree", "willing"],
        "kind": "select"
    }

    patterns["valid_passport"] = {
        "keywords": ["valid passport", "hold a passport", "do you have a passport"],
        "value": "Yes",
        "aliases": ["yes", "true"],
        "kind": "select"
    }

    patterns["privacy_notice"] = {
        "keywords": ["candidate privacy notice", "privacy notice", "candidate privacy policy", "read rubrik", "accordance with this policy", "privacy notice and understand"],
        "value": "Yes",
        "aliases": ["yes", "true", "i agree", "agree", "accept", "i acknowledge", "consent"],
        "kind": "select"
    }

    # 18. Education Patterns
    edu_list = profile.get("education") or []
    highest_degree = "Master's Degree"
    major = "Cybersecurity"
    grad_year = "2025"
    if edu_list:
        e0 = edu_list[0]
        deg0 = str(e0.get("degree") or "")
        if "master" in deg0.lower() or "m.s." in deg0.lower():
            highest_degree = "Master's Degree"
        elif "bachelor" in deg0.lower() or "b.e." in deg0.lower() or "b.tech" in deg0.lower():
            highest_degree = "Bachelor's Degree"
        major = str(e0.get("major") or major)
        end_date = str(e0.get("endDate") or "")
        digits = re.findall(r"\d{4}", end_date)
        if digits:
            grad_year = digits[0]

    patterns["highest_education"] = {
        "keywords": [
            "highest level of education", "highest education", "highest qualification",
            "education level", "degree completed", "level of education"
        ],
        "value": highest_degree,
        "aliases": [
            highest_degree.lower(), "master's", "post graduate", "masters", "master of science",
            "m.s.", "m.s. cybersecurity", "post-graduation", "graduate degree"
        ],
        "kind": "select"
    }

    patterns["field_of_study"] = {
        "keywords": [
            "field of study", "major", "specialization", "stream", "department of study"
        ],
        "value": major,
        "aliases": [major.lower(), "cybersecurity", "computer science", "information technology"],
        "kind": "text"
    }

    patterns["graduation_year"] = {
        "keywords": [
            "graduation year", "year of graduation", "year of completion", "year of passing"
        ],
        "value": grad_year,
        "aliases": [grad_year, "2025", "2022"],
        "kind": "text"
    }

    # 19. Experience & Employment Status
    exp_list = profile.get("workExperience") or []
    current_company = "PNC Financial Services"
    current_title = "Cybersecurity Analyst"
    if exp_list:
        w0 = exp_list[0]
        current_company = str(w0.get("company") or current_company)
        current_title = str(w0.get("role") or current_title)

    patterns["current_employer"] = {
        "keywords": [
            "current employer", "current company", "present company", "present employer",
            "name of current employer", "current organization"
        ],
        "value": current_company,
        "kind": "text"
    }

    patterns["current_title"] = {
        "keywords": [
            "current title", "current designation", "current role", "present title",
            "present designation"
        ],
        "value": current_title,
        "kind": "text"
    }

    patterns["currently_employed"] = {
        "keywords": [
            "currently employed", "are you employed", "presently working", "currently working"
        ],
        "value": "Yes",
        "aliases": ["yes", "true", "employed"],
        "kind": "select"
    }

    patterns["total_experience"] = {
        "keywords": [
            "years of experience", "years of work experience", "total years",
            "total years of experience", "total experience", "overall experience",
            "years of relevant experience", "total work experience", "relevant experience"
        ],
        "value": "5",
        "aliases": ["5", "5 years", "4-6 years", "4-5 years", "3-5 years", "5+ years"],
        "kind": "text"
    }

    # 20. Legal, Background & Conduct
    patterns["criminal_history"] = {
        "keywords": [
            "convicted of a felony", "convicted of a crime", "criminal record",
            "criminal offense", "criminal conviction", "felony conviction"
        ],
        "value": "No",
        "aliases": ["no", "false", "none", "never"],
        "kind": "select"
    }

    patterns["previously_interviewed"] = {
        "keywords": [
            "interviewed with us in the past", "interviewed by us", "interviewed for this position",
            "applied to this company in the last", "previously interviewed"
        ],
        "value": "No",
        "aliases": ["no", "false", "none", "never"],
        "kind": "select"
    }

    patterns["disciplinary_actions"] = {
        "keywords": [
            "disciplinary action", "terminated from employment", "discharged from employment",
            "asked to resign"
        ],
        "value": "No",
        "aliases": ["no", "false", "none", "never"],
        "kind": "select"
    }

    patterns["lwd_serving_notice"] = {
        "keywords": [
            "last working day", "last working date", "if serving notice what is your",
            "official lwd"
        ],
        "value": "N/A",
        "aliases": ["n/a", "not applicable", "none"],
        "kind": "text"
    }

    save_memory(memory, path)
    return memory


def remember_answer(label: str, value: Any, kind: str = "text",
                    options: list | None = None, path: str | None = None) -> bool:
    """Store a reviewed candidate answer permanently in memory."""
    if not label or value is None:
        return False
    memory = load_memory(path)
    norm = normalize_question(label)

    # Don't save primary identity fields as custom question memory
    compact_lbl = re.sub(r"[^a-z0-9]", "", label.lower())
    is_referral = any(k in compact_lbl for k in ("referred", "referral"))
    if not is_referral and any(k in compact_lbl for k in (
        "firstname", "first_name", "lastname", "last_name", "fullname", "legalname",
        "email", "phone", "mobilenumber", "cellphone", "resume", "cv"
    )):
        return False

    entry = {
        "label": label,
        "value": value,
        "kind": kind,
        "options": [str(o.get("value") if isinstance(o, dict) else o) for o in (options or [])],
        "updatedAt": int(time.time())
    }

    memory.setdefault("answers", {})[norm] = entry
    return save_memory(memory, path)


def remember_all_answers(answers: list[dict], path: str | None = None) -> int:
    """Store all valid, non-fallback answered questions from a trace into persistent memory.

    Args:
        answers: list of answer dicts from trace (with label, value, source, kind, options).
        path: optional path to answers_memory.json.

    Returns:
        int: number of answers saved.
    """
    if not answers or not isinstance(answers, list):
        return 0
    saved_count = 0
    for item in answers:
        if not isinstance(item, dict):
            continue
        source = item.get("source")
        if source in ("skip", "fallback") or not source:
            continue
        value = item.get("value")
        if value is None or value == "":
            continue
        label = item.get("label") or item.get("fieldId") or ""
        if remember_answer(label, value, kind=item.get("kind", "text"),
                           options=item.get("options"), path=path):
            saved_count += 1
    return saved_count


def recall_answer(field: dict, profile: dict, memory_path: str | None = None) -> dict | None:
    """Query memory for a previously stored or profile-seeded answer.
    
    Returns:
        dict of {value, source, display, reason} or None if not found in memory.
    """
    label = str(field.get("label") or "").strip()
    field_id = str(field.get("field_id") or field.get("fieldId") or "").strip()
    kind = str(field.get("kind") or "text").lower()
    options = field.get("options") or []
    norm_label = normalize_question(label)

    # Never let memory override primary contact identity or core profile fields
    compact_id = re.sub(r"[^a-z0-9]", "", field_id.lower())
    compact_lbl = re.sub(r"[^a-z0-9]", "", label.lower())
    is_referral = any(k in compact_lbl for k in ("referred", "referral"))
    if not is_referral and any(k in compact_id or k in compact_lbl for k in (
        "firstname", "first_name", "lastname", "last_name", "fullname", "legalname",
        "email", "phone", "mobilenumber", "cellphone", "resume", "cv", "linkedin", "github"
    )):
        return None

    memory = load_memory(memory_path)
    # Ensure memory is initialized/seeded
    if not memory.get("patterns"):
        memory = seed_default_memory(profile, memory_path)

    # 1. Check exact question match
    answers = memory.get("answers", {})
    if norm_label in answers:
        saved = answers[norm_label]
        val = saved.get("value")
        if options:
            chosen = _match_options(options, val, saved.get("options", []))
            if chosen is not None:
                return {
                    "value": chosen["value"],
                    "source": "user-memory",
                    "display": chosen["label"],
                    "reason": "Recalled from your previous answer"
                }
        else:
            return {
                "value": val,
                "source": "user-memory",
                "display": str(val),
                "reason": "Recalled from your previous answer"
            }

    # 2. Check state residence list question
    state = str((profile.get("personalInformation") or {}).get("state") or "").upper()
    state_names = {
        "IL": ["illinois", " il "],
        "CA": ["california", " ca "],
        "NY": ["new york", " ny "],
        "TX": ["texas", " tx "],
        "FL": ["florida", " fl "]
    }
    if any(q in norm_label for q in ("reside in one of the following states", "located in one of the following states")):
        matched_state = False
        target_names = state_names.get(state, [state.lower()])
        for s_name in target_names:
            if s_name in f" {norm_label} ":
                matched_state = True
                break
        ans = "Yes" if matched_state else "No"
        if options:
            chosen = _match_options(options, ans, [ans.lower()])
            if chosen is not None:
                return {
                    "value": chosen["value"],
                    "source": "user-memory",
                    "display": chosen["label"],
                    "reason": f"Profile indicates residence in {state}"
                }
        return {"value": ans, "source": "user-memory", "display": ans}

    # 3. Check pattern matches
    patterns = memory.get("patterns", {})
    for p_id, p_data in patterns.items():
        keywords = p_data.get("keywords", [])
        if any(kw in norm_label for kw in keywords):
            val = p_data.get("value")
            aliases = p_data.get("aliases", [str(val).lower()])

            # Special case for referral: do not match if it's asking for candidate's own name
            if p_id == "referral":
                if options:
                    chosen = _match_options(options, "No", ["no", "none", "false"])
                    if chosen:
                        return {"value": chosen["value"], "source": "user-memory", "display": chosen["label"]}
                return {"value": "None", "source": "user-memory", "display": "None", "reason": "Candidate was not referred"}

            if options:
                chosen = _match_options(options, val, aliases)
                if chosen is not None:
                    return {
                        "value": chosen["value"],
                        "source": "user-memory",
                        "display": chosen["label"],
                        "reason": f"Recalled standard preference for {p_id}"
                    }
            else:
                return {
                    "value": val,
                    "source": "user-memory",
                    "display": str(val),
                    "reason": f"Recalled standard preference for {p_id}"
                }

    return None


def _match_options(options: list, preferred_val: Any, aliases: list) -> dict | None:
    """Find the matching option for a preferred value or alias list in priority order."""
    clean_aliases = []
    if preferred_val is not None:
        clean_aliases.append(str(preferred_val).lower().strip())
    for a in aliases:
        if a is not None:
            s = str(a).lower().strip()
            if s and s not in clean_aliases:
                clean_aliases.append(s)

    # 1. Exact match pass in priority order
    for alias in clean_aliases:
        for opt in options:
            if isinstance(opt, dict):
                o_val = str(opt.get("value", "")).lower().strip()
                o_lbl = str(opt.get("label", "")).lower().strip()
            else:
                o_val = str(opt).lower().strip()
                o_lbl = o_val
            if alias == o_val or alias == o_lbl:
                return opt if isinstance(opt, dict) else {"value": opt, "label": str(opt)}

    # 2. Semantic substring match pass in priority order
    for alias in clean_aliases:
        if len(alias) < 3:
            continue
        for opt in options:
            if isinstance(opt, dict):
                o_val = str(opt.get("value", "")).lower().strip()
                o_lbl = str(opt.get("label", "")).lower().strip()
            else:
                o_val = str(opt).lower().strip()
                o_lbl = o_val
            if alias in o_val or alias in o_lbl or o_val in alias or o_lbl in alias:
                return opt if isinstance(opt, dict) else {"value": opt, "label": str(opt)}

    return None
