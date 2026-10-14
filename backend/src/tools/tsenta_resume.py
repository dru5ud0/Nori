"""tsenta_resume — PDF resume → profile import tool (M7).

Extracts text from a PDF resume using pypdf and populates the 18-section
Tsenta profile schema via heuristic parsing (email, phone, name, address,
skills, work experience, education, certifications, summary).

The import is best-effort: fields that cannot be confidently extracted are
left empty. The caller should review and fill in gaps before use.

Public functions return strings and never raise.
"""

from __future__ import annotations

import json
import os
import re

try:
    from tsenta_profiles import empty_profile
except ImportError:
    from backend.src.tools.tsenta_profiles import empty_profile


def _extract_text(pdf_path: str) -> str:
    """Extract all text from a PDF using pypdf.

    Args:
        pdf_path: absolute or relative path to the PDF file.

    Returns:
        str: extracted text (pages joined by newlines). Empty on failure.
    """
    try:
        from pypdf import PdfReader

        reader = PdfReader(pdf_path)
        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            pages.append(text)
        return "\n".join(pages)
    except Exception:
        return ""


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+", re.IGNORECASE)
_PHONE_RE = re.compile(
    r"(\+?\d[\d\s.-]{7,}\d)|(\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})"
)
_URL_RE = re.compile(
    r"https?://(?:www\.)?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?", re.IGNORECASE
)
_LINKEDIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w-]+", re.IGNORECASE
)
_GITHUB_RE = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/[\w-]+", re.IGNORECASE
)


def _first_match(pattern: re.Pattern, text: str) -> str:
    matches = pattern.findall(text)
    return matches[0] if matches else ""


def _likely_name(text: str) -> str:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines[:5]:
        words = line.split()
        if 2 <= len(words) <= 4 and all(w.isalpha() for w in words):
            return line
    return ""


def _likely_title(text: str) -> str:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines[1:6]:
        words = line.split()
        if 2 <= len(words) <= 6 and all(w.isalpha() for w in words):
            return line
    return ""


def _parse_address(text: str) -> dict:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines[:10]:
        if re.search(r"\d{5}", line) and re.search(r"[A-Za-z]", line):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2:
                result = {"address": parts[0], "city": "", "state": "", "zipCode": "", "country": "United States"}
                state_zip = parts[-1].strip()
                sz = re.match(r"([A-Za-z\s]+)\s+(\d{5}(?:-\d{4})?)", state_zip)
                if sz:
                    result["state"] = sz.group(1).strip()
                    result["zipCode"] = sz.group(2).strip()
                result["city"] = parts[-2].strip() if len(parts) >= 2 else ""
                if len(parts) > 2:
                    result["address"] = ", ".join(parts[:-2])
                return result
    return {"address": "", "city": "", "state": "", "zipCode": "", "country": "United States"}


def _parse_skills(text: str) -> list:
    skills = []
    lines = text.lower().split("\n")
    in_skills = False
    for line in lines:
        stripped = line.strip()
        if re.search(r"\bskills?\b|\btechnical skills?\b|\bcore competencies?\b", stripped):
            in_skills = True
            continue
        if in_skills:
            if not stripped or re.search(
                r"\bexperience\b|\bwork\b|\beducation\b|\bprojects?\b|\bcertifications?\b",
                stripped,
            ):
                in_skills = False
                continue
            for item in re.split(r"[,\n|•]", stripped):
                item = item.strip().strip("•-").strip()
                if item and len(item) > 1 and not re.search(r"^[0-9\s]+$", item):
                    skills.append(item)
    return skills[:50]


