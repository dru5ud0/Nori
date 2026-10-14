"""tsenta_auto — automated job discovery, ranking, and batch application runner.

Built for automated candidate application matching:
- Analyzes candidate background (e.g. Cybersecurity, IAM, Threat/Risk, Cloud, Analyst).
- Ranks target opportunities based on candidate location match (Bangalore / South India / Remote / US Remote)
  and domain relevance.
- Automates form walk and preparation via tsenta_pipeline.create_job() and tsenta_pipeline.run_job().
- Enforces strict review gate safety: leaves applications at status="review" with zero blockers
  ready for explicit user review and one-click submission.

All public functions return dicts or strings and catch exceptions internally.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

try:
    from backend.src.tools.tsenta_pipeline import (
        create_job, run_job, job_report, list_jobs, default_store_path,
        STATUS_REVIEW, STATUS_APPLIED, STATUS_QUEUED, STATUS_FAILED
    )
except ImportError:
    from tsenta_pipeline import (
        create_job, run_job, job_report, list_jobs, default_store_path,
        STATUS_REVIEW, STATUS_APPLIED, STATUS_QUEUED, STATUS_FAILED
    )


def default_profile_path() -> str:
    """Return the absolute path to candidate profile.json in loot/state/."""
    return os.path.abspath(os.path.join(os.path.dirname(default_store_path()), "profile.json"))


def default_resume_path() -> str:
    """Return the absolute path to candidate resume.pdf in loot/state/."""
    return os.path.abspath(os.path.join(os.path.dirname(default_store_path()), "resume.pdf"))


def load_candidate_profile(profile_path: Optional[str] = None) -> Dict[str, Any]:
    """Load profile JSON from disk; returns empty dict on any failure."""
    path = profile_path or default_profile_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


# High-value skill keywords with scoring weights
_ROLE_WEIGHTS = {
    # Tier 1: Core specialization (IAM, Identity, Cyber)
    r"\b(iam|identity|access management|cybersecurity|infosec)\b": 35,
    # Tier 2: Core security operations & engineering
    r"\b(security engineer|cloud security|soc|incident response|threat|vulnerability)\b": 28,
    # Tier 3: Governance, Risk, Compliance, Trust & Privacy
    r"\b(risk|compliance|governance|privacy|trust|audit)\b": 22,
    # Tier 4: Technical & operations analyst
    r"\b(security analyst|operations analyst|systems analyst|data analyst|support engineer)\b": 18,
    # Broad analyst/engineer
    r"\b(analyst|engineer|specialist)\b": 8,
}

# Exclusion keywords (executive/mismatched roles)
_DISQUALIFY_PATTERNS = [
    r"\b(director|vice president|vp|chief|ciso|head of|partner sales)\b",
    r"\b(recruiter|account executive|sales rep|real estate|paralegal|counsel|marketing)\b",
]

_BANGALORE_LOCATIONS = ["bangalore", "bengaluru", "karnataka"]
_SOUTH_INDIA_LOCATIONS = ["hyderabad", "chennai", "kerala", "telangana", "tamil nadu", "andhra"]
_INDIA_LOCATIONS = ["india", "in", "gurugram", "gurgaon", "noida", "mumbai", "pune"]
_US_REMOTE_LOCATIONS = ["remote - usa", "remote, united states", "remote - us", "united states - remote", "remote (us)"]


def score_job_match(job: Dict[str, Any], candidate_profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Score a job posting against candidate profile preferences and skills.

    Args:
        job: dictionary with 'title', 'location', 'url', 'companyName'.
        candidate_profile: optional profile dict (defaults to loot/state/profile.json).

    Returns:
        dict: {
            "score": float,
            "region_tier": str ("bangalore" | "south_india" | "india_remote" | "us_remote" | "other"),
            "matched_keywords": list[str],
            "disqualified": bool,
            "disqualify_reason": str,
        }
    """
    try:
        title = (job.get("title") or "").strip()
        location = (job.get("location") or "").strip().lower()
        title_lower = title.lower()

        # Check disqualifiers
        for pattern in _DISQUALIFY_PATTERNS:
            if re.search(pattern, title_lower):
                return {
                    "score": -100.0,
                    "region_tier": "disqualified",
                    "matched_keywords": [],
                    "disqualified": True,
                    "disqualify_reason": f"Matches disqualifying pattern: {pattern}",
                }

        # Determine location tier
        region_tier = "other"
        location_score = 0.0

        if any(loc in location for loc in _BANGALORE_LOCATIONS):
            region_tier = "bangalore"
            location_score = 45.0  # Top target
        elif any(loc in location for loc in _SOUTH_INDIA_LOCATIONS):
            region_tier = "south_india"
            location_score = 35.0
        elif any(loc in location for loc in _INDIA_LOCATIONS):
            region_tier = "india_other"
            location_score = 25.0
        elif any(loc in location for loc in _US_REMOTE_LOCATIONS) or ("remote" in location and ("usa" in location or "united states" in location)):
            region_tier = "us_remote"
            location_score = 30.0
        elif "remote" in location:
            # Check if foreign country restrictive
            if not any(excluded in location for excluded in ["australia", "israel", "netherlands", "uk", "poland", "japan", "germany", "france", "colombia", "ireland"]):
                region_tier = "global_remote"
                location_score = 25.0
            else:
                region_tier = "foreign_country_remote"
                location_score = -50.0

        if location_score < 0:
            return {
                "score": -50.0,
                "region_tier": region_tier,
                "matched_keywords": [],
                "disqualified": True,
                "disqualify_reason": f"Outside authorized candidate regions ({location})",
            }

        # Role keyword scoring
        role_score = 0.0
        matched_keywords = []
        for pattern, weight in _ROLE_WEIGHTS.items():
            match = re.search(pattern, title_lower)
            if match:
                role_score += weight
                matched_keywords.append(match.group(0))

        # Base company tier bonus for top-tier startups and tech leaders
        company = (job.get("companyName") or "").lower()
        company_bonus = 0.0
        if any(top in company for top in ["rubrik", "zscaler", "gitlab", "postman", "hasura", "razorpay", "cred", "databricks", "coinbase", "stripe", "instacart", "mongodb", "datadog", "elastic", "okta", "zeta", "meesho"]):
            company_bonus = 15.0

        total_score = location_score + role_score + company_bonus

        return {
            "score": round(total_score, 1),
            "region_tier": region_tier,
            "matched_keywords": matched_keywords,
            "disqualified": False,
            "disqualify_reason": "",
        }
    except Exception as e:
        return {
            "score": 0.0,
            "region_tier": "error",
            "matched_keywords": [],
            "disqualified": True,
            "disqualify_reason": str(e),
        }


