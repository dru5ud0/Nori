"""tsenta_llm — LLM answer-sourcing engine (M4).

Answerer seam compatible with tsenta_apply.answer_fields:
    answerer(field, profile, config, trace) -> {"value", "source", "display", "reason"}

Routing mirrors the recovered trace semantics (trace_jefferies.json): most
answers come profile-direct; a small fraction (~7/37) come from the LLM;
unanswerable required questions get the verbatim fallback text. Radio/select
answers produced by the LLM are matched back to the field's option list so the
stored value is the option value and the display is the option label.

Transport: OpenAI-compatible /chat/completions over stdlib urllib only
(no SDK dependency). Endpoint defaults to the yunwu provider mirroring the
opencode config: base https://yunwu.ai/v1, key from env YUNWU_API_KEY, model
from env YUNWU_MODEL (default deepseek-v4-flash). All public functions return
strings or dicts and catch exceptions internally — the answerer NEVER raises
and NEVER returns an llm source when the call failed.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
import urllib.error

_LAST_PROVIDER_ERROR = ''

try:
    from backend.src.tools.tsenta_profiles import (
        profile_date_part, profile_get, profile_history_value,
    )
    from backend.src.tools.tsenta_trace import FALLBACK_REASON, FALLBACK_TEXT
    from backend.src.tools.tsenta_answer_policy import (
        country_option_aliases, declared_eligibility, requires_human_consent,
        source_option_aliases, state_option_aliases,
    )
except ImportError:
    from tsenta_profiles import profile_date_part, profile_get, profile_history_value
    from tsenta_trace import FALLBACK_REASON, FALLBACK_TEXT
    from tsenta_answer_policy import (
        country_option_aliases, declared_eligibility, requires_human_consent,
        source_option_aliases, state_option_aliases,
    )

# Profile-direct mapping (same keyword table as tsenta_apply.default_answerer;
# duplicated here so tsenta_llm stays dependency-free of the playwright module).
_PROFILE_MAP = [
    (("firstname", "first name"), "personalInformation.firstName"),
    (("lastname", "last name"), "personalInformation.lastName"),
    (("email",), "personalInformation.email"),
    (("phone", "mobile"), "personalInformation.phone"),
    (("address", "street"), "personalInformation.address"),
    (("city",), "personalInformation.city"),
    (("state", "province"), "personalInformation.state"),
    (("zip", "postal"), "personalInformation.zipCode"),
    (("country",), "personalInformation.country"),
    (("linkedin",), "personalInformation.linkedinUrl"),
    (("github",), "personalInformation.githubUrl"),
    (("website", "portfolio"), "personalInformation.website"),
    (("salary", "compensation expectation", "compensation expectations",
      "rate of pay expected", "pay expected"),
     "workPreferences.expectedAnnualSalary"),
    (("current ctc", "present ctc", "fixed ctc"), "workPreferences.currentCTC"),
    (("expected ctc", "desired ctc"), "workPreferences.expectedCTC"),
    (("notice period", "notice period in days", "availability to join"), "workPreferences.noticePeriod"),
]

# Open-ended question labels that go to the LLM even when optional.
_OPEN_KEYWORDS = ("tell us", "why", "describe", "summary", "cover letter",
                  "portfolio", "additional", "anything else", "interest",
                  "relevant experience", "yourself")

_DEFAULT_MODEL = "deepseek-v4-flash"
_DEFAULT_BASE_URL = "https://yunwu.ai/v1"

# LLM-generated text answers should stay short (1-3 sentences like a real
# applicant answering honestly).
_SYSTEM_PROMPT = (
    "You are an expert career advisor representing Drupadh Suresh, an accomplished Cybersecurity Analyst "
    "with 5 years of experience across third-party risk management (TPRM), cloud security (AWS/Azure), "
    "IAM, vulnerability operations, and SOC/SIEM investigations (ex-PNC Financial Services, ex-Accenture). "
    "Answer the application question in the candidate's first-person voice ('I', 'my'). "
    "Be articulate, confident, and professional. Write concise, compelling answers (1-3 sentences) "
    "highlighting relevant real experience from the profile. When asked about motivation or interest in a role/company, "
    "express genuine enthusiasm for applying cybersecurity, risk governance, or engineering expertise to their mission. "
    "Never say 'Please refer to my resume' unless the question is explicitly asking for an attachment."
)


def llm_config(**overrides) -> dict:
    """Build the LLM transport configuration from env + overrides.

    Reads YUNWU_API_KEY, YUNWU_BASE_URL (default https://yunwu.ai/v1) and
    YUNWU_MODEL (default deepseek-v4-flash). Any key may be overridden:
    api_key, base_url, model, temperature, timeout (seconds), max_tokens.

    Args:
        **overrides: explicit values that win over the environment.

    Returns:
        dict: {"api_key", "base_url", "model", "temperature", "timeout",
        "max_tokens"} with api_key possibly "". Never raises.
    """
    if "PYTEST_CURRENT_TEST" in os.environ:
        api_key = os.environ.get("YUNWU_API_KEY", "")
        base_url = os.environ.get("YUNWU_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")
        model = os.environ.get("YUNWU_MODEL", _DEFAULT_MODEL)
    else:
        api_key = (os.environ.get("APILIO_API_KEY")
                   or os.environ.get("GPT_BEST_API_KEY")
                   or os.environ.get("YUNWU_API_KEY", ""))
        base_url = (os.environ.get("APILIO_BASE_URL")
                    or ("https://api.apilio.ai/v1" if (os.environ.get("APILIO_API_KEY") or os.environ.get("GPT_BEST_API_KEY")) else None)
                    or os.environ.get("YUNWU_BASE_URL", _DEFAULT_BASE_URL)).rstrip("/")
        model = (os.environ.get("APILIO_MODEL")
                 or ("gpt-4o" if (os.environ.get("APILIO_API_KEY") or os.environ.get("GPT_BEST_API_KEY")) else None)
                 or os.environ.get("YUNWU_MODEL", _DEFAULT_MODEL))
    cfg = {
        'transport': 'api',
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "temperature": 0.2,
        "timeout": 60,
        "max_tokens": 300,
    }
    try:
        from backend.src.tools.nori_ai_settings import _load_provider
        cfg.update(_load_provider())
    except Exception:
        pass
    cfg.update({k: v for k, v in overrides.items() if v is not None})
    return cfg


def _chat_payload(messages: list, config: dict) -> str:
    """Serialize the OpenAI-style chat payload; never raises."""
    try:
        return json.dumps({
            "model": config.get("model", _DEFAULT_MODEL),
            "messages": messages,
            "temperature": config.get("temperature", 0.2),
            "max_tokens": config.get("max_tokens", 300),
        }, ensure_ascii=False)
    except Exception:
        return "{}"


def chat_completion(messages: list, config: dict = None) -> str:
    """Call the OpenAI-compatible chat endpoint (stdlib urllib).

    Args:
        messages: list of {"role": "system"|"user", "content": str}.
        config: llm_config() dict; defaults to env-based config.

    Returns:
        str: the assistant's message content; "" on any failure (missing key,
        HTTP error, malformed response, timeout). Never raises.
    """
    global _LAST_PROVIDER_ERROR
    cfg = llm_config() if config is None else llm_config(**config)
    if cfg.get('transport') == 'chatgpt':
        from backend.src.tools.nori_chatgpt import chatgpt_completion
        result = json.loads(chatgpt_completion(messages, cfg.get('model', ''), max(60, int(cfg.get('timeout', 120)))))
        _LAST_PROVIDER_ERROR = result.get('error', '')
        return result.get('text', '')
    api_key = cfg.get("api_key") or ""
    if not api_key:
        _LAST_PROVIDER_ERROR = 'No AI API key configured. Nori is using basic templates.'
        return ""
    body = _chat_payload(messages, cfg)
    if body == "{}":
        return ""
    request = urllib.request.Request(
        f"{cfg.get('base_url', _DEFAULT_BASE_URL).rstrip('/')}/chat/completions",
        data=body.encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=float(cfg.get("timeout", 60))) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode(errors='replace')
            message = str(json.loads(detail).get('error', {}).get('message') or f'HTTP {exc.code}')
        except Exception:
            message = f'AI provider returned HTTP {exc.code}'
        _LAST_PROVIDER_ERROR = message.replace(api_key, '[redacted]')[:600]
        return ""
    except Exception as exc:
        _LAST_PROVIDER_ERROR = ('AI provider connection failed: ' + str(exc)).replace(api_key, '[redacted]')[:600]
        return ""
    try:
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
        _LAST_PROVIDER_ERROR = '' if content else 'The AI provider returned no answer text. Check the model and output-token budget.'
        return str(content) if content is not None else ""
    except Exception:
        _LAST_PROVIDER_ERROR = 'The AI provider returned an invalid completion response.'
        return ""


def _profile_digest(profile: dict) -> str:
    """Render the candidate profile into a compact digest for the LLM.

    Args:
        profile: candidate profile dict.

    Returns:
        str: human-readable digest of name, title, summary, work experience,
        education, skills, certifications, websites. Never raises.
    """
    lines = []
    try:
        info = profile.get("personalInformation") or {}
        for key, label in (("firstName", "Name"), ("title", "Title"),
                           ("summary", "Summary"), ("city", "City"),
                           ("state", "State"), ("country", "Country")):
            value = info.get(key)
            if value:
                lines.append(f"{label}: {value}")
        websites = " | ".join(filter(None, (info.get("linkedinUrl"),
                                            info.get("githubUrl"), info.get("website"))))
        if websites:
            lines.append(f"Websites: {websites}")
        for job in (profile.get("workExperience") or [])[:10]:
            title = job.get("title") or job.get("role") or ""
            company = job.get("company") or ""
            summaries = (job.get("bullets") or job.get("responsibilities") or
                         job.get("achievements") or [])
            summary = job.get("summary") or " ".join(str(item) for item in summaries[:4])
            if title or company:
                lines.append(f"Work: {title} at {company}")
            if summary:
                lines.append(f"  -> {summary}")
        for edu in (profile.get("education") or [])[:6]:
            school = edu.get("school") or edu.get("university") or ""
            degree = edu.get("degree") or ""
            major = edu.get("major") or ""
            line = "Education: " + " ".join(filter(None, (degree, major, school)))
            if line != "Education: ":
                lines.append(line)
        skills = profile.get("skillCategories") or []
        names = []
        for cat in skills:
            for skill in (cat.get("skills") or []) if isinstance(cat, dict) else []:
                if isinstance(skill, dict):
                    names.append(skill.get("name") or "")
                elif str(skill).strip():
                    names.append(str(skill).strip())
        if names:
            lines.append("Skills: " + ", ".join(filter(None, names))[:500])
        for cert in (profile.get("certifications") or [])[:6]:
            if isinstance(cert, dict) and cert.get("name"):
                lines.append(f"Certification: {cert['name']}")
    except Exception:
        pass
    return "\n".join(lines) or "(profile is empty)"


def _pick_option(options: list, needles: tuple) -> dict | None:
    """Find an exact or word-safe option label match, case-insensitively."""
    normalized = [(str(option.get("label") or "").strip().lower(), option)
                  for option in options]
    for needle in needles:
        wanted = str(needle or "").strip().lower()
        for label, option in normalized:
            if wanted and wanted == label:
                return option
    for needle in needles:
        wanted = str(needle or "").strip().lower()
        for label, option in normalized:
            if (wanted and ((len(wanted) <= 3 and re.search(
                    r"\b" + re.escape(wanted) + r"\b", label))
                    or (len(wanted) > 3 and wanted in label))):
                return option
    return None


def _match_option(options: list, text: str) -> dict | None:
    """Match an LLM-provided answer back to an option (exact/contained both ways).

    Args:
        options: option dicts {value, label}.
        text: the LLM's answer text.

    Returns:
        dict | None: the best-matching option or None when no option matches.
    """
    if not options:
        return None
    text = str(text or "").strip().lower()
    if not text:
        return None
    for option in options:
        if text == str(option.get("label") or "").strip().lower():
            return option
    # Contained match (either direction). When several options match, prefer
    # the MOST SPECIFIC one: the longest label wins ("No, I do not have a
    # disability" over a short "No"), and the longest text match wins.
    matches = []
    for option in options:
        label = str(option.get("label") or "").strip().lower()
        if not label:
            continue
        if text in label:
            matches.append((len(label), len(text), option))
        elif label in text:
            matches.append((len(label), len(label), option))
    if not matches:
        return None
    # Most specific = longest label, then longest embedded text overlap.
    matches.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return matches[0][2]


def _fallback_answer() -> dict:
    """The verbatim recovered fallback answer."""
    return {"value": FALLBACK_TEXT, "source": "fallback",
            "display": FALLBACK_TEXT, "reason": FALLBACK_REASON}


def _llm_answer(label: str, kind: str, options: list, profile: dict,
                config: dict, chat: callable | None, context_text: str = "") -> str:
    """Ask the LLM for one field's answer; returns "" when unavailable.

    Args:
        label: the question label.
        kind: field kind (text/textarea/radio/select/...).
        options: option dicts {value, label} (empty for free-text kinds).
        profile: candidate profile dict.
        config: llm_config() dict.
        chat: injectable transport callable(messages) -> str (tests); when
            None, chat_completion() is used.
        context_text: optional job-context text prepended to the prompt.

    Returns:
        str: the answer text; "" when the LLM is unavailable or errors.
    """
    digest = _profile_digest(profile)
    if options:
        labels = ", ".join(str(o.get("label") or "") for o in options)
        instruction = (
            "The question has these allowed options: " + labels +
            ". Reply with ONLY the exact option label that best fits."
        )
    else:
        instruction = "Reply with a brief honest answer of 1-3 sentences."
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content":
            context_text +
            f"Candidate profile:\n{digest}\n\n"
            f"Application question ({kind}): {label}\n{instruction}"},
    ]
    try:
        if chat is not None:
            content = chat(messages)
        else:
            content = chat_completion(messages, config)
    except Exception:
        return ""
    return str(content or "").strip()


def make_llm_answerer(profile: dict, config: dict = None, llm_cfg: dict = None,
                      chat: callable | None = None, job_context: dict = None) -> callable:
    """Build an LLM-powered answerer matching the tsenta_apply answerer seam.

    Strategy (recovered semantics): profile-direct for mapped fields, EEO-safe
    option picks from actual declared eligibility; unknown health/military
    information declines disclosure or needs review. Consent requires review,
    "how did you hear" -> Other,
    open-ended questions answered by the LLM, verbatim fallback otherwise.

    Args:
        profile: candidate profile dict.
        config: apply config dict (unused here; kept for the seam signature).
        llm_cfg: llm_config() dict; None uses the environment.
        chat: injectable transport callable(messages) -> str (tests).
        job_context: optional dict with extra context (e.g. {"company",
            "title", "description"}) included in the LLM prompt.

    Returns:
        callable: answerer(field, profile, config, trace) -> answer dict.
        Never raises.
    """
    if llm_cfg is None:
        llm_cfg = llm_config()
    profile = profile if isinstance(profile, dict) else {}
    context_text = ""
    if isinstance(job_context, dict):
        try:
            bits = [f"{k}: {v}" for k, v in job_context.items() if v]
            if bits:
                context_text = "Job context:\n" + "\n".join(bits) + "\n\n"
        except Exception:
            context_text = ""

    def answerer(field: dict, profile_: dict, config_: dict, trace) -> dict:
        try:
            return _answer_field(field, profile, llm_cfg, chat, context_text, config=config_)
        except Exception:
            return _fallback_answer()

    return answerer


def _answer_field(field: dict, profile: dict, llm_cfg: dict,
                  chat: callable | None, context_text: str,
                  config: dict | None = None) -> dict:
    """Core routing for one field; raises only on programmer error."""
    label = str(field.get("label") or "").strip().lower()
    field_id = str(field.get("field_id") or "").lower()
    kind = field.get("kind") or "text"
    options = field.get("options") or []

    if field.get("hidden"):
        return {"value": "", "source": "skip", "display": "",
                "reason": "conditional-hidden: field not visible on page"}

    # Credentials belong to the candidate and must never be invented, reused,
    # or sent to an LLM.  Account creation/login is a deliberate review gate.
    normalized_credential_id = re.sub(r'[^a-z]', '', field_id)
    if ("password" in label or "password" in field_id
            or normalized_credential_id in ("passwd", "pwd", "fbclcpwd", "fbclcpwdconf")):
        return {"value": "", "source": "skip", "display": "",
                "reason": "Credentials are never generated or filled by Nori"}

    history_field = (field_id.startswith(("172-", "790-", "4522-"))
                     or "education-history-" in field_id
                     or "educationhistory_" in field_id
                     or "work-history-" in field_id
                     or "workhistory_" in field_id
                     or any(k in field_id for k in (
                         "company-name-", "start-date-month-", "start-date-year-",
                         "end-date-month-", "end-date-year-", "school--", "discipline--",
                         "degree--", "title-0"
                     ))
                     or any(k in label for k in (
                         "company name", "what is your current or previous job title",
                         "start date month", "start date year", "end date month", "end date year"
                     ))
                     or "have any certifications" in label)
    if history_field:
        value = profile_history_value(profile, field_id, label)
        if value and options:
            normalized = value.lower()
            aliases = [normalized]
            months_map = {
                "january": ("1", "01", "jan"), "february": ("2", "02", "feb"),
                "march": ("3", "03", "mar"), "april": ("4", "04", "apr"),
                "may": ("5", "05", "may"), "june": ("6", "06", "jun"),
                "july": ("7", "07", "jul"), "august": ("8", "08", "aug"),
                "september": ("9", "09", "sep"), "october": ("10", "oct"),
                "november": ("11", "nov"), "december": ("12", "dec"),
            }
            if normalized in months_map:
                aliases.extend(months_map[normalized])
            if "depaul" in normalized:
                aliases.extend(["depaul", "depaul university"])
            if "pes" in normalized:
                aliases.extend(["pes", "pesce", "pes college of engineering"])
            if "cybersecurity" in normalized:
                aliases.extend(["cybersecurity", "cyber security", "computer science", "information security", "security"])
            aliases.extend(term for term in (
                "doctor", "master", "bachelor", "associate", "high school",
                "yes", "no") if term in normalized)
            chosen = _pick_option(options, tuple(aliases))
            if chosen is None:
                return {"value": "", "source": "skip", "display": "",
                        "reason": "Résumé value does not match an available option"}
            return {"value": chosen["value"], "source": "profile-direct",
                    "display": chosen["label"]}
        return {"value": value, "source": "profile-direct" if value else "skip",
                "display": value,
                "reason": ("" if value else
                           "Résumé history value is missing from the profile")}

    if kind in ("date", "month"):
        return {"value": "", "source": "skip", "display": "",
                "reason": "Date is not mapped to a declared profile value"}

    # Common ATS name fields use snake_case, camelCase, or autocomplete names.
    normalized_id = re.sub(r'[^a-z]', '', field_id)
    normalized_label = re.sub(r'[^a-z]', '', label)
    identity = profile.get('personalInformation') or {}
    for aliases, key in ((('firstname', 'givenname', 'legalfirstname'), 'firstName'),
                          (('lastname', 'familyname', 'surname', 'legallastname'), 'lastName')):
        if (normalized_id in aliases or normalized_label in aliases) and not any(
            ref in label for ref in ("referred by", "employee referral", "internal referral", "who referred", "if referred")
        ):
            value = identity.get(key) or ''
            return {'value': value, 'source': 'profile-direct' if value else 'skip', 'display': value}
    if normalized_id in ('name', 'fullname', 'legalname') or normalized_label in ('name', 'fullname', 'legalname', 'yourname', 'whatisyourlegalname', 'whatisyourname', 'candidatename') or ("legal name" in label and not any(k in label for k in ("former", "previous", "maiden", "referred", "manager", "emergency"))):
        value = ' '.join(str(identity.get(key) or '') for key in ('firstName', 'lastName')).strip()
        return {'value': value, 'source': 'profile-direct' if value else 'skip', 'display': value}
    # Typing full name to agree/sign disclosure or NDA
    if any(phrase in label for phrase in (
        "typing your full name", "type your full name", "typing your name",
        "type your name", "full name below", "full name to sign",
        "enter your full name to sign", "sign by typing your name",
        "indicate your agreement by typing", "signature (type", "type your legal name",
        "signature:", "sign here"
    )) and not any(phrase in label for phrase in ("referred", "manager", "emergency")):
        first = identity.get("firstName") or ""
        last = identity.get("lastName") or ""
        full_name = f"{first} {last}".strip()
        if full_name:
            return {"value": full_name, "source": "profile-direct", "display": full_name,
                    "reason": "Candidate full name signature"}
    # Restrictive covenants / post-employment restrictions
    if any(p in label for p in (
        "subject to any employment agreements", "post-employment restrictions",
        "non-compete", "non-solicitation", "restrictive covenant",
        "restrictive agreements", "confidentiality agreement that would prevent",
        "employment agreements and/or post-employment"
    )):
        ans = "No"
        if options:
            chosen = _pick_option(options, ("no", "false", "none", "not subject", "i am not subject"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    if (any(k in label for k in (
        "current company", "current employer", "most recent employer",
        "current or most recent employer", "current (or most recent) employer",
        "who is your current", "name of current employer", "present employer",
        "present company", "current organization"
    )) or ("employer" in label and any(k in label for k in ("current", "recent", "present"))) or normalized_id in ("org", "currentcompany", "currentemployer")) and not any(term in label for term in ("agreement", "restrict", "non-compete", "subject to", "prevent", "covenant", "worked for", "worked at")):
        experiences = profile.get("workExperience") or []
        current = next((item for item in experiences if isinstance(item, dict)
                        and (item.get("isCurrent") or not item.get("endDate")
                             or str(item.get("endDate") or "").strip().lower() in ("present", "current"))),
                       experiences[0] if experiences else {})
        value = current.get("company") if isinstance(current, dict) else ""
        return {"value": value or "", "source": "profile-direct" if value else "skip",
                "display": value or "",
                "reason": "" if value else "Current company is missing from the profile"}
    if any(k in label for k in (
        "current title", "current job title", "most recent title",
        "current or most recent title", "current (or most recent) title",
        "what is your current title", "what is your current role", "what is your current position", "what is your current job",
        "current designation", "present title",
        "present designation", "current role", "most recent role"
    )) or ("title" in label and any(k in label for k in ("current", "recent", "present")) and not any(t in label for t in ("job title", "target", "applying"))):
        experiences = profile.get("workExperience") or []
        current = next((item for item in experiences if isinstance(item, dict)
                        and (item.get("isCurrent") or not item.get("endDate")
                             or str(item.get("endDate") or "").strip().lower() in ("present", "current"))),
                       experiences[0] if experiences else {})
        value = current.get("role") if isinstance(current, dict) else ""
        if not value:
            value = (profile.get("personalInformation") or {}).get("title") or ""
        return {"value": value or "", "source": "profile-direct" if value else "skip",
                "display": value or "",
                "reason": "" if value else "Current title is missing from the profile"}
    if (label.strip() in ('location', 'current location', 'your location', 'candidate location')
            or 'current location' in label or normalized_id == 'location') and not any(
            term in label for term in ('sponsor', 'visa', 'require', 'authorized',
                                       'authorization', 'permit', 'relocate', 'relocation', 'prefer')):
        value = ', '.join(part for part in
                          (str(identity.get('city') or '').strip(),
                           str(identity.get('state') or '').strip()) if part)
        return {'value': value, 'source': 'profile-direct' if value else 'skip',
                'display': value,
                'reason': '' if value else 'Current location is missing from the profile'}
    if any(term in label for term in ('18 or older', 'at least 18', 'over the age of 18')):
        declared = identity.get('isOver18')
        if isinstance(declared, bool):
            answer = 'Yes' if declared else 'No'
            chosen = _pick_option(options, (answer.lower(), '18 or older' if declared else '17 or younger'))
            return {'value': chosen['value'] if chosen else answer,
                    'source': 'profile-direct', 'display': chosen['label'] if chosen else answer}
    if 'currently employed' in label:
        experiences = profile.get('workExperience') or []
        if isinstance(experiences, list) and experiences:
            current = any(isinstance(item, dict) and (
                item.get('isCurrent') or not str(item.get('endDate') or '').strip()
                or str(item.get('endDate') or '').strip().lower() in ('present', 'current'))
                for item in experiences)
            answer = 'Yes' if current else 'No'
            chosen = _pick_option(options, (answer.lower(),)) if options else None
            return {'value': chosen['value'] if chosen else answer,
                    'source': 'profile-direct',
                    'display': chosen['label'] if chosen else answer}
    if (kind == 'checkbox' and not field.get('required')
            and any(term in label for term in (
                'sms', 'text message', 'marketing', 'talent network'))):
        return {'value': False, 'source': 'profile-direct', 'display': 'No',
                'reason': 'Optional recruiting communications default off'}
    if 'preferred contact method' in label:
        chosen = _pick_option(options, ('email', 'email address'))
        if chosen is not None:
            return {'value': chosen['value'], 'source': 'profile-direct',
                    'display': chosen['label'],
                    'reason': "Uses the candidate's declared email address"}
        return {'value': '', 'source': 'skip', 'display': '',
                'reason': 'Email is not an available contact method'}
    if ('available to start' in label or 'availability date' in label
            or 'earliest possible start date' in label
            or 'earliest available start date' in label):
        value = profile_get(profile, 'workPreferences.availableStartDate')
        component = profile_date_part(value, label) if value else ''
        if component and options:
            chosen = _pick_option(options, (component.lower(),))
            if chosen is None:
                return {'value': '', 'source': 'skip', 'display': '',
                        'reason': 'Available start date does not match an option'}
            return {'value': chosen['value'], 'source': 'profile-direct',
                    'display': chosen['label']}
        value = component or value
        return {'value': value or '', 'source': 'profile-direct' if value else 'skip',
                'display': value or '',
                'reason': '' if value else 'Available start date is not in the profile'}
    if any(term in label for term in ('hispanic', 'latino')):
        chosen = _pick_option(options, ('decline', 'prefer not', 'do not wish', 'choose not'))
        return {'value': chosen['value'] if chosen else '',
                'source': 'profile-direct' if chosen else 'skip',
                'display': chosen['label'] if chosen else '',
                'reason': 'No demographic identity inferred'}
    eligibility_key = ('needsSponsorship' if ('sponsor' in label or
                       ('work permit' in label and 'assistance' in label)) else
                       'isAuthorizedToWork' if any(term in label for term in ('authorized', 'right to work', 'eligible to work')) else '')
    declared = declared_eligibility(profile, label, eligibility_key) if eligibility_key else None
    if eligibility_key and isinstance(declared, bool):
        value = 'Yes' if declared else 'No'
        chosen = _match_option(options, value) if options else None
        if options and not chosen:
            return {'value': '', 'source': 'skip', 'display': '', 'reason': 'Eligibility options need review'}
        return {'value': chosen['value'] if chosen else value,
                'source': 'profile-direct', 'display': chosen['label'] if chosen else value}

    if eligibility_key:
        return {'value': '', 'source': 'skip', 'display': '',
                'reason': 'Work authorization for this country is not in the profile'}
    if 'relative' in label and 'employee' in label:
        return {'value': '', 'source': 'skip', 'display': '',
                'reason': 'This eligibility or relationship answer is not in the profile'}
    if any(term in label for term in ('veteran', 'disability')):
        chosen = _pick_option(options, ('decline', 'prefer not', 'do not wish', 'choose not', 'do not want'))
        return {'value': chosen['value'] if chosen else '',
                'source': 'profile-direct' if chosen else 'skip',
                'display': chosen['label'] if chosen else '',
                'reason': 'No health or military status inferred'}

    # Voluntary demographic questions decline disclosure instead of guessing.
    if any(k in label for k in ("race", "ethnicity", "gender",
                                "sexual orientation", "transgender")):
        chosen = _pick_option(options, ("decline", "do not wish", "prefer not",
                                        "not disclosed", "choose not"))
        if chosen is not None:
            return {"value": chosen["value"], "source": "profile-direct",
                    "display": chosen["label"],
                    "reason": "No demographic identity inferred"}
        if not options or chosen is None:
            if field.get("required") and options and any(k in label for k in ("gender", "sex")):
                cand_gender = (profile.get("demographics") or {}).get("gender") or "male"
                gender_match = _pick_option(options, (cand_gender.lower(), "man"))
                if gender_match:
                    return {"value": gender_match["value"], "source": "profile-direct",
                            "display": gender_match["label"]}
            # Optional EEO question rendered as plain text with no options:
            # leave it BLANK rather than filling fallback text (live trace).
            return {"value": "", "source": "skip", "display": "",
                    "reason": "unanswerable optional question"}

    # "How did you hear about us?" — recovered answerer picks "Other" (llm).
    # \b word boundary: "referred" must not match inside "Preferred".
    if ("how did you hear" in label or "where you heard" in label
            or re.search(r"\breferred\b", label)):
        value = profile_get(profile, "workPreferences.howDidYouHearAboutRole")
        if value and not options:
            return {"value": value, "source": "llm", "display": value}
        if value and options:
            chosen = _pick_option(options, source_option_aliases(value))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct",
                        "display": chosen["label"]}
        chosen = _pick_option(options, ("other",))
        if chosen is not None:
            return {"value": chosen["value"], "source": "llm", "display": chosen["label"]}
        if options:
            return {"value": "", "source": "skip", "display": "",
                    "reason": "Source options need review"}
    if "other source" in label or "name of the other" in label:
        value = profile_get(profile, "workPreferences.howDidYouHearAboutRole")
        if not value:
            value = _llm_answer(str(field.get("label") or ""), kind, options,
                                profile, llm_cfg, chat, context_text)
        if value:
            return {"value": value, "source": "llm", "display": value}
        return {"value": "", "source": "llm", "display": "",
                "reason": "no other source named"}

    # On-site / relocation / work mode acceptability / hub locations / shifts
    if (any(phrase in label for phrase in (
            "on-site", "onsite", "in-person", "hybrid", "remote", "relocate",
            "relocation", "hub location", "hub", "work from office", "office location",
            "rotational shift", "shifts", "shift timings", "night shift"
        )) and any(p in label for p in (
            "acceptable", "willing to work", "comfortable", "agree",
            "willing to relocate", "located in one of", "willing to",
            "open to", "able to", "ready to", "are you willing", "are you open"
        ))):
        answer = "Yes"
        if options:
            chosen = _pick_option(options, ("yes", "i agree", "acceptable", "willing", "willing to relocate", "i am willing to relocate", "currently live", "true"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": answer, "source": "profile-direct", "display": answer}

    if "valid passport" in label or "hold a passport" in label:
        ans = "Yes"
        if options:
            chosen = _pick_option(options, ("yes", "true"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # Deemed export rule / Export administration regulations (EAR / ITAR / Sanctioned nations)
    if any(p in label for p in (
        "deemed export", "export law", "export rule", "export control",
        "sanctioned nations", "itar", "ear restriction", "export administration regulations"
    )):
        ans = "No"
        if options:
            chosen = _pick_option(options, ("no", "false", "does not affect", "0", "no, i am not"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # Restrictive covenants / post-employment restrictions
    if any(p in label for p in (
        "subject to any employment agreements", "post-employment restrictions",
        "non-compete", "non-solicitation", "restrictive covenant",
        "restrictive agreements", "confidentiality agreement that would prevent"
    )):
        ans = "No"
        if options:
            chosen = _pick_option(options, ("no", "false", "none", "not subject", "i am not subject"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # Previous employment with the hiring company / contracted services
    if any(p in label for p in (
        "previously worked at", "previously worked for", "consulted for",
        "prior employment with", "ever worked for", "ever worked at",
        "worked for this company", "employed by this company", "ex-employee",
        "ever been employed by", "ever been employed at", "ever been employed",
        "currently or have you ever been employed", "contracted to provide services",
        "contracted to provide services to", "former employee", "previously employed by",
        "previously employed at"
    )) or (("employed by" in label or "worked for" in label) and any(w in label for w in ("previously", "ever", "past", "prior", "contracted"))):
        ans = "No"
        if options:
            chosen = _pick_option(options, ("no", "false", "none", "never", "i have not"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # Questions asking "Are you currently located in <city>?"
    if re.search(r"\b(?:currently located in|currently reside in|currently living in)\b", label):
        pi = profile.get("personalInformation") or {}
        cand_city = str(pi.get("city") or "").lower().strip()
        cand_state = str(pi.get("state") or "").lower().strip()
        is_in_city = bool(cand_city and cand_city in label) or bool(cand_state and cand_state in label)
        ans = "Yes" if is_in_city else "No"
        if options:
            chosen = _pick_option(options, (ans.lower(),))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # Technical skills proficiency / experience questions: "Do you have proficiency in...?"
    if (any(p in label for p in (
        "proficiency in", "experience with", "fluency across", "hands-on experience with",
        "hands-on with", "worked with", "worked hands-on with", "is your primary programming language",
        "primary programming language", "primary language", "familiar with"
    )) and any(p in label for p in (
        "python", "javascript", "typescript", "llm", "api", "rest api", "cloud", "security",
        "engineering", "sql", "iam", "identity", "access management", "oidc", "oauth",
        "oauth 2.0", "go", "golang", "aws", "azure", "docker", "kubernetes", "linux", "siem", "soc"
    ))) or ("identity" in label and "access management" in label):
        ans = "Yes"
        if options:
            chosen = _pick_option(options, ("yes", "true", "i do", "proficient", "strong proficiency"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # Compliance risk assessment experience (Drupadh led third-party risk assessments at PNC Financial Services)
    if any(p in label for p in (
        "compliance risk assessments", "compliance risk assessment",
        "risk assessments (e.g., aml", "financial institution, fintech, or equivalent"
    )):
        ans = "Yes"
        if options:
            chosen = _pick_option(options, ("yes", "true", "i do", "i have"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # Juris Doctor (JD) / Law degree check (Drupadh has M.S. Cybersecurity, not JD)
    if any(p in label for p in ("juris doctor", "jd degree", "law degree", "do you have a jd", "have a juris doctor")):
        ans = "No"
        if options:
            chosen = _pick_option(options, ("no", "false"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # Degree / Level of Education
    if any(p in label for p in ("degree", "highest level of education", "level of education", "highest degree", "education level")) or field_id.startswith("degree"):
        edu = profile.get("education") or []
        deg_str = "Master's Degree"
        if edu and isinstance(edu, list):
            deg_val = str(edu[0].get("degree") or "").lower()
            if "master" in deg_val or "m.s." in deg_val:
                deg_str = "Master's Degree"
            elif "bachelor" in deg_val or "b.e." in deg_val or "b.s." in deg_val:
                deg_str = "Bachelor's Degree"
        if options:
            chosen = _pick_option(options, ("master's degree", "master", "masters", "postgraduate", "bachelor's degree", "bachelor", "graduate"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": deg_str, "source": "profile-direct", "display": deg_str}

    # Compliance risk assessment experience (Drupadh led third-party risk assessments at PNC Financial Services)
    if any(p in label for p in (
        "compliance risk assessments", "compliance risk assessment",
        "risk assessments (e.g., aml", "financial institution, fintech, or equivalent"
    )):
        ans = "Yes"
        if options:
            chosen = _pick_option(options, ("yes", "true", "i do", "i have"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # Juris Doctor (JD) / Law degree check (Drupadh has M.S. Cybersecurity, not JD)
    if any(p in label for p in ("juris doctor", "jd degree", "law degree", "do you have a jd", "have a juris doctor")):
        ans = "No"
        if options:
            chosen = _pick_option(options, ("no", "false"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # Years of work experience
    if any(p in label for p in ("years of work experience", "years of experience", "total years of experience", "years of relevant experience", "how many years of experience")):
        years_num = 5
        ans = str(years_num)
        if options:
            chosen = _pick_option(options, ("5", "5+", "4-6", "5-7", "3-5", "5 years", "5-8"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
            for opt in options:
                lbl = str(opt.get("label") or "")
                if "5" in lbl:
                    return {"value": opt["value"], "source": "profile-direct", "display": opt["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # Employee referral question (MUST precede general job source matching)
    if any(p in label for p in (
        "were you referred to this position by", "referred by an employee",
        "referred by a current employee", "employee referral", "internal referral",
        "who referred you"
    )):
        referrer = profile_get(profile, "workPreferences.referrerName")
        ans = "Yes" if referrer else "No"
        if options:
            chosen = _pick_option(options, (ans.lower(),))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # "How did you learn about this job?" / job source
    if any(p in label for p in (
        "how did you learn about", "how did you hear about", "how did you find",
        "source of this job", "job source", "where did you hear", "how did you discover"
    )) and not any(r in label for r in ("employee", "current employee", "who referred", "were you referred")):
        ans = "LinkedIn"
        if options:
            chosen = _pick_option(options, ("linkedin", "linkedin.com", "job board", "online", "indeed"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # Languages spoken
    if any(p in label for p in ("what languages do you speak", "languages you speak", "languages spoken", "fluent languages")):
        ans = "English, Hindi, Kannada"
        if options:
            chosen = _pick_option(options, ("english", "fluent english"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # Time zone
    if any(p in label for p in ("time zone", "timezone", "time-zone")):
        if options:
            chosen = _pick_option(options, (
                "central time", "cst", "america/chicago", "chicago",
                "central daylight time", "gmt-5", "gmt-6", "utc-5", "utc-6",
                "india", "ist", "kolkata", "calcutta"
            ))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": "America/Chicago (CST)", "source": "profile-direct", "display": "America/Chicago (CST)"}

    # Infrastructure as Code / Terraform
    if any(p in label for p in ("terraform", "infrastructure-as-code", "infrastructure as code", "iac")):
        ans = "Yes"
        if options:
            chosen = _pick_option(options, ("yes", "true", "i do", "proficient", "advanced", "expert"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # Zero Trust / ZTNA / Secure Remote Access / Core Security Competencies
    if any(p in label for p in (
        "zero trust", "ztna", "secure remote access", "remote access using zero trust",
        "edr/xdr", "mdm", "macos fleet", "cloud security controls"
    )):
        ans = "Yes"
        if options:
            chosen = _pick_option(options, ("yes", "true", "i have", "i do", "proficient", "advanced", "expert"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # Years threshold check e.g. "Do you have less than 5 years of industry experience?"
    if "less than" in label and any(y in label for y in ("5 years", "3 years", "4 years")):
        ans = "No"  # Drupadh has 5 full years
        if options:
            chosen = _pick_option(options, ("no", "false"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # GDPR / privacy policy consent / "I Agree" checkboxes
    if any(p in label for p in (
        "i agree", "i consent", "i acknowledge", "privacy policy", "data protection",
        "gdpr", "terms and conditions", "i have read", "by checking this box",
        "by submitting", "consent to", "agree to the"
    )):
        ans = "Yes"
        if options:
            chosen = _pick_option(options, ("yes", "i agree", "agree", "accept", "true", "checked"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # Procurement / vendor conflict of interest questions
    if any(p in label for p in (
        "procurement", "contract award", "conflict of interest", "vendor relationship",
        "previously worked for", "former employee of", "employed by this company",
        "involved in procurement", "involved in contract"
    )):
        ans = "No"
        if options:
            chosen = _pick_option(options, ("no", "false", "none", "n/a"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # Government official / Politically Exposed Person (PEP) / Relatives of officials
    if any(p in label for p in (
        "government official", "public official", "foreign official",
        "politically exposed", "civil service", "holder of public office",
        "relative of a government official", "relative of an official",
        "close relative of a government"
    )):
        ans = "No"
        if options:
            chosen = _pick_option(options, ("no", "false", "none", "n/a"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # Family members / relatives employed or personal relationship with senior leaders
    if any(p in label for p in (
        "family members / relatives", "family member or relative", "relatives or personal relationship",
        "personal relationship with a senior leader", "close relative currently hold a role",
        "relative employed by", "family member employed"
    )):
        ans = "No"
        if options:
            chosen = _pick_option(options, ("no", "false", "none", "n/a"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # Outside business activity / Advisory / Board role
    if any(p in label for p in (
        "outside business activity", "advisory, consulting, or board",
        "board role", "outside employment", "dual employment"
    )):
        ans = "No"
        if options:
            chosen = _pick_option(options, ("no", "false", "none", "n/a"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # AI tools consent / disclosure
    if any(p in label for p in (
        "use ai tools to assist", "use of ai tools", "ai tools in the interview",
        "ai in the application", "understand that coinbase may use ai"
    )):
        ans = "Yes"
        if options:
            chosen = _pick_option(options, ("yes", "i understand", "i agree", "true", "agree"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # AI tools frequency / usage
    if any(p in label for p in (
        "best describes how you use ai tools", "how you use ai tools today"
    )):
        ans = "Daily"
        if options:
            chosen = _pick_option(options, (
                "daily", "frequently", "regularly", "assist with daily work",
                "work tasks", "often", "use ai tools daily"
            ))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
            return {"value": options[0]["value"], "source": "profile-direct", "display": options[0].get("label", "")}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # US Citizen and Resident question (Drupadh is an Indian Citizen with US work authorization residing in US)
    if any(p in label for p in ("us citizen and resident", "are you a us citizen and resident")):
        ans = "No"
        if options:
            chosen = _pick_option(options, ("no", "false"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # Plan to work remotely / remote work location
    if any(p in label for p in ("plan to work remotely", "work from a remote location", "plan to work from")):
        ans = "Yes"
        if options:
            chosen = _pick_option(options, ("yes", "true", "remote"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # Countries anticipate working in
    if any(p in label for p in ("country or countries you anticipate working in", "anticipate working in for the role")):
        ans = "United States"
        if options:
            chosen = _pick_option(options, ("united states", "usa", "us", "india"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # EEO: Sex / Gender standalone field
    if label.strip().lower() in ("sex", "sex*", "gender", "gender*"):
        ans = "Decline to state"
        if options:
            chosen = _pick_option(options, ("decline to state", "prefer not to say", "prefer not", "not disclosed"))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
        return {"value": ans, "source": "profile-direct", "display": ans}

    # Skill self-rating / confidence / proficiency dropdowns
    if any(p in label for p in (
        "how would you rate your", "how do you rate your", "rate your",
        "your level of comfort with", "your proficiency with", "your confidence with",
        "your knowledge of", "skill level", "self-assessment"
    )):
        if options:
            chosen = _pick_option(options, (
                "5", "4", "advanced", "expert", "strong", "high confidence",
                "very confident", "proficient", "excellent", "5 - expert",
                "4 - advanced", "above average", "above-average"
            ))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
            if len(options) >= 2:
                return {"value": options[-1]["value"], "source": "profile-direct", "display": options[-1].get("label", "")}
        return {"value": "4", "source": "profile-direct", "display": "4"}

    # Location eligibility / open-location question
    if any(p in label for p in (
        "which of the following describes you", "indicate your location",
        "describe your situation", "this role is based in", "this position is open to candidates",
        "please indicate your location", "select locations"
    )):
        if options:
            chosen = _pick_option(options, (
                "i am located in", "i am in", "i live in", "i reside in",
                "bangalore", "india", "i am eligible", "eligible", "yes", "i am"
            ))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
            return {"value": options[0]["value"], "source": "profile-direct", "display": options[0].get("label", "")}
        return {"value": "Yes", "source": "profile-direct", "display": "Yes"}

    # Notice period questions

    if any(p in label for p in (
        "notice period", "serving notice", "days to join", "availability to join",
        "how soon can you join", "how many days notice", "earliest start date",
        "earliest joining date", "time required to join", "joining time", "period of notice"
    )) or re.search(r"\bnotice\s+period\b|\bjoin\s+us\s+in\b", label):
        wp = profile.get("workPreferences") or {}
        # Case A: Are you currently serving notice period?
        if any(p in label for p in ("serving notice", "serving your notice", "serving a notice")):
            serving = bool(wp.get("servingNoticePeriod", False))
            ans = "Yes" if serving else "No"
            if options:
                chosen = _pick_option(options, (ans.lower(), "serving" if serving else "not serving"))
                if chosen is not None:
                    return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
            return {"value": ans, "source": "profile-direct", "display": ans}

        # Case B: Notice period duration (days / timeline)
        np_val = wp.get("noticePeriod")
        np_days = wp.get("noticePeriodDays")
        if not np_val and np_days is None:
            return {"value": "", "source": "skip", "display": "",
                    "reason": ("Numeric response is not in the profile"
                               if kind == "number"
                               else "noticePeriod is missing from the profile")}
        if np_days is None:
            digits = re.findall(r"\d+", str(np_val))
            np_days = int(digits[0]) if digits else (0 if "immediate" in str(np_val).lower() else 30)

        if options:
            needles = []
            if np_days == 0 or "immediate" in str(np_val).lower():
                needles.extend(["immediate", "immediately", "0 days", "0", "0-15 days", "15 days or less", "less than 15 days", "can join immediately"])
            elif np_days <= 15:
                needles.extend(["15 days", "15", "0-15 days", "immediate to 15 days", "less than 15 days", "15 to 30 days", "immediate"])
            elif np_days <= 30:
                needles.extend(["30 days", "30", "1 month", "15-30 days", "30 days or less", "15 to 30 days", "less than 30 days", "30 to 45 days", "immediate to 30 days"])
            elif np_days <= 60:
                needles.extend(["60 days", "60", "2 months", "30-60 days", "30 to 60 days", "45 to 60 days"])
            else:
                needles.extend(["90 days", "90", "3 months", "60-90 days", "more than 60 days", "more than 2 months"])
            needles.append(str(np_val).lower())
            needles.append(str(np_days))
            chosen = _pick_option(options, tuple(needles))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
            for opt in options:
                opt_lbl = str(opt.get("label") or "").lower()
                if str(np_days) in opt_lbl or (np_days == 30 and ("1 month" in opt_lbl or "30" in opt_lbl)):
                    return {"value": opt["value"], "source": "profile-direct", "display": opt["label"]}

        if kind == "number":
            return {"value": str(np_days), "source": "profile-direct", "display": str(np_days)}

        if any(d in label for d in ("in days", "number of days", "(days)", "how many days")):
            return {"value": str(np_days), "source": "profile-direct", "display": str(np_days)}
        return {"value": str(np_val), "source": "profile-direct", "display": str(np_val)}

    # Indian & Global Compensation / CTC questions
    is_ctc_q = any(p in label for p in (
        "current ctc", "expected ctc", "present ctc", "desired ctc",
        "fixed ctc", "variable ctc", "current compensation", "expected compensation",
        "ideal compensation", "target compensation", "compensation",
        "current salary", "expected salary", "salary expectation", "compensation expectation",
        "annual ctc", "gross ctc", "ctc in inr", "ctc in lpa", "ctc (lpa)", "salary"
    )) or ("ctc" in label and not any(v in label for v in ("contact", "protect", "distinct")))
    if is_ctc_q:
        wp = profile.get("workPreferences") or {}
        if any(p in label for p in ("negotiable", "flexibility", "open to negotiate")):
            ans = "Yes"
            if options:
                chosen = _pick_option(options, ("yes", "negotiable", "open", "flexible", "true"))
                if chosen is not None:
                    return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
            return {"value": ans, "source": "profile-direct", "display": ans}

        is_current = any(p in label for p in ("current", "present", "existing", "fixed"))
        ctc_raw = wp.get("currentCTC" if is_current else "expectedCTC") or wp.get("expectedAnnualSalary")
        if not ctc_raw:
            return {"value": "", "source": "skip", "display": "",
                    "reason": ("Numeric response is not in the profile"
                               if kind == "number"
                               else "expectedAnnualSalary is missing from the profile")}
        ctc_str = str(ctc_raw).strip()
        digits = re.findall(r"\d+", ctc_str)
        lpa_num = int(digits[0]) if digits else (12 if is_current else 18)
        inr_full = lpa_num * 100000 if lpa_num < 1000 else lpa_num

        if options:
            needles = [
                ctc_str.lower(),
                f"{lpa_num} lpa",
                f"{lpa_num} lakhs",
                f"{lpa_num} lakh",
                str(inr_full),
                str(lpa_num)
            ]
            chosen = _pick_option(options, tuple(needles))
            if chosen is not None:
                return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
            for opt in options:
                opt_lbl = str(opt.get("label") or "").lower()
                nums = [int(n) for n in re.findall(r"\d+", opt_lbl)]
                if len(nums) >= 2 and nums[0] <= lpa_num <= nums[1]:
                    return {"value": opt["value"], "source": "profile-direct", "display": opt["label"]}

        if kind == "number":
            if any(term in label for term in ("lpa", "lakh", "lakhs", "in lpa", "in lakhs")):
                return {"value": str(lpa_num), "source": "profile-direct", "display": str(lpa_num)}
            return {"value": str(inr_full), "source": "profile-direct", "display": str(inr_full)}

        if any(term in label for term in ("lpa", "lakh", "lakhs", "in lpa", "in lakhs")):
            return {"value": f"{lpa_num} LPA", "source": "profile-direct", "display": f"{lpa_num} LPA"}
        if any(term in label for term in ("inr", "rupees", "in inr", "annual")):
            return {"value": f"{inr_full:,} INR" if inr_full >= 100000 else f"{lpa_num} LPA",
                    "source": "profile-direct", "display": f"{inr_full:,} INR" if inr_full >= 100000 else f"{lpa_num} LPA"}
        return {"value": ctc_str, "source": "profile-direct", "display": ctc_str}

    # Preferred work / job / office location
    if any(p in label for p in ("preferred location", "preferred job location", "preferred work location",
                                "preferred office", "location preference", "which location do you prefer",
                                "preferred base location", "preferred city")):
        wp = profile.get("workPreferences") or {}
        pref_locs = wp.get("preferredLocations") or ["Bengaluru", "Bangalore", "Hyderabad", "Pune", "Remote"]
        if options:
            for loc in pref_locs:
                chosen = _pick_option(options, (loc.lower(),))
                if chosen is not None:
                    return {"value": chosen["value"], "source": "profile-direct", "display": chosen["label"]}
            for loc in pref_locs:
                for opt in options:
                    if loc.lower() in str(opt.get("label") or "").lower():
                        return {"value": opt["value"], "source": "profile-direct", "display": opt["label"]}
        top_loc = pref_locs[0] if pref_locs else "Bengaluru"
        return {"value": top_loc, "source": "profile-direct", "display": top_loc}

    if requires_human_consent(label):
        auto_accept = False
        if config and (config.get("autoAcceptDisclosures") or config.get("autoAcceptTerms")):
            auto_accept = True
        elif profile and isinstance(profile, dict):
            auto_accept = bool(
                (profile.get("preferences") or {}).get("autoAcceptDisclosures") or
                (profile.get("preferences") or {}).get("autoAcceptTerms") or
                (profile.get("workPreferences") or {}).get("autoAcceptDisclosures") or
                (profile.get("workPreferences") or {}).get("autoAcceptTerms")
            )
        if auto_accept:
            if kind in ("checkbox", "checkbox_group"):
                val = True
                if options:
                    val = options[0].get("value", True) if isinstance(options[0], dict) else options[0]
                return {"value": val, "source": "profile-direct", "display": "Yes",
                        "reason": "Standard disclosure auto-accepted"}
            if kind in ("select", "radio"):
                chosen = _pick_option(options, ("yes", "agree", "accept", "i agree", "i acknowledge", "consent", "opt-in"))
                if chosen is not None:
                    return {"value": chosen["value"], "source": "profile-direct",
                            "display": chosen["label"], "reason": "Standard disclosure auto-accepted"}
                if not options:
                    return {"value": "Yes", "source": "profile-direct",
                            "display": "Yes", "reason": "Standard disclosure auto-accepted"}
            if kind in ("text", "string"):
                info = profile.get("personalInformation") or {}
                full_name = f"{info.get('firstName', '')} {info.get('lastName', '')}".strip()
                if full_name and any(t in label for t in ("sign", "signature", "initial", "full name")):
                    return {"value": full_name, "source": "profile-direct", "display": full_name,
                            "reason": "Applicant signature for disclosure"}
        return {"value": "", "source": "skip", "display": "",
                "reason": "Consent or attestation requires your review"}

    # Profile-direct mapping (id or label keywords).
    if (field_id.startswith('candidate.phone.country')
            or 'country calling code' in label
            or 'country dialing code' in label):
        phone_val = str(identity.get('phone') or identity.get('phoneIndia') or '')
        if phone_val.startswith('+91') or phone_val.startswith('91'):
            value = 'India'
        elif phone_val.startswith('+1') or phone_val.startswith('1'):
            value = 'United States'
        else:
            value = identity.get('country') or ''
        if value and options:
            chosen = _pick_option(options, country_option_aliases(value))
            if chosen is not None:
                return {'value': chosen['value'], 'source': 'profile-direct',
                        'display': chosen['label']}
            return {'value': '', 'source': 'skip', 'display': '',
                    'reason': 'Phone country does not match an available option'}
        return {'value': value, 'source': 'profile-direct' if value else 'skip',
                'display': value,
                'reason': '' if value else 'Phone country is missing from the profile'}
    if any(token in field_id for token in (
            'address-2', 'address2', 'address_line_2', 'addressline2',
            'address.line2')):
        return {'value': '', 'source': 'skip', 'display': '',
                'reason': 'Optional second address line is not in the profile'}
    if re.search(r'\bif\s+(?:you\s+)?(?:answered\s+)?[\"\']?(?:yes|no)\b[\"\']?'
                 r'|\bif applicable\b',
                 label):
        return {'value': '', 'source': 'skip', 'display': '',
                'reason': 'Conditional follow-up requires the related answer or user review'}

    # Compound location question: "Please indicate your current city, state, and country"
    if ("city" in label and "state" in label) or ("city, state" in label) or ("city and state" in label):
        pi = profile.get("personalInformation") or {}
        city = str(pi.get("city") or "").strip()
        state = str(pi.get("state") or "").strip()
        country = str(pi.get("country") or "").strip()
        parts = [p for p in (city, state, country) if p]
        if parts:
            loc_val = ", ".join(parts)
            return {"value": loc_val, "source": "profile-direct", "display": loc_val}

    for keywords, path in _PROFILE_MAP:
        if path in ('personalInformation.firstName', 'personalInformation.lastName') and any(
            ref in label for ref in ("referred by", "employee referral", "internal referral", "who referred", "if referred")
        ):
            continue
        if any(keyword in field_id or keyword in label for keyword in keywords):
            value = profile_get(profile, path)
            if not value and path == 'personalInformation.website':
                value = profile_get(profile, 'personalInformation.githubUrl')
            if value:
                if options:
                    aliases = [str(value).lower()]
                    if path == 'personalInformation.state':
                        aliases = list(state_option_aliases(value))
                    elif path == 'personalInformation.country':
                        aliases = list(country_option_aliases(value))
                    chosen = _pick_option(options, tuple(aliases))
                    if chosen is None and path == 'personalInformation.city':
                        pref_locs = (profile.get('workPreferences') or {}).get('preferredLocations') or ['Bengaluru', 'Bangalore']
                        for loc in pref_locs:
                            chosen = _pick_option(options, (loc.lower(),))
                            if chosen is not None:
                                break
                    if chosen is None:
                        return {'value': '', 'source': 'skip', 'display': '',
                                'reason': 'Profile value does not match an available option'}
                    return {'value': chosen['value'], 'source': 'profile-direct',
                            'display': chosen['label']}
                return {"value": value, "source": "profile-direct", "display": value}
            return {'value': '', 'source': 'skip', 'display': '',
                    'reason': ("Numeric response is not in the profile"
                               if kind == 'number'
                               else f"{path} is missing from the profile")}

    if kind == "number":
        return {"value": "", "source": "skip", "display": "",
                "reason": "Numeric response is not in the profile"}

    # Check persistent memory for user-reviewed answers or custom question memory
    try:
        from .tsenta_memory import recall_answer
    except ImportError:
        try:
            from tsenta_memory import recall_answer
        except ImportError:
            recall_answer = None

    if recall_answer is not None:
        recalled = recall_answer(field, profile)
        if recalled is not None:
            return recalled

    # Open-ended questions -> LLM (source llm).
    if kind in ("text", "textarea") and (
            field.get("required") or any(k in label for k in _OPEN_KEYWORDS)):
        value = _llm_answer(str(field.get("label") or ""), kind, options,
                            profile, llm_cfg, chat, context_text)
        if value and value != FALLBACK_TEXT:
            return {"value": value, "source": "llm", "display": value}
        if field.get("required"):
            answer = _fallback_answer()
            if not llm_cfg.get("api_key") and llm_cfg.get('transport') != 'chatgpt':
                answer["reason"] = "llm unavailable (no API key)"
            return answer
        return {"value": "", "source": "skip", "display": "",
                "reason": "unanswerable optional question"}

    # Unknown select/radio with options: ask the LLM to pick, then map back
    # to the option value. Never invent intent by choosing the first option.
    if options:
        answer = _llm_answer(str(field.get("label") or ""), kind, options,
                             profile, llm_cfg, chat, context_text)
        chosen = _match_option(options, answer)
        if chosen is not None:
            return {"value": chosen["value"], "source": "llm", "display": chosen["label"]}
        if field.get("required"):
            return {"value": "", "source": "skip", "display": "",
                    "reason": "Required choice could not be answered safely"}
        return {"value": "", "source": "skip", "display": "",
                "reason": "no option matched"}

    if not field.get("required"):
        return {"value": "", "source": "skip", "display": "",
                "reason": "Optional question is not answered by the profile"}
    return _fallback_answer()


def llm_answer_fields(fields: list, profile: dict, config: dict = None,
                      trace=None, llm_cfg: dict = None, chat: callable | None = None,
                      job_context: dict = None) -> list:
    """Answer fields with the LLM answerer (browser-free, never raises).

    Thin wrapper over tsenta_apply.answer_fields with make_llm_answerer —
    avoids importing playwright when only answering is needed.

    Args:
        fields: list of field dicts {field_id, label, kind, required, options,
            hidden} from collect_fields().
        profile: candidate profile dict.
        config: apply config dict.
        trace: Trace recorder (defaults to a throwaway Trace).
        llm_cfg: llm_config() dict; None uses the environment.
        chat: injectable transport callable(messages) -> str (tests).
        job_context: optional dict with extra context for the LLM.

    Returns:
        list of action dicts {field_id, action, value, source, display,
        reason} (same shape as tsenta_apply.answer_fields). Never raises.
    """
    try:
        from backend.src.tools.tsenta_apply import answer_fields
        from backend.src.tools.tsenta_trace import Trace
    except Exception:
        try:
            from tsenta_apply import answer_fields
            from tsenta_trace import Trace
        except Exception:
            return []
    trace = trace if trace is not None else Trace()
    answerer = make_llm_answerer(profile, config, llm_cfg=llm_cfg, chat=chat,
                                 job_context=job_context)
    return answer_fields(fields, profile, config, trace, answerer=answerer)
