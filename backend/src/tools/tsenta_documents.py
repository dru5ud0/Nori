"""tsenta_documents — resume summary + cover letter generation (honest/optimized).

Recovered product semantics (internal_api_map + cover_letter_data_jefferies.json):
- preferences: optimizationMode ("honest" | "aggressive"), coverLetterMode
  ("honest" | "generated" | "off"), autoApproveResume, autoApproveCoverLetter.
- cover letter response shape:
  {"coverLetterHtml": null, "coverLetterText": ..., "status": "COMPLETED",
   "useCoverLetter": bool, "coverLetterMode": ..., "coverLetterMetadata": null}

Honest mode = NO fabrication: documents are assembled strictly from profile
facts (never invented). An LLM may only rephrase existing facts; when no API
key is available the templates are used directly.

Optimized mode ("aggressive", recovered ATS_SCRAPING_ENGINE.md): keywords are
extracted from the job description, bullets/experience/skills are reordered to
prioritize keyword matches (no facts invented), and the LLM may rewrite the
text with a strict no-invention guard.

Public functions return dicts, catch exceptions internally and never raise.
"""

from __future__ import annotations

import html as _html
import hashlib
import json
import os
import re as _re
import time
import urllib.request
from datetime import datetime

from .tsenta_profiles import profile_get, skills_flat
from .tsenta_bullhorn import bullhorn_fetch_job, bullhorn_job_identity

try:
    from backend.src.tools.tsenta_llm import chat_completion
except ImportError:
    from tsenta_llm import chat_completion

_STATUS_COMPLETED = "COMPLETED"

_STOPWORDS = frozenset(
    "a an and are as at be but by for from has have he her his i in is it its of on "
    "or our that the their them they this to was we were will with you your about "
    "after all also any can did do does each else few for had how if into just like "
    "more most much new no not now only other out over own same she should some "
    "such than then there these those through too under until up very what when "
    "where which while who whom why would yet us our".split())

_JOB_GENERIC = frozenset(
    "ability applicant application business candidate company environment experience "
    "including individual job position preferred provide required requirements role team "
    "work working years opportunity responsibilities skills".split())

# Recovered cover-letter response shape with empty (off) defaults.
_EMPTY_COVER_LETTER = {
    "coverLetterHtml": None,
    "coverLetterText": None,
    "status": _STATUS_COMPLETED,
    "useCoverLetter": False,
    "coverLetterMode": "off",
    "coverLetterMetadata": None,
}

_EMPTY_RESUME = {
    "resumeText": "",
    "status": _STATUS_COMPLETED,
    "useOptimizedResume": False,
    "optimizationMode": "honest",
    "resumeMetadata": None,
}


def _extract_keywords(description, limit: int = 12) -> list:
    """Extract the most distinctive keywords from a job description.

    Args:
        description: job description text (or None).
        limit: max number of keywords to return.

    Returns:
        list[str]: lowercase keywords (4+ chars, stopwords removed) in first
        occurrence order. Never raises.
    """
    keywords = []
    try:
        counts = {}
        first_seen = {}
        for token in _re.findall(r"[a-zA-Z][a-zA-Z0-9+#.\-]{1,}", str(description or "")):
            word = token.rstrip(".,;:!?()[]{}").lower()
            if (not word or len(word) < 3 or word in _STOPWORDS or
                    word in _JOB_GENERIC or word.isdigit()):
                continue
            if word not in first_seen:
                first_seen[word] = len(first_seen)
            counts[word] = counts.get(word, 0) + 1
        ordered = sorted(counts, key=lambda word: (-counts[word], first_seen[word]))
        keywords = ordered[:limit]
    except Exception:
        return []
    return keywords


def _bullet_keyword_score(bullet: str, keywords: list) -> int:
    """Count how many keywords a bullet contains (case-insensitive)."""
    text = bullet.lower()
    return sum(1 for k in keywords if k in text)


def _sort_entries_by_keywords(entries: list, keywords: list) -> list:
    """Prioritize relevant bullets while preserving work-history chronology.

    Args:
        entries: list of (title, company, dates, bullets).
        keywords: extracted job keywords.

    Returns:
        list: same entries in their original order, with up to three bullets
        sorted by keyword score (descending). Never raises.
    """
    ordered_entries = []
    for title, company, dates, bullets in entries:
        ordered = sorted(bullets, key=lambda b: _bullet_keyword_score(b, keywords),
                          reverse=True)
        # Preserve reverse-chronological work history while emphasizing the
        # three most relevant factual bullets inside each role.
        ordered_entries.append((title, company, dates, ordered[:3]))
    return ordered_entries


def _sort_skills_by_keywords(skills: list, keywords: list) -> list:
    """Reorder skills so keyword-matched skills come first."""
    def score(skill: str) -> int:
        value = skill.lower()
        parts = set(_re.findall(r"[a-z0-9+#.\-]+", value))
        return sum(1 for keyword in keywords if keyword in value or keyword in parts)
    return sorted(skills, key=lambda skill: (-score(skill), skill.lower()))


def _work_entries(profile: dict) -> list:
    """Verbatim work experience entries as [title, company, date_range, bullets]."""
    entries = []
    for job in profile.get("workExperience") or []:
        try:
            if not isinstance(job, dict):
                continue
            title = str(job.get("title") or job.get("role") or job.get("jobTitle") or "").strip()
            company = str(job.get("company") or job.get("companyName") or "").strip()
            if not title and not company:
                continue
            started = _format_resume_date(job.get("startDate") or job.get("startedAt") or "")
            ended = _format_resume_date(job.get("endDate") or job.get("endedAt") or "")
            # Resume imports and profile edits do not always persist the
            # explicit current-role checkbox. A dated role with no end date
            # is the same signal used by the ATS field mapper, so render the
            # recruiter-standard range instead of a misleading lone date.
            if job.get("isCurrentRole") or (started and not ended):
                ended = "Present"
            if started and ended:
                dates = f"{started} – {ended}"
            elif started:
                dates = started
            else:
                dates = ""
            location = str(job.get("location") or "").strip()
            if location:
                dates = " | ".join(filter(None, (dates, location)))
            source_bullets = (job.get("bullets") or job.get("responsibilities") or
                              job.get("achievements") or [])
            bullets = [str(b).strip() for b in source_bullets if str(b).strip()]
            entries.append((title, company, dates, bullets))
        except Exception:
            continue
    return entries


def _work_fact_ledger(profile: dict) -> list:
    """Return independent, structured evidence records for each work role."""
    ledger = []
    try:
        for job in profile.get("workExperience") or []:
            if not isinstance(job, dict):
                continue
            title = str(job.get("title") or job.get("role") or
                        job.get("jobTitle") or "").strip()
            company = str(job.get("company") or job.get("companyName") or "").strip()
            if not title and not company:
                continue
            ledger.append({
                "role": title,
                "company": company,
                "dates": [job.get("startDate") or job.get("startedAt") or "",
                          job.get("endDate") or job.get("endedAt") or ""],
                "location": job.get("location") or "",
                "achievements": job.get("responsibilities") or job.get("bullets") or
                job.get("achievements") or [],
            })
    except Exception:
        return []
    return ledger