def _parse_experience(text: str) -> list:
    entries = []
    lines = text.split("\n")
    in_exp = False
    current = {}
    bullets = []
    exp_headers = re.compile(
        r"^(experience|work experience|employment|professional experience|hackerone security research|security research)$", re.IGNORECASE
    )
    section_end = re.compile(
        r"^(education|skills|projects|certifications|training)$", re.IGNORECASE
    )
    role_re = re.compile(
        r"^([A-Za-z][A-Za-z\s&./]+)\s+(at|@|–|—|-)\s+([A-Za-z][A-Za-z\s&.]+)", re.IGNORECASE
    )
    role_re2 = re.compile(
        r"^([A-Za-z][A-Za-z\s&./]+)\s*[|]\s*([A-Za-z][A-Za-z\s&.]+)", re.IGNORECASE
    )
    date_re = re.compile(
        r"(\d{4})\s*[-–—to]+\s*(\d{4}|present|current|now)", re.IGNORECASE
    )
    inline_role = re.compile(
        r'^([^,]+),\s*(.+?)\s+((?:[A-Za-z]{3,9}\s+)?\d{4})\s*[-–—]\s*'
        r'((?:[A-Za-z]{3,9}\s+)?\d{4}|Present|Current)(?:\s*\|\s*(.*))?$', re.I)

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if exp_headers.search(stripped):
            in_exp = True
            continue
        if in_exp and section_end.search(stripped):
            if current:
                current["responsibilities"] = bullets
                entries.append(current)
                current = {}
                bullets = []
            in_exp = False
            continue
        if not in_exp:
            continue
        inline = inline_role.match(stripped)
        if inline:
            if current:
                current['responsibilities'] = bullets
                entries.append(current)
            end_date = inline.group(4)
            current = {'company': inline.group(1).strip(), 'role': inline.group(2).strip(),
                       'startDate': inline.group(3), 'endDate': end_date,
                       'isCurrentRole': str(end_date).strip().lower() in ('present', 'current'),
                       'location': inline.group(5) or '', 'responsibilities': []}
            bullets = []
            continue
        match = role_re.match(stripped) or role_re2.match(stripped)
        if match:
            if current:
                current["responsibilities"] = bullets
                entries.append(current)
                current = {}
                bullets = []
            role = (match.group(1) or match.group(2)).strip()
            company = (match.group(3) or match.group(1)).strip() if match.lastindex >= 3 else match.group(2).strip()
            current = {
                "role": role,
                "company": company,
                "startDate": "",
                "endDate": "",
                "responsibilities": [],
            }
            dm = date_re.search(stripped)
            if dm:
                current["startDate"] = dm.group(1)
                current["endDate"] = dm.group(2)
                current["isCurrentRole"] = str(dm.group(2)).strip().lower() in (
                    "present", "current", "now")
            continue
        if current and stripped.startswith(("•", "-", "–", "—”", "*", "�")):
            bullet = stripped.lstrip("•–—*-�").strip()
            if bullet:
                bullets.append(bullet)
        elif current and bullets:
            bullets[-1] += ' ' + stripped
    if current:
        current["responsibilities"] = bullets
        entries.append(current)
    return entries


def _parse_education(text: str) -> list:
    entries = []
    lines = text.split("\n")
    in_edu = False
    current = {}
    edu_headers = re.compile(r"\b(education|academic background)\b", re.IGNORECASE)
    section_end = re.compile(
        r"\b(experience|skills|projects|certifications|work)\b", re.IGNORECASE
    )
    degree_re = re.compile(
        r"(Bachelor|Master|PhD|Ph\.D|B\.S|B\.A|M\.S|M\.A|MBA|Associate|"
        r"B\.Eng|M\.Eng|Doctorate|High School|Diploma|Certificate)",
        re.IGNORECASE,
    )
    school_re = re.compile(
        r"(University|College|Institute|School|Academy)", re.IGNORECASE
    )
    year_re = re.compile(r"(\d{4})")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if edu_headers.search(stripped):
            in_edu = True
            continue
        if in_edu and section_end.search(stripped):
            if current:
                entries.append(current)
                current = {}
            break
        if not in_edu:
            continue
        if degree_re.search(stripped) or school_re.search(stripped):
            if current:
                entries.append(current)
            current = {"degree": "", "institution": "", "field": "", "startDate": "", "endDate": "", "gpa": ""}
            if degree_re.search(stripped):
                current["degree"] = degree_re.search(stripped).group(1)
            if school_re.search(stripped):
                current["institution"] = stripped
            else:
                current["institution"] = stripped
            years = year_re.findall(stripped)
            if len(years) >= 2:
                current["startDate"] = years[0]
                current["endDate"] = years[1]
            elif len(years) == 1:
                current["endDate"] = years[0]
    if current:
        entries.append(current)
    return entries


def _parse_certifications(text: str) -> list:
    certs = []
    lines = text.split("\n")
    in_cert = False
    cert_headers = re.compile(r"\b(certifications?|licenses?|credentials?)\b", re.IGNORECASE)
    section_end = re.compile(
        r"\b(experience|education|skills|projects|work)\b", re.IGNORECASE
    )
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if cert_headers.search(stripped):
            in_cert = True
            continue
        if in_cert and section_end.search(stripped):
            break
        if in_cert and stripped:
            certs.append({"name": stripped, "issuer": "", "date": ""})
    return certs


