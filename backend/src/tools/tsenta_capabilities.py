"""Truthful runtime capability registry for Nori's ATS adapters.

Detection is not execution support.  This registry tells the API and UI what
the current Python runner can actually prepare, and keeps unattended submit
disabled until an adapter has real submission-and-receipt evidence.
"""

from __future__ import annotations

try:
    from backend.src.tools.tsenta_ats import ATS_CATALOG, ats_display_name
except ImportError:
    from tsenta_ats import ATS_CATALOG, ats_display_name


_PREPARE = {
    "greenhouse": "dry-run-verified",
    "lever": "dry-run-verified",
    "workday": "dry-run-verified",
    "ashby": "dry-run-verified",
    "icims": "dry-run-verified",
    "smartrecruiters": "dry-run-verified",
    "jazzhr": "dry-run-verified",
    "bamboohr": "dry-run-verified",
    "workable": "dry-run-verified",
    "rippling": "dry-run-verified",
    "oraclecloud": "dry-run-verified",
    "jobvite": "dry-run-verified",
    "breezyhr": "dry-run-verified",
    "recruitee": "dry-run-verified",
    "teamtailor": "dry-run-verified",
    "dayforce": "dry-run-verified",
    "paylocity": "dry-run-verified",
    "brassring": "dry-run-verified",
    "adp": "dry-run-verified",
    "paycom": "dry-run-verified",
    "successfactors": "dry-run-verified",
    "zohorecruit": "dry-run-verified",
    "ultipro": "dry-run-verified",
    "avature": "dry-run-verified",
    "pinpoint": "dry-run-verified",
    "phenom": "dry-run-verified",
    "hireology": "dry-run-verified",
    "join": "dry-run-verified",
    "dover": "dry-run-verified",
    "gem": "dry-run-verified",
    "polymer": "dry-run-verified",
    "indeed": "dry-run-verified",
    "bullhorn": "dry-run-verified",
    "eightfold": "dry-run-verified",
}


def ats_capability(ats_id: str) -> dict:
    """Return the execution capability and evidence for one ATS id."""
    try:
        aid = str(ats_id or "unknown").lower()
        level = _PREPARE.get(aid, "detect-only")
        prepare = aid in _PREPARE
        warnings = []
        if level == "experimental":
            warnings.append("This adapter is experimental and may need manual correction.")
        if level == "detect-only":
            warnings.append("Nori can identify this ATS but cannot safely walk its form yet.")
        if prepare:
            warnings.append("Review is a fresh form replay; answers must be checked before submission.")
        if aid == "bullhorn":
            warnings[-1:] = [
                "Review is a fresh API replay; no candidate data is sent until explicit approval."
            ]
        if aid == "dayforce":
            warnings.append(
                "Dayforce may activate invisible reCAPTCHA and require manual completion."
            )
        if aid == "paylocity":
            warnings.append(
                "Employer screening questions and final acknowledgments remain user-reviewed."
            )
        if aid == "oraclecloud":
            warnings.append(
                "Oracle Candidate Experience privacy notice and employer disclosures require user review."
            )
        if aid == "smartrecruiters":
            warnings.append(
                "SmartRecruiters may present a DataDome challenge requiring human completion."
            )
        if aid == "jobvite":
            warnings.append(
                "Jobvite data consent or employer terms remain user-reviewed."
            )
        if aid == "brassring":
            warnings.append(
                "BrassRing employer privacy notices and account gates require user review."
            )
        if aid == "adp":
            warnings.append(
                "ADP candidate account checkpoints require user sign-in."
            )
        if aid == "paycom":
            warnings.append(
                "Paycom multi-step applicant questions and attestations remain user-reviewed."
            )
        if aid == "successfactors":
            warnings.append(
                "SAP SuccessFactors tenant candidate accounts require user sign-in."
            )
        if aid == "zohorecruit":
            warnings.append(
                "Zoho Recruit employer questions and consent choices remain user-reviewed."
            )
        if aid == "ultipro":
            warnings.append(
                "UKG Pro candidate accounts require user sign-in."
            )
        if aid == "avature":
            warnings.append(
                "Avature candidate credential checkpoints require user sign-in."
            )
        if aid == "join":
            warnings.append(
                "JOIN email magic-link verification requires your confirmation."
            )
        if aid == "polymer":
            warnings.append(
                "Polymer Cloudflare checkpoints or custom screening remain user-reviewed."
            )
        if aid == "indeed":
            warnings.append(
                "Indeed SmartApply may require account sign-in or phone verification."
            )
        return {
            "ats": aid,
            "name": ats_display_name(aid),
            "level": level,
            "detect": aid in ATS_CATALOG,
            "prepare": prepare,
            "fill": prepare,
            "reviewMode": "replay" if prepare else "none",
            "manualSubmit": prepare,
            "unattendedSubmit": False,
            "confirmation": ("structured-api" if aid == "bullhorn" else
                             "specific-signals" if prepare else "none"),
            "persistentSession": prepare and aid != "bullhorn",
            "receiptEvidence": aid in (
                "greenhouse", "lever", "workday", "ashby", "icims", "jazzhr",
                "workable", "bamboohr", "rippling"),
            "warnings": warnings,
        }
    except Exception:
        return {
            "ats": "unknown", "name": "Unknown", "level": "detect-only",
            "detect": False, "prepare": False, "fill": False,
            "reviewMode": "none", "manualSubmit": False,
            "unattendedSubmit": False, "confirmation": "none",
            "persistentSession": False, "receiptEvidence": False,
            "warnings": ["ATS capability could not be determined."],
        }


def ats_capabilities() -> list:
    """Return capabilities for every built-in ATS in display-name order."""
    try:
        return [ats_capability(aid) for aid in sorted(
            ATS_CATALOG, key=lambda item: ats_display_name(item).lower())]
    except Exception:
        return []


def ats_can_prepare(ats_id: str) -> bool:
    """Return whether Nori can create a browser-walked review draft."""
    return bool(ats_capability(ats_id).get("prepare"))


def ats_can_unattended_submit(ats_id: str) -> bool:
    """Return whether unattended submission is certified for this ATS."""
    return bool(ats_capability(ats_id).get("unattendedSubmit"))