def _number_tokens(value) -> set[str]:
    """Extract numeric claim tokens from text or JSON-compatible data."""
    try:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return set(_re.findall(r"\d+(?:\.\d+)?", text))
    except Exception:
        return set()


def _target_role_is_referenced(text: str, title: str) -> bool:
    """Return whether a letter meaningfully names the target role.

    Natural prose may say ``cybersecurity programs`` in one sentence and
    ``engineer`` in another instead of repeating the exact posting title.
    Require every meaningful title token, while ignoring punctuation and
    generic connectors, so the quality gate catches genuinely generic letters
    without rejecting fluent targeted writing.
    """
    try:
        body = str(text or "").casefold()
        target = str(title or "").strip().casefold()
        if not target:
            return True
        if target in body:
            return True
        tokens = {
            token for token in _re.findall(r"[a-z0-9+#.-]+", target)
            if len(token) >= 3 and token not in _STOPWORDS and token not in {"role", "position"}
        }
        return bool(tokens) and all(
            _re.search(rf"(?<![a-z0-9]){_re.escape(token)}(?![a-z0-9])", body)
            for token in tokens)
    except Exception:
        return False


def _target_company_is_referenced(text: str, company: str) -> bool:
    """Return whether a letter names the target employer or its brand name."""
    try:
        body = str(text or "").casefold()
        target = str(company or "").strip().casefold()
        if not target:
            return True
        if target in body:
            return True
        generic = {
            "and", "company", "corp", "corporation", "group", "holdings",
            "inc", "information", "llc", "limited", "ltd", "services",
            "solutions", "systems", "technologies", "technology", "the",
        }
        tokens = [
            token for token in _re.findall(r"[a-z0-9]+", target)
            if len(token) >= 3 and token not in generic
        ]
        # The longest remaining token is normally the distinctive employer
        # brand (for example, Apollo in Apollo Information Systems).
        brand = max(tokens, key=len) if tokens else ""
        return bool(brand and _re.search(
            rf"(?<![a-z0-9]){_re.escape(brand)}(?![a-z0-9])", body))
    except Exception:
        return False


def _resume_role_blocks(text: str, profile: dict) -> list[tuple[dict, str]]:
    """Pair rendered resume experience blocks with their source role records."""
    try:
        jobs = [job for job in profile.get("workExperience") or []
                if isinstance(job, dict)]
        if not jobs:
            return []
        lines = str(text or "").splitlines()
        start = next((i + 1 for i, line in enumerate(lines)
                      if line.strip().upper() == "EXPERIENCE"), None)
        if start is None:
            return []
        stop_sections = {"EDUCATION", "PROJECTS", "CERTIFICATIONS",
                         "CUSTOM SECTIONS", "RELEVANT COURSEWORK"}
        end = next((i for i in range(start, len(lines))
                    if lines[i].strip().upper() in stop_sections), len(lines))

        headers = []
        for index in range(start, end):
            line = lines[index].strip()
            if not line or line.startswith("-") or "|" not in line:
                continue
            folded = line.casefold()
            for job in jobs:
                company = str(job.get("company") or job.get("companyName") or "").strip()
                title = str(job.get("title") or job.get("role") or
                            job.get("jobTitle") or "").strip()
                if company and company.casefold() in folded and (
                        not title or title.casefold() in folded):
                    headers.append((index, job))
                    break
        blocks = []
        for position, (index, job) in enumerate(headers):
            block_end = headers[position + 1][0] if position + 1 < len(headers) else end
            blocks.append((job, "\n".join(lines[index:block_end]).strip()))
        return blocks
    except Exception:
        return []


def _employer_scoped_fact_issues(text: str, profile: dict, kind: str,
                                 job_context: dict | None = None) -> list[str]:
    """Find metrics attributed to an employer that are absent from that role.

    Resume experience blocks are checked as a whole. Cover letters are checked
    only when an attribution phrase such as ``at Acme`` or ``with Acme`` makes
    the employer relationship explicit, avoiding false positives for a target
    company mentioned in the opening sentence.
    """
    try:
        profile = profile if isinstance(profile, dict) else {}
        issues = []
        if kind == "resume":
            for job, block in _resume_role_blocks(text, profile):
                unexpected = _number_tokens(block) - _number_tokens(job)
                if unexpected:
                    company = str(job.get("company") or job.get("companyName") or
                                  "this employer").strip()
                    issues.append(
                        f"Metrics under {company} are not present in that role's profile facts: "
                        + ", ".join(sorted(unexpected)))
            return issues

        target_company = str((job_context or {}).get("company") or "").strip().casefold()
        ledger = _work_fact_ledger(profile)
        sentences = [part.strip() for part in _re.split(r"(?<=[.!?])\s+|\n+", str(text or ""))
                     if part.strip()]
        for sentence in sentences:
            attributions = []
            for role in ledger:
                company = str(role.get("company") or "").strip()
                if not company:
                    continue
                escaped = _re.escape(company)
                match = _re.search(
                        rf"(?i)(?:\bat\s+|\bwith\s+|\bfor\s+|\bmy\s+(?:work|role|time)\s+at\s+)"
                        rf"{escaped}(?![\w])", sentence)
                if match:
                    if (company.casefold() == target_company and
                            _re.search(r"(?i)\b(?:applying|interest|position|role)\b", sentence) and
                            not _re.search(r"(?i)\b(?:my work|my role|my time|while)\b", sentence)):
                        continue
                    attributions.append((match.start(), role))
            if not attributions:
                continue
            attributions.sort(key=lambda item: item[0])
            for index, (offset, role) in enumerate(attributions):
                segment_end = (attributions[index + 1][0]
                               if index + 1 < len(attributions) else len(sentence))
                # A number earlier in the sentence (for example "spans 5
                # roles, most recently ... at Acme") is not an Acme metric.
                segment = sentence[offset:segment_end]
                unexpected = _number_tokens(segment) - _number_tokens(role)
                if unexpected:
                    company = str(role.get("company") or "this employer")
                    issues.append(
                        f"Metrics attributed to {company} are not present in those role facts: "
                        + ", ".join(sorted(unexpected)))
        return list(dict.fromkeys(issues))
    except Exception:
        return []