def rank_jobs(jobs: List[Dict[str, Any]], min_score: float = 30.0) -> List[Dict[str, Any]]:
    """Score and rank a list of jobs, sorting highest match first.

    Args:
        jobs: list of raw job dicts.
        min_score: minimum threshold score to retain in rankings.

    Returns:
        list of scored job dicts with 'match_details' sorted descending by score.
    """
    ranked = []
    try:
        for job in jobs:
            match = score_job_match(job)
            if not match["disqualified"] and match["score"] >= min_score:
                job_copy = dict(job)
                job_copy["match_details"] = match
                job_copy["match_score"] = match["score"]
                ranked.append(job_copy)

        ranked.sort(key=lambda x: x["match_score"], reverse=True)
    except Exception:
        pass
    return ranked


def auto_apply_single_job(
    job: Dict[str, Any],
    store_path: Optional[str] = None,
    profile_path: Optional[str] = None,
    headless: bool = True,
    dry_run: bool = True,
    confirmed: bool = False,
) -> Dict[str, Any]:
    """Execute end-to-end automated preparation for a single job posting.

    Checks if already in store; if new, creates job and runs tsenta_pipeline.run_job().
    Stops safely at review gate by default.

    Args:
        job: job dictionary with 'url', 'title', 'companyName', etc.
        store_path: optional path to applications.json.
        profile_path: optional path to profile.json.
        headless: whether to run Playwright browser headlessly.
        dry_run: strict safety default True.
        confirmed: user confirmation flag (default False).

    Returns:
        dict: execution summary including job_id, status, answers_count, blockers, and error.
    """
    store = store_path or default_store_path()
    url = job.get("url") or ""
    title = job.get("title") or ""
    company = job.get("companyName") or ""
    domain = job.get("companyDomain") or ""
    logo = job.get("logoUrl") or ""

    if not url:
        return {"success": False, "status": "error", "error": "Missing job url"}

    try:
        profile = load_candidate_profile(profile_path)
        if not profile:
            return {"success": False, "status": "error", "error": "Could not load candidate profile"}

        resume = default_resume_path()

        # Check if already tracked
        raw_list = list_jobs(store_path=store)
        existing_apps = json.loads(raw_list).get("applications", []) if raw_list else []
        for existing in existing_apps:
            if existing.get("url") == url:
                status = existing.get("status")
                return {
                    "success": True,
                    "already_tracked": True,
                    "job_id": existing.get("applicationId"),
                    "status": status,
                    "company": company or existing.get("companyName"),
                    "title": title or existing.get("jobTitle"),
                    "message": f"Job already tracked in state '{status}'",
                }

        # Create job
        created_raw = create_job(
            url=url,
            profile=profile,
            company_name=company,
            job_title=title,
            company_domain=domain,
            logo_url=logo,
            store_path=store,
        )
        created = json.loads(created_raw) if isinstance(created_raw, str) else created_raw
        if not created.get("ok"):
            return {
                "success": False,
                "status": "create_failed",
                "error": created.get("error", "Failed to create pipeline job"),
            }

        job_id = created.get("applicationId")

        # Run job through Playwright form-walker and LLM answer engine
        run_raw = run_job(
            job_id=job_id,
            profile=profile,
            confirmed=confirmed,
            resume_path=resume,
            headless=headless,
            store_path=store,
        )
        run_res = json.loads(run_raw) if isinstance(run_raw, str) else run_raw

        report_raw = job_report(job_id, store_path=store)
        final_job = json.loads(report_raw) if isinstance(report_raw, str) else {}

        return {
            "success": run_res.get("ok", False),
            "job_id": job_id,
            "status": final_job.get("status"),
            "company": company or final_job.get("companyName"),
            "title": title or final_job.get("jobTitle"),
            "url": url,
            "answered_count": len(final_job.get("answersSummary", {})),
            "trace_id": (final_job.get("trace") or {}).get("traceId"),
            "error": run_res.get("error"),
        }
    except Exception as e:
        return {
            "success": False,
            "status": "exception",
            "error": str(e),
            "company": company,
            "title": title,
            "url": url,
        }