def _parse_summary(text: str) -> str:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for i, line in enumerate(lines):
        if re.search(r"\bsummary\b", line, re.IGNORECASE) and i + 1 < len(lines):
            next_line = lines[i + 1]
            if len(next_line.split()) > 8 and not re.search(r"@|http|•", next_line):
                return next_line
    for line in lines[1:6]:
        if len(line.split()) > 8 and not re.search(r"@|http|•", line):
            return line
    return ""


def resume_import(pdf_path: str) -> str:
    """Import a PDF resume and produce a filled profile JSON string.

    Args:
        pdf_path: absolute or relative path to the PDF resume file.

    Returns:
        str: JSON of {"ok": True, "profile": <profile dict>, "hints": [...]}
        on success, or {"ok": False, "error": "..."} on failure.
        Never raises.
    """
    try:
        if not pdf_path or not os.path.isfile(pdf_path):
            return json.dumps({"ok": False, "error": "file-not-found"})
        text = _extract_text(pdf_path)
        if not text.strip():
            return json.dumps({"ok": False, "error": "no-text-extracted"})

        profile = empty_profile()
        profile["resumeFormat"] = "pdf"

        name = _likely_name(text)
        email = _first_match(_EMAIL_RE, text)
        phone = _first_match(_PHONE_RE, text)
        title = _likely_title(text)
        linkedin = _first_match(_LINKEDIN_RE, text)
        github = _first_match(_GITHUB_RE, text)
        url = _first_match(_URL_RE, text)
        address = _parse_address(text)
        skills = _parse_skills(text)
        experience = _parse_experience(text)
        education = _parse_education(text)
        certs = _parse_certifications(text)
        summary = _parse_summary(text)

        if name:
            parts = name.split(None, 1)
            profile["personalInformation"]["firstName"] = parts[0] if len(parts) > 0 else ""
            profile["personalInformation"]["lastName"] = parts[1] if len(parts) > 1 else ""
        profile["personalInformation"]["email"] = email
        profile["personalInformation"]["phone"] = phone
        profile["personalInformation"]["title"] = title
        profile["personalInformation"]["linkedinUrl"] = linkedin
        profile["personalInformation"]["githubUrl"] = github
        profile["personalInformation"]["website"] = url if not linkedin and not github else ""
        profile["personalInformation"]["summary"] = summary
        profile["personalInformation"]["address"] = address["address"]
        profile["personalInformation"]["city"] = address["city"]
        profile["personalInformation"]["state"] = address["state"]
        profile["personalInformation"]["zipCode"] = address["zipCode"]
        profile["personalInformation"]["country"] = address["country"]

        if skills:
            profile["skillCategories"] = [{"name": "Parsed", "skills": skills}]

        if experience:
            profile["workExperience"] = experience

        if education:
            profile["education"] = education

        if certs:
            profile["certifications"] = certs

        hints = []
        if not name:
            hints.append("name-not-found")
        if not email:
            hints.append("email-not-found")
        if not phone:
            hints.append("phone-not-found")
        if not experience:
            hints.append("work-experience-not-found")
        if not education:
            hints.append("education-not-found")

        return json.dumps(
            {
                "ok": True,
                "profile": profile,
                "hints": hints,
                "extracted": {
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "title": title,
                    "skills": len(skills),
                    "experience": len(experience),
                    "education": len(education),
                    "certifications": len(certs),
                },
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc) or "import-failed"})


def resume_import_to_file(pdf_path: str, output_path: str | None = None) -> str:
    """Import a PDF resume and save the profile to a JSON file.

    Args:
        pdf_path: path to the PDF resume file.
        output_path: path for the output JSON profile (default:
            loot/state/profile.json next to the pipeline store).

    Returns:
        str: JSON of {"ok": True, "path": <output path>, "hints": [...]}
        on success, or {"ok": False, "error": "..."} on failure.
        Never raises.
    """
    try:
        result = json.loads(resume_import(pdf_path))
        if not result.get("ok"):
            return json.dumps(result)
        if output_path is None:
            output_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "..", "..", "loot", "state",
            )
            output_path = os.path.join(output_dir, "profile.json")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(result["profile"], handle, ensure_ascii=False, indent=2)
        return json.dumps(
            {
                "ok": True,
                "path": output_path,
                "hints": result.get("hints", []),
                "extracted": result.get("extracted", {}),
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc) or "save-failed"})