def _format_resume_date(value) -> str:
    """Format ISO-like profile dates as recruiter-friendly month labels."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    for pattern in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(raw, pattern).strftime("%b %Y")
        except ValueError:
            continue
    return raw


def _resume_skill_lines(profile: dict, keywords: list, optimized: bool) -> list:
    """Build categorized skill lines while preserving the original profile style."""
    categories = []
    for index, category in enumerate(profile.get("skillCategories") or []):
        if not isinstance(category, dict):
            continue
        name = str(category.get("name") or "Skills").strip()
        values = []
        for skill in category.get("skills") or []:
            value = (skill.get("name") if isinstance(skill, dict) else skill)
            if str(value or "").strip():
                values.append(str(value).strip())
        if not values:
            continue
        score = sum(_bullet_keyword_score(name + " " + " ".join(values), keywords)
                    for _ in (0,))
        categories.append((score, index, name, values))
    if optimized and keywords:
        categories.sort(key=lambda item: (-item[0], item[1]))
    return [f"{name}: {', '.join(values)}" for _, _, name, values in categories]


def resume_summary_document(profile: dict, config: dict | None = None,
                            job_context: dict | None = None,
                            llm_cfg: dict | None = None,
                            chat: callable | None = None) -> dict:
    """Build the resume text summary from profile facts.

    Honest mode ("honest", default): sections are taken VERBATIM from the
    profile — nothing is invented, nothing is reordered, the LLM is never
    asked to rewrite.

    Optimized mode ("aggressive"): keywords are extracted from the job
    description (job_context["description"]), work bullets and experience
    entries are reordered to prioritize keyword matches, skills are reordered
    with matched skills first, and the LLM may rewrite the assembled text
    under a strict no-invention guard. matchPercentage + matchedKeywords land
    in resumeMetadata.

    Args:
        profile: candidate profile dict.
        config: apply config dict (uses optimizationMode; defaults).
        job_context: optional {"company", "title", "description"}.
        llm_cfg: llm_config() dict; None uses the environment.
        chat: injectable transport callable(messages) -> str (tests).

    Returns:
        dict: {"resumeText", "status", "useOptimizedResume",
        "optimizationMode", "resumeMetadata"} — mirrors the recovered shape.
        Never raises.
    """
    try:
        profile = profile if isinstance(profile, dict) else {}
        mode = "honest"
        if isinstance(config, dict):
            mode = str(config.get("optimizationMode") or "honest")
        context = job_context if isinstance(job_context, dict) else {}
        description = str(context.get("description") or "").strip()

        info = profile.get("personalInformation") or {}
        lines = []
        name = " ".join(p for p in (info.get("firstName"), info.get("lastName")) if p)
        title = str(info.get("title") or "").strip()
        if name:
            lines.append(name)
        if title:
            lines.append(title)
        location = ", ".join(str(p).strip() for p in
                             (info.get("city"), info.get("state")) if str(p or "").strip())
        contact = " | ".join(p for p in (
            info.get("email"), info.get("phone"), location,
            info.get("linkedinUrl"), info.get("githubUrl"),
            info.get("website")) if p)
        if contact:
            lines.append(contact)
        summary = str(info.get("summary") or "").strip()
        if summary:
            lines += ["", "SUMMARY", summary]

        keywords = _extract_keywords(description)
        use_requested = bool(config.get("useOptimizedResume", True)) if isinstance(config, dict) else True
        optimization_active = use_requested and (mode == "aggressive" or bool(keywords))
        entries = _work_entries(profile)
        if optimization_active and keywords:
            entries = _sort_entries_by_keywords(entries, keywords)

        skill_lines = _resume_skill_lines(profile, keywords, optimization_active)
        if skill_lines:
            lines += ["", "SKILLS"] + skill_lines
        else:
            skills = skills_flat(profile)
            if optimization_active and keywords and skills:
                skills = ", ".join(_sort_skills_by_keywords(
                    skills.split(", "), keywords)[:24])
            if skills:
                lines += ["", "SKILLS", skills]

        if entries:
            lines += ["", "EXPERIENCE"]
        for title_, company, dates, bullets in entries:
            header = " | ".join(p for p in (title_, company, dates) if p)
            lines.append(header)
            lines += [f"- {b}" for b in bullets]
        education_lines = []
        for edu in profile.get("education") or []:
            if not isinstance(edu, dict):
                continue
            school = str(edu.get("school") or edu.get("university") or
                         edu.get("institution") or "").strip()
            degree = str(edu.get("degree") or edu.get("degreeName") or "").strip()
            if not school and not degree:
                continue
            minor = str(edu.get("minor") or "").strip()
            if minor and degree:
                degree = f"{degree} (Minor: {minor})"
            end_date = _format_resume_date(edu.get("endDate") or "")
            location = str(edu.get("location") or "").strip()
            education_lines.append(" | ".join(
                p for p in (degree, school, end_date, location) if p))
        if education_lines:
            lines += ["", "EDUCATION"] + education_lines
        project_lines = []
        for proj in profile.get("projects") or []:
            if not isinstance(proj, dict):
                continue
            pname = str(proj.get("name") or "").strip()
            desc = str(proj.get("description") or "").strip()
            if not pname and not desc:
                continue
            project_lines.append(" | ".join(p for p in (pname, desc) if p))
        if project_lines:
            lines += ["", "PROJECTS"] + project_lines
        certification_lines = []
        for cert in profile.get("certifications") or []:
            if not isinstance(cert, dict):
                continue
            cname = str(cert.get("name") or "").strip()
            if cname:
                certification_lines.append(cname)
        if certification_lines:
            lines += ["", "CERTIFICATIONS"] + certification_lines

        text = "\n".join(lines).strip()
        metadata = None
        if optimization_active and keywords:
            matched = [k for k in keywords if k in text.lower()]
            metadata = {
                "matchedKeywords": matched,
                "matchPercentage": round(len(matched) / len(keywords) * 100)
                if keywords else 0,
                "targetCompany": str(context.get("company") or ""),
                "targetTitle": str(context.get("title") or ""),
            }
        if optimization_active and keywords:
            base_text = text
            text = _llm_rewrite_resume(
                text, profile, keywords, llm_cfg, chat, job_context=context)
            if metadata is not None:
                metadata["generator"] = "llm" if text != base_text else "deterministic-fallback"
        return {"resumeText": text,
                "status": _STATUS_COMPLETED,
                "useOptimizedResume": optimization_active,
                "optimizationMode": mode,
                "resumeMetadata": metadata}
    except Exception:
        return dict(_EMPTY_RESUME)


def _llm_rewrite_resume(text: str, profile: dict, keywords: list,
                        llm_cfg: dict | None, chat: callable | None,
                        job_context: dict | None = None) -> str:
    """Tailor only the professional summary with the LLM; original on failure.

    The deterministic renderer retains contact data, categorized skills, work
    chronology, bullets, education, and certifications. Restricting the model
    to the summary prevents layout drift and accidental factual omissions.
    """
    if not text:
        return text
    if llm_cfg is None:
        try:
            from backend.src.tools.tsenta_llm import llm_config
        except ImportError:
            from tsenta_llm import llm_config
        llm_cfg = llm_config()
    if not llm_cfg.get("api_key") and llm_cfg.get('transport') != 'chatgpt' and chat is None:
        return text
    base_summary = _re.search(
        r"(?ims)^SUMMARY\s*\n(.*?)(?=^SKILLS\s*$)", text)
    if not base_summary:
        return text
    prompt = (
        "Return only a polished 3-4 sentence PROFESSIONAL SUMMARY with no "
        "heading, analysis, bullets, or Markdown. Tailor it to the target role. "
        "STRICT RULES: "
        "use ONLY the facts already present in the resume below; invent "
        "NOTHING; preserve years of experience and factual tools; emphasize "
        "the target role's most important requirements using concrete evidence "
        "from the candidate's actual experience; keep it between "
        "75 and 115 words.\n"
        + (f"Target role: {str((job_context or {}).get('title') or '').strip()} at "
           f"{str((job_context or {}).get('company') or '').strip()}\n"
           if (job_context or {}).get("title") or (job_context or {}).get("company") else "")
        + (f"Job keywords to emphasize when already present: {', '.join(keywords)}\n"
           if keywords else "")
        + f"\nResume:\n{text}"
    )
    messages = [{"role": "user", "content": prompt}]
    # The configured reasoning model occasionally spends the entire first
    # output budget in reasoning_content and returns empty content. Retry once
    # with a larger budget rather than silently claiming an LLM-generated PDF.
    budgets = (4000, 6000) if chat is None else (4000,)
    for budget in budgets:
        try:
            resume_cfg = dict(llm_cfg or {})
            resume_cfg["max_tokens"] = max(int(resume_cfg.get("max_tokens") or 0), budget)
            resume_cfg["temperature"] = min(float(resume_cfg.get("temperature", 0.2)), 0.2)
            rewritten = chat_completion(messages, resume_cfg) if chat is None else chat(messages)
        except Exception:
            rewritten = ""
        rewritten = str(rewritten or "").strip()
        rewritten = _re.sub(r"(?m)^\s*#{1,6}\s*", "", rewritten)
        rewritten = _re.sub(r"\*\*(.*?)\*\*", r"\1", rewritten)
        rewritten = rewritten.replace("�", "-")
        full_resume = _re.search(
            r"(?ims)^SUMMARY\s*\n(.*?)(?=^SKILLS\s*$)", rewritten)
        if full_resume:
            rewritten = full_resume.group(1).strip()
        rewritten = _re.sub(r"(?i)^professional summary\s*:?\s*", "", rewritten).strip()
        word_count = len(rewritten.split())
        if 60 <= word_count <= 140:
            return text[:base_summary.start(1)] + rewritten + "\n\n" + text[base_summary.end(1):].lstrip()
    return text


def _cover_letter_template(profile: dict, job_context: dict | None) -> str:
    """Honest cover letter assembled from profile facts + job context."""
    info = profile.get("personalInformation") or {}
    name = " ".join(p for p in (info.get("firstName"), info.get("lastName")) if p)
    context = job_context if isinstance(job_context, dict) else {}
    company = str(context.get("company") or "").strip().rstrip(" .")
    title = str(context.get("title") or "").strip()
    custom = str(profile.get("coverLetterText") or "").strip()
    if len(custom) >= 40:
        # A reusable candidate-authored letter is a first-class Tsenta-style
        # profile asset. Only substitute explicit placeholders; the text is
        # otherwise preserved verbatim so Nori never invents content.
        replacements = {
            "{{company}}": company,
            "{{role}}": title,
            "[Company]": company,
            "[Role]": title,
        }
        for token, value in replacements.items():
            custom = custom.replace(token, value)
        return custom
    summary = str(info.get("summary") or "").strip()
    skills = skills_flat(profile)
    if skills and context.get("description"):
        skills = ", ".join(_sort_skills_by_keywords(
            skills.split(", "), _extract_keywords(context.get("description")))[:12])
    entries = _work_entries(profile)
    latest = entries[0] if entries else None
    keywords = _extract_keywords(str(context.get('description') or '') + ' ' + title)
    evidence = sorted(((company_, bullet) for _, company_, _, bullets in entries for bullet in bullets),
                      key=lambda row: _bullet_keyword_score(row[1], keywords), reverse=True)[:2]

    greeting = "Dear Hiring Team,"
    if company and title:
        target = f"the {title} role at {company}"
    elif title:
        target = f"the {title} role"
    elif company:
        target = f"{company}"
    else:
        target = ""

    para1 = (f"I am writing to express my interest in {target}." if target else
             "I am writing to express my interest in this role.")
    if latest:
        para1 += (f" My professional experience spans {len(entries)} roles, most recently "
                  f"as {latest[0] or 'a team member'} at {latest[1] or 'my previous employer'}.")
    para2 = ""
    if summary:
        para2 += f"{summary.strip()}"
    if skills:
        para2 += (f" My relevant experience spans {skills}." if not para2 else
                  f" My experience spans {skills}.")
    if para2:
        para2 += (" I believe my background aligns well with the requirements of "
                  "this position.")
    else:
        para2 = "I believe my background aligns well with the requirements of this position."
    if evidence:
        para2 = '\n\n'.join(f'At {employer}, my work included the following: {bullet}'
                            for employer, bullet in evidence)
    para3 = ("I would welcome the opportunity to discuss how I can contribute to "
             "the team. Thank you for your time and consideration.")
    closing = f"Sincerely,\n{name}" if name else "Sincerely,"
    return "\n\n".join(p for p in (greeting, para1, para2, para3, closing) if p)


def cover_letter_document(profile: dict, config: dict | None = None,
                          job_context: dict | None = None,
                          llm_cfg: dict | None = None,
                          chat: callable | None = None) -> dict:
    """Generate the cover letter (honest | generated; "off" = empty shape).

    Honest mode: template assembled strictly from profile facts + optional
    job context ({company, title, description}). When an LLM key is configured
    and a chat callable is available, the letter may be rephrased — but only
    from the facts already present; the prompt forbids invention.

    Generated mode: the LLM writes a full job-specific letter from profile
    facts + job context under a strict no-invention guard; falls back to the
    honest template when no LLM is available or the model refuses (guard:
    output shorter than 50 chars is discarded).

    Args:
        profile: candidate profile dict.
        config: apply config dict (coverLetterMode, autoApproveCoverLetter).
        job_context: optional {"company", "title", "description"}.
        llm_cfg: llm_config() dict; None uses the environment.
        chat: injectable transport callable(messages) -> str (tests).

    Returns:
        dict: {"coverLetterHtml", "coverLetterText", "status", "useCoverLetter",
        "coverLetterMode", "coverLetterMetadata"} — recovered shape. Never raises.
    """
    try:
        profile = profile if isinstance(profile, dict) else {}
        config = config if isinstance(config, dict) else {}
        mode = str(config.get("coverLetterMode") or "honest")
        if mode == "off":
            return dict(_EMPTY_COVER_LETTER)
        auto_approve = bool(config.get("autoApproveCoverLetter", True))
        generator = 'template'
        if mode in ("generated", "llm"):
            text = _llm_generate_letter(profile, job_context, llm_cfg, chat)
            generator = 'llm' if text else 'deterministic-fallback'
            if not text:
                text = _cover_letter_template(profile, job_context)
        else:
            text = _cover_letter_template(profile, job_context)
            if chat is not None:
                try:
                    text = _llm_rephrase(text, profile, llm_cfg, chat)
                except Exception:
                    pass
        html = _html.escape(text).replace("\n", "<br>")
        return {"coverLetterHtml": html,
                "coverLetterText": text,
                "status": _STATUS_COMPLETED,
                "useCoverLetter": bool(auto_approve),
                "coverLetterMode": mode,
                "coverLetterMetadata": {'generator': generator}}
    except Exception:
        return dict(_EMPTY_COVER_LETTER)


def _llm_generate_letter(profile: dict, job_context: dict | None,
                         llm_cfg: dict | None, chat: callable | None) -> str:
    """Generate a full job-specific cover letter via the LLM; "" on failure.

    STRICT no-invention rules: the prompt lists the ONLY facts the model may
    use (name, summary, skills, work history); output shorter than 50 chars is
    discarded (guard against refusal).
    """
    if llm_cfg is None:
        try:
            from backend.src.tools.tsenta_llm import llm_config
        except ImportError:
            from tsenta_llm import llm_config
        llm_cfg = llm_config()
    if not llm_cfg.get("api_key") and llm_cfg.get('transport') != 'chatgpt' and chat is None:
        return ""
    context = job_context if isinstance(job_context, dict) else {}
    company = str(context.get("company") or "").strip()
    title = str(context.get("title") or "").strip()
    description = str(context.get("description") or "").strip()
    info = profile.get("personalInformation") or {}
    name = " ".join(p for p in (info.get("firstName"), info.get("lastName")) if p)
    facts = {
        "name": name,
        "title": info.get("title") or "",
        "summary": info.get("summary") or "",
        "skills": skills_flat(profile),
    }
    jobs = [json.dumps(role, ensure_ascii=False)
            for role in _work_fact_ledger(profile)[:4]]
    prompt = (
        f"Write a professional cover letter for the {title or 'open'} role"
        f" at {company or 'the company'}"
        + (f". Job description: {description[:8000]}" if description else "")
        + ".\nSTRICT RULES: use ONLY the facts listed below; invent NOTHING "
        "(no new employers, titles, dates, degrees, skills or achievements); "
        "treat every work-history record as an independent evidence boundary: "
        "NEVER move a metric, tool, responsibility, or achievement from one "
        "employer to another; "
        "keep it under 250 words; open with the strongest relevant achievement, "
        "connect two concrete examples to this posting's requirements, avoid generic enthusiasm "
        "and keyword lists; address it to the hiring team; sign with "
        f"the candidate's name.\n\nFacts: {facts}"
        + (f"\nWork history: {', '.join(jobs)}" if jobs else "")
    )
    messages = [{"role": "user", "content": prompt}]
    try:
        letter_cfg = {**llm_cfg, 'max_tokens': max(int(llm_cfg.get('max_tokens') or 0), 2000)}
        content = chat_completion(messages, letter_cfg) if chat is None else chat(messages)
    except Exception:
        return ""
    content = str(content or "").strip()
    return content if len(content) > 50 else ""


def _llm_rephrase(text: str, profile: dict, llm_cfg: dict | None,
                  chat: callable | None) -> str:
    """Rephrase the honest letter with the LLM; returns the original on failure."""
    if llm_cfg is None:
        try:
            from backend.src.tools.tsenta_llm import llm_config
        except ImportError:
            from tsenta_llm import llm_config
        llm_cfg = llm_config()
    if not llm_cfg.get("api_key") and llm_cfg.get('transport') != 'chatgpt' and chat is None:
        return text
    facts = {
        "name": profile_get(profile, "personalInformation.firstName"),
        "summary": profile_get(profile, "personalInformation.summary"),
        "skills": skills_flat(profile),
        "workHistory": _work_fact_ledger(profile),
    }
    prompt = (
        "Rewrite the following cover letter. STRICT RULES: use ONLY the facts "
        "listed below or already in the letter; invent NOTHING; keep each "
        "achievement and metric attached to its original employer; keep it "
        "professional, concise and under 250 words.\n\n"
        f"Facts: {facts}\n\nLetter:\n{text}"
    )
    messages = [{"role": "user", "content": prompt}]
    letter_cfg = {**llm_cfg, 'max_tokens': max(int(llm_cfg.get('max_tokens') or 0), 1200)}
    rewritten = chat_completion(messages, letter_cfg) if chat is None else chat(messages)
    rewritten = str(rewritten or "").strip()
    return rewritten if len(rewritten) > 50 else text


def _clean_markup(value: str, limit: int = 40000) -> str:
    """Convert a bounded HTML fragment to readable plain text."""
    value = _re.sub(r"(?is)<(script|style|svg)\b.*?</\1>", " ", str(value or ""))
    value = _re.sub(r"(?i)<br\s*/?>|</(?:p|div|li|h[1-6])>", "\n", value)
    value = _re.sub(r"(?s)<[^>]+>", " ", value)
    value = _html.unescape(value).replace("\xa0", " ")
    value = _re.sub(r"[ \t]+", " ", value)
    value = _re.sub(r"\n\s*\n+", "\n", value)
    return value.strip()[:limit]


def _job_posting_objects(value) -> list:
    """Recursively find JobPosting objects in parsed JSON-LD."""
    found = []
    if isinstance(value, list):
        for item in value:
            found.extend(_job_posting_objects(item))
    elif isinstance(value, dict):
        kind = value.get("@type")
        if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
            found.append(value)
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in value:
                found.extend(_job_posting_objects(value[key]))
    return found


def fetch_job_context(url: str, timeout: int = 20) -> dict:
    """Fetch a job page and extract title, company, location, and description.

    JSON-LD JobPosting data is preferred. OpenGraph/title patterns and readable
    page text provide deterministic fallbacks for Greenhouse and other public
    ATS pages. This function performs no browser interaction and never submits
    or changes an application.

    Args:
        url: Public job posting or application URL.
        timeout: Network timeout in seconds.

    Returns:
        dict: ``{"title", "company", "location", "description", "source"}``.
        Values are empty when extraction fails; exceptions are handled.
    """
    empty = {"title": "", "company": "", "location": "",
             "description": "", "source": ""}
    try:
        if bullhorn_job_identity(url).get("ok"):
            fetched = bullhorn_fetch_job(url, timeout_s=timeout)
            job = fetched.get("job") if isinstance(fetched, dict) else {}
            if fetched.get("ok") and isinstance(job, dict):
                address = job.get("address") if isinstance(job.get("address"), dict) else {}
                location = ", ".join(
                    str(address.get(key) or "").strip()
                    for key in ("city", "state", "countryName")
                    if str(address.get(key) or "").strip()
                )
                return {
                    "title": _clean_markup(job.get("title") or "", 500),
                    "company": "",
                    "location": location[:500],
                    "description": _clean_markup(job.get("publicDescription") or ""),
                    "source": "bullhorn-public-rest",
                }
        request = urllib.request.Request(
            str(url or ""),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 Chrome/126 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urllib.request.urlopen(request, timeout=max(1, int(timeout))) as response:
            raw = response.read(2_000_000)
            charset = response.headers.get_content_charset() or "utf-8"
        markup = raw.decode(charset, errors="replace")
        result = dict(empty)
        for match in _re.finditer(
                r"(?is)<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
                markup):
            try:
                postings = _job_posting_objects(json.loads(_html.unescape(match.group(1))))
            except Exception:
                postings = []
            if not postings:
                continue
            posting = postings[0]
            organization = posting.get("hiringOrganization") or {}
            location = posting.get("jobLocation") or {}
            if isinstance(location, list):
                location = location[0] if location else {}
            address = location.get("address") or {} if isinstance(location, dict) else {}
            country = address.get("addressCountry") if isinstance(address, dict) else ""
            if isinstance(country, dict):
                country = country.get("name") or country.get("value") or ""
            location_text = ", ".join(str(address.get(key) or "").strip() for key in
                                      ("addressLocality", "addressRegion")
                                      if str(address.get(key) or "").strip())
            if country:
                location_text = ", ".join(filter(None, (location_text, str(country).strip())))
            result = {
                "title": _clean_markup(posting.get("title") or "", 500),
                "company": _clean_markup(organization.get("name") or "", 500)
                if isinstance(organization, dict) else "",
                "location": location_text[:500],
                "description": _clean_markup(posting.get("description") or ""),
                "source": "json-ld",
            }
            break

        meta = _re.search(
            r"(?is)<meta[^>]+(?:property|name)=[\"']og:title[\"'][^>]+content=[\"'](.*?)[\"']",
            markup)
        if not meta:
            meta = _re.search(
                r"(?is)<meta[^>]+content=[\"'](.*?)[\"'][^>]+(?:property|name)=[\"']og:title[\"']",
                markup)
        page_title = _re.search(r"(?is)<title\b[^>]*>(.*?)</title>", markup)
        raw_title = _html.unescape(meta.group(1)).strip() if meta else ""
        full_title = _clean_markup(page_title.group(1) if page_title else "", 1000)
        for candidate in (full_title, raw_title):
            pattern = _re.match(
                r"(?is)Job Application for\s+(.+?)\s+at\s+(.+?)(?:\s*\||$)", candidate)
            if pattern:
                result["title"] = result["title"] or pattern.group(1).strip()
                result["company"] = result["company"] or pattern.group(2).strip()
                break
        if not result["title"]:
            h1 = _re.search(r"(?is)<h1\b[^>]*>(.*?)</h1>", markup)
            result["title"] = _clean_markup(
                h1.group(1) if h1 else (raw_title or (page_title.group(1) if page_title else "")), 500)
        if not result["location"]:
            location_meta = _re.search(
                r"(?is)<meta[^>]+(?:property|name)=[\"']og:description[\"'][^>]+content=[\"'](.*?)[\"']",
                markup)
            if not location_meta:
                location_meta = _re.search(
                    r"(?is)<meta[^>]+content=[\"'](.*?)[\"'][^>]+(?:property|name)=[\"']og:description[\"']",
                    markup)
            if location_meta:
                result["location"] = _clean_markup(location_meta.group(1), 500)
        if not result["location"]:
            location_match = _re.search(
                r"(?is)<[^>]+class=[\"'][^\"']*location[^\"']*[\"'][^>]*>(.*?)</[^>]+>",
                markup)
            if location_match:
                result["location"] = _clean_markup(location_match.group(1), 500)
        if not result["description"]:
            result["description"] = _clean_markup(markup)
        result["source"] = result["source"] or "html"
        return result
    except Exception:
        return empty


def _contact_html(value: str) -> str:
    """Render contact text with compact labels for LinkedIn and GitHub URLs."""
    parts = [part.strip() for part in str(value or "").split("|") if part.strip()]
    rendered = []
    for part in parts:
        escaped = _html.escape(part)
        if "linkedin.com/" in part.lower():
            rendered.append(f"<a href='{escaped}'>LinkedIn</a>")
        elif "github.com/" in part.lower():
            rendered.append(f"<a href='{escaped}'>GitHub</a>")
        elif part.lower().startswith(("http://", "https://")):
            rendered.append(f"<a href='{escaped}'>Portfolio</a>")
        else:
            rendered.append(escaped)
    return "<span class='sep'>|</span>".join(rendered)


def _document_html(text: str, title: str, kind: str, compact: bool = False) -> str:
    """Render structured document text as polished, ATS-safe print HTML."""
    heading = _html.escape(title or ("Tailored Resume" if kind == "resume" else "Cover Letter"))
    if kind != "resume":
        paragraphs = [p.strip() for p in _re.split(r"\n\s*\n", str(text or "")) if p.strip()]
        body = "".join(f"<p>{_html.escape(p).replace(chr(10), '<br>')}</p>" for p in paragraphs)
        return f"""<!doctype html><html><head><meta charset='utf-8'><title>{heading}</title>