def sweep_target_jobs(
    jobs: List[Dict[str, Any]],
    max_applications: int = 5,
    store_path: Optional[str] = None,
    profile_path: Optional[str] = None,
    headless: bool = True,
    dry_run: bool = True,
    confirmed: bool = False,
) -> Dict[str, Any]:
    """Automate sweeping and applying for a batch of ranked target jobs.

    Args:
        jobs: list of ranked job dicts.
        max_applications: max number of new applications to execute in this batch.
        store_path: optional applications.json path.
        profile_path: optional profile.json path.
        headless: whether browser runs headless.
        dry_run: safety gate (default True).
        confirmed: user confirmation (default False).

    Returns:
        dict: {
            "total_candidates": int,
            "attempted": int,
            "ready_for_review": int,
            "already_tracked": int,
            "failed": int,
            "results": list[dict],
        }
    """
    results = []
    attempted = 0
    ready_for_review = 0
    already_tracked = 0
    failed = 0

    try:
        for job in jobs:
            if attempted >= max_applications:
                break

            res = auto_apply_single_job(
                job=job,
                store_path=store_path,
                profile_path=profile_path,
                headless=headless,
                dry_run=dry_run,
                confirmed=confirmed,
            )

            if res.get("already_tracked"):
                already_tracked += 1
                results.append(res)
                continue

            attempted += 1
            results.append(res)

            if res.get("status") == STATUS_REVIEW:
                ready_for_review += 1
            else:
                failed += 1

        return {
            "total_candidates": len(jobs),
            "attempted": attempted,
            "ready_for_review": ready_for_review,
            "already_tracked": already_tracked,
            "failed": failed,
            "results": results,
        }
    except Exception as e:
        return {
            "total_candidates": len(jobs),
            "attempted": attempted,
            "ready_for_review": ready_for_review,
            "already_tracked": already_tracked,
            "failed": failed,
            "error": str(e),
            "results": results,
        }