<style>
@page {{ size: Letter; margin: 0.85in 0.9in; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: 10.5pt; line-height: 1.6; color: #1e293b; margin: 0; }}
p {{ margin: 0 0 16px; text-align: justify; }}
</style>
</head><body>{body}</body></html>"""

    lines = [line.strip() for line in str(text or "").splitlines()]
    section_names = {"SUMMARY", "SKILLS", "EXPERIENCE", "EDUCATION", "PROJECTS",
                     "CERTIFICATIONS"}
    first_section = next((i for i, value in enumerate(lines) if value in section_names), len(lines))
    header = [line for line in lines[:first_section] if line]
    name = header[0] if header else "Candidate"
    contact = next((line for line in header[1:] if "@" in line or "http" in line or " | " in line), "")
    body = [f"<header><h1>{_html.escape(name)}</h1><div class='contact'>{_contact_html(contact)}</div></header>"]
    section = ""
    labels = {"SUMMARY": "PROFESSIONAL SUMMARY"}
    for line in lines[first_section:]:
        if not line:
            continue
        if line in section_names:
            section = line
            body.append(f"<h2>{labels.get(line, line)}</h2>")
            continue
        if line.startswith(("- ", "• ", "* ")):
            clean_b = line[2:].strip()
            body.append(f"<div class='bullet'><span class='bullet-marker'>•</span><span>{_html.escape(clean_b)}</span></div>")
            continue
        if section == "SKILLS" and ":" in line:
            label, values = line.split(":", 1)
            body.append(f"<div class='skill'><strong>{_html.escape(label)}:</strong>{_html.escape(values)}</div>")
            continue
        if section == "EXPERIENCE" and " | " in line:
            parts = [part.strip() for part in line.split(" | ")]
            if len(parts) >= 3:
                role = parts[0] if parts else ""
                company = parts[1] if len(parts) > 1 else ""
                dates = parts[2] if len(parts) > 2 else ""
                location = parts[3] if len(parts) > 3 else ""
                body.append(
                    "<div class='entry'><div><strong>" + _html.escape(company) +
                    "</strong>, " + _html.escape(role) + "</div><div class='entry-meta'><strong>" +
                    _html.escape(dates) + "</strong>" +
                    (" <span>|</span> " + _html.escape(location) if location else "") + "</div></div>")
            elif len(parts) == 2:
                body.append(
                    "<div class='entry'><div><strong>" + _html.escape(parts[0]) +
                    "</strong></div><div class='entry-meta'>" + _html.escape(parts[1]) + "</div></div>")
            continue
        if section == "EDUCATION" and " | " in line:
            parts = [part.strip() for part in line.split(" | ")]
            degree = parts[0] if parts else ""
            school = parts[1] if len(parts) > 1 else ""
            dates = parts[2] if len(parts) > 2 else ""
            location = parts[3] if len(parts) > 3 else ""
            body.append(
                "<div class='entry education'><div><strong>" + _html.escape(school) +
                "</strong>, " + _html.escape(degree) + "</div><div class='entry-meta'><strong>" +
                _html.escape(dates) + "</strong>" +
                (" <span>|</span> " + _html.escape(location) if location else "") + "</div></div>")
            continue
        if section == "CERTIFICATIONS":
            body.append(f"<span class='cert'>• {_html.escape(line)}</span>")
            continue
        css_class = "summary" if section == "SUMMARY" else "plain"
        body.append(f"<p class='{css_class}'>{_html.escape(line)}</p>")

    font_size = "8.25pt" if compact else "8.85pt"
    line_height = "1.28" if compact else "1.34"
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{heading}</title>
<style>
@page {{ size: Letter; margin: 0.44in 0.52in 0.4in 0.52in; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; color: #1e293b; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: {font_size}; line-height: {line_height}; }}
header {{ text-align: center; margin-bottom: 9px; padding-bottom: 5px; border-bottom: 1.5px solid #cbd5e1; }}
h1 {{ margin: 0 0 4px; font-size: 19pt; font-weight: 700; color: #0f172a; letter-spacing: -0.015em; }}
.contact {{ font-size: 8.8pt; color: #475569; }}
.contact a {{ color: #0284c7; text-decoration: none; font-weight: 500; }}
.sep {{ margin: 0 7px; color: #cbd5e1; }}
h2 {{ margin: 9px 0 4px; padding-bottom: 2px; border-bottom: 1.5px solid #0f172a; color: #0f172a; font-size: 9.8pt; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; }}
p {{ margin: 0; }}
.summary {{ text-align: justify; margin-bottom: 3px; line-height: 1.36; color: #334155; }}
.skill {{ margin: 2px 0; line-height: 1.32; font-size: 8.8pt; color: #334155; }}
.skill strong {{ color: #0f172a; font-weight: 600; margin-right: 4px; }}
.entry {{ display: flex; justify-content: space-between; align-items: baseline; margin: 5px 0 2px; font-size: 9pt; }}
.entry strong {{ color: #0f172a; font-weight: 600; }}
.entry-meta {{ flex: none; white-space: nowrap; color: #475569; font-size: 8.8pt; }}
.entry-meta strong {{ color: #334155; }}
.entry-meta span {{ margin: 0 4px; color: #cbd5e1; }}
.bullet {{ display: flex; align-items: flex-start; margin: 2px 0 2px 4px; text-align: left; font-size: 8.8pt; line-height: 1.34; color: #334155; }}
.bullet-marker {{ flex: none; margin-right: 6px; color: #64748b; }}
.education {{ margin-top: 4px; }}
.cert {{ display: inline-block; width: 33.1%; color: #0284c7; font-size: 8.8pt; }}
</style></head><body>{''.join(body)}</body></html>"""


def render_document_pdf(text: str, output_path: str, title: str = "",
                        kind: str = "resume") -> dict:
    """Render generated document text to a real, text-searchable PDF.

    Args:
        text: Resume or cover-letter text to render.
        output_path: Destination PDF path; its parent is created when needed.
        title: Optional PDF/page title.
        kind: ``"resume"`` or ``"cover_letter"`` for layout selection.

    Returns:
        dict: ``{"ok", "path", "fileName", "byteSize", "sha256", "error"}``.
        ``ok`` is true only after a valid non-empty ``%PDF`` file is verified.
        Exceptions are caught and returned in ``error``.
    """
    result = {"ok": False, "path": "", "fileName": "", "byteSize": 0,
              "sha256": "", "error": ""}
    try:
        if not str(text or "").strip():
            result["error"] = "empty-document"
            return result
        path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content(_document_html(text, title, kind), wait_until="load")
                page.pdf(path=path, format="Letter", print_background=True,
                         prefer_css_page_size=True)
                if kind == "resume":
                    try:
                        from pypdf import PdfReader
                        if len(PdfReader(path).pages) > 1:
                            page.set_content(_document_html(text, title, kind, compact=True),
                                             wait_until="load")
                            page.pdf(path=path, format="Letter", print_background=True,
                                     prefer_css_page_size=True)
                    except Exception:
                        pass
            finally:
                browser.close()
        with open(path, "rb") as handle:
            payload = handle.read()
        if not payload.startswith(b"%PDF") or len(payload) < 1000:
            result["error"] = "invalid-pdf"
            return result
        try:
            from pypdf import PdfReader
            page_count = len(PdfReader(path).pages)
        except Exception:
            page_count = 0
        result.update({"ok": True, "path": path, "fileName": os.path.basename(path),
                       "byteSize": len(payload),
                       "sha256": hashlib.sha256(payload).hexdigest(),
                       "pageCount": page_count})
        return result
    except Exception as exc:
        result["error"] = str(exc) or "pdf-render-failed"
        return result


def _filename_component(value: str, fallback: str) -> str:
    """Convert human-facing document text to a safe filename component."""
    value = _re.sub(r"[^A-Za-z0-9]+", "_", str(value or "")).strip("_")
    return (value or fallback)[:80]


def materialize_documents(documents: dict, application_id: str, output_dir: str,
                          renderer: callable | None = None) -> dict:
    """Create application-specific PDF artifacts and attach verified metadata.

    Args:
        documents: Output from :func:`documents_for_application`.
        application_id: Local application identifier used in PDF metadata.
        output_dir: Per-application directory under ``loot/``.
        renderer: Optional injectable PDF renderer for tests. It must accept
            ``(text, output_path, title, kind)`` and return render metadata.

    Returns:
        dict: A copy of ``documents`` whose resume and cover-letter records
        include ``pdfPath``, ``fileName``, ``byteSize``, ``sha256``,
        ``pdfGenerated``, ``attachmentReady``, and optional ``artifactError``.
        Exceptions are contained and the original document text is preserved.
    """
    rendered = {
        "resume": dict((documents or {}).get("resume") or {}),
        "coverLetter": dict((documents or {}).get("coverLetter") or {}),
    }
    render = renderer or render_document_pdf
    try:
        os.makedirs(output_dir, exist_ok=True)
        resume_text = str(rendered["resume"].get("resumeText") or "")
        candidate_name = next((line.strip() for line in resume_text.splitlines()
                               if line.strip()), "Candidate")
        metadata = rendered["resume"].get("resumeMetadata") or {}
        target_title = str(metadata.get("targetTitle") or "Targeted Role").strip()
        name_part = _filename_component(candidate_name, "Candidate")
        role_part = _filename_component(target_title, "Targeted_Role")
        resume_filename = f"{name_part}_{role_part}_Resume.pdf"
        cover_filename = f"{name_part}_{role_part}_Cover_Letter.pdf"
        targets = [
            ("resume", "resumeText", resume_filename, "resume",
             f"{candidate_name} - {target_title} Resume"),
            ("coverLetter", "coverLetterText", cover_filename, "cover_letter",
             f"{candidate_name} - {target_title} Cover Letter"),
        ]
        for key, text_key, filename, kind, document_title in targets:
            document = rendered[key]
            should_render = bool(document.get(text_key))
            if key == "resume":
                should_render = should_render and bool(document.get("useOptimizedResume"))
            else:
                should_render = should_render and bool(document.get("useCoverLetter"))
            if not should_render:
                document.update({"pdfGenerated": False, "attachmentReady": False})
                continue
            meta = render(document[text_key], os.path.join(output_dir, filename),
                          document_title, kind)
            document.update({
                "pdfGenerated": bool(meta.get("ok")),
                "attachmentReady": bool(meta.get("ok")),
                "pdfPath": meta.get("path") or "",
                "fileName": meta.get("fileName") or filename,
                "byteSize": int(meta.get("byteSize") or 0),
                "sha256": meta.get("sha256") or "",
                "pageCount": int(meta.get("pageCount") or 0),
                "generatedAt": int(time.time() * 1000) if meta.get("ok") else None,
            })
            if meta.get("error"):
                document["artifactError"] = meta["error"]
        return rendered
    except Exception as exc:
        rendered["resume"]["artifactError"] = str(exc) or "materialize-failed"
        rendered["coverLetter"]["artifactError"] = str(exc) or "materialize-failed"
        return rendered


def documents_for_application(profile: dict, config: dict | None = None,
                              job_context: dict | None = None,
                              llm_cfg: dict | None = None,
                              chat: callable | None = None) -> dict:
    """Generate both documents for one application, honoring the config gates.

    Args:
        profile: candidate profile dict.
        config: apply config dict (optimizationMode, coverLetterMode,
            autoApproveResume, autoApproveCoverLetter).
        job_context: optional {"company", "title", "description"} — used for
            keyword optimization (resume) and letter targeting (cover letter).
        llm_cfg: llm_config() dict; None uses the environment.
        chat: injectable transport callable(messages) -> str (tests).

    Returns:
        dict: {"resume": {...}, "coverLetter": {...}} — recovered shapes.
        Never raises.
    """
    try:
        config = config if isinstance(config, dict) else {}
        resume = resume_summary_document(profile, config, job_context, llm_cfg, chat)
        cover = cover_letter_document(profile, config, job_context, llm_cfg, chat)
        facts = json.dumps(profile, ensure_ascii=False)
        name = ' '.join(str((profile.get('personalInformation') or {}).get(k) or '') for k in ('firstName', 'lastName')).strip()
        context = job_context if isinstance(job_context, dict) else {}
        target_company = str(context.get('company') or '').strip()
        target_title = str(context.get('title') or '').strip()
        known_numbers = (_number_tokens(facts) | _number_tokens(target_company) |
                         _number_tokens(target_title))
        # The deterministic letter may state the number of supplied roles;
        # this value is derived exactly from the profile rather than invented.
        known_numbers.add(str(len(profile.get('workExperience') or [])))

        # A model output that crosses an employer boundary is discarded before
        # any PDF can be produced or any application can consume the letter.
        cover_text = str(cover.get('coverLetterText') or '')
        cover_scope_issues = _employer_scoped_fact_issues(
            cover_text, profile, 'cover_letter', context)
        cover_metadata = cover.get('coverLetterMetadata') or {}
        if cover_scope_issues and cover_metadata.get('generator') == 'llm':
            safe_text = _cover_letter_template(profile, context)
            cover['coverLetterText'] = safe_text
            cover['coverLetterHtml'] = _html.escape(safe_text).replace("\n", "<br>")
            cover_metadata = dict(cover_metadata)
            cover_metadata.update({
                'generator': 'deterministic-safety-fallback',
                'safetyFallback': True,
                'rejectedIssues': cover_scope_issues,
            })
            cover['coverLetterMetadata'] = cover_metadata
        for document, text_key in ((resume, 'resumeText'), (cover, 'coverLetterText')):
            text = document.get(text_key) or ''
            issues = []
            metadata = document.get('resumeMetadata') or document.get('coverLetterMetadata') or {}
            if metadata.get('generator') == 'deterministic-fallback':
                issues.append('AI tailoring did not complete; this is a basic template. Check your AI provider connection.')
            if text:
                if name and name.lower() not in text.lower():
                    issues.append('Candidate name is missing')
                if _re.search(r'\[(?:company|name|insert|your)|as an ai|please refer to my resume', text, _re.I):
                    issues.append('Placeholder or generic fallback text detected')
                invented_numbers = _number_tokens(text) - known_numbers
                if invented_numbers:
                    issues.append('Review numbers absent from profile: ' + ', '.join(sorted(invented_numbers)))
                issues.extend(_employer_scoped_fact_issues(
                    text, profile,
                    'resume' if text_key == 'resumeText' else 'cover_letter', context))
                if text_key == 'coverLetterText':
                    words = len(_re.findall(r"\b[\w'+#.-]+\b", text))
                    if words < 80:
                        issues.append('Cover letter is too brief for a job-specific review')
                    if words > 275:
                        issues.append('Cover letter exceeds the 275-word quality limit')
                    if target_company and not _target_company_is_referenced(text, target_company):
                        issues.append('Target company is missing from the cover letter')
                    if target_title and not _target_role_is_referenced(text, target_title):
                        issues.append('Target role is missing from the cover letter')
            document['qualityIssues'] = issues
        if not bool(config.get("autoApproveResume", True)):
            resume["useOptimizedResume"] = False
        return {"resume": resume, "coverLetter": cover}
    except Exception:
        return {"resume": dict(_EMPTY_RESUME), "coverLetter": dict(_EMPTY_COVER_LETTER)}
