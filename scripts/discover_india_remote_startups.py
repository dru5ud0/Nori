"""Automated discovery of 100% remote security, risk, and analyst roles at high-paying Indian startups."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

APPS_PATH = ROOT / "loot" / "state" / "applications.json"


def query_greenhouse(company: str) -> list[dict]:
    """Query Greenhouse public boards API."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=6)
        data = json.loads(resp.read().decode("utf-8"))
        jobs = data.get("jobs", [])
        matched = []
        for j in jobs:
            loc = (j.get("location", {}).get("name") or "").lower()
            title = (j.get("title") or "").lower()
            
            is_india = any(k in loc for k in ("india", "bangalore", "bengaluru", "delhi", "remote - india"))
            is_remote = "remote" in loc or "remote" in title
            is_sec = any(k in title for k in ("security", "risk", "compliance", "grc", "privacy", "soc", "analyst"))
            
            if is_sec and (is_remote or is_india):
                matched.append({
                    "companyName": company.capitalize(),
                    "jobTitle": j.get("title"),
                    "jobLocation": j.get("location", {}).get("name"),
                    "url": j.get("absolute_url"),
                    "atsType": "greenhouse",
                    "status": "review",
                    "source": "discovery_india_remote",
                    "tags": ["india_startup_remote"],
                    "discoveredAt": int(time.time()),
                })
        return matched
    except Exception:
        return []


def query_ashby(company: str) -> list[dict]:
    """Query Ashby public boards API."""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=6)
        data = json.loads(resp.read().decode("utf-8"))
        jobs = data.get("jobs", [])
        matched = []
        for j in jobs:
            loc = (j.get("location") or "").lower()
            title = (j.get("title") or "").lower()
            workplace = (j.get("workplaceType") or "").lower()
            
            is_india = any(k in loc for k in ("india", "bangalore", "bengaluru", "delhi"))
            is_remote = "remote" in workplace or "remote" in loc or "remote" in title
            is_sec = any(k in title for k in ("security", "risk", "compliance", "grc", "privacy", "soc", "analyst"))
            
            if is_sec and (is_remote or is_india):
                matched.append({
                    "companyName": company.capitalize(),
                    "jobTitle": j.get("title"),
                    "jobLocation": f"{j.get('location')} ({j.get('workplaceType')})",
                    "url": j.get("jobUrl"),
                    "atsType": "ashby",
                    "status": "review",
                    "source": "discovery_india_remote",
                    "tags": ["india_startup_remote"],
                    "discoveredAt": int(time.time()),
                })
        return matched
    except Exception:
        return []


def discover_and_stage():
    print("=" * 70)
    print("  DISCOVERING HIGH-PAYING REMOTE ROLES AT INDIAN STARTUPS")
    print("=" * 70)
    
    ashby_companies = ["atlan", "pragmatike", "hasura", "signoz", "outmarket-ai", "devrev"]
    gh_companies = ["alphasense", "coinbase", "zscaler", "okta", "elastic", "snyk", "gitlab"]

    all_matched = []
    
    print("\nScanning Ashby boards (Atlan, Pragmatike, Hasura, SigNoz)...")
    for c in ashby_companies:
        res = query_ashby(c)
        if res:
            print(f"  + {c.capitalize()}: {len(res)} matching remote roles")
            all_matched.extend(res)

    print("\nScanning Greenhouse boards (AlphaSense, Coinbase, Zscaler, Okta)...")
    for c in gh_companies:
        res = query_greenhouse(c)
        if res:
            print(f"  + {c.capitalize()}: {len(res)} matching remote roles")
            all_matched.extend(res)

    print(f"\nTotal remote India roles discovered: {len(all_matched)}")

    # Load existing applications
    os.makedirs(APPS_PATH.parent, exist_ok=True)
    if APPS_PATH.exists():
        data = json.loads(APPS_PATH.read_text(encoding="utf-8"))
    else:
        data = {"applications": {}}

    apps_dict = data.get("applications", {})
    existing_urls = {a.get("url") for a in apps_dict.values() if a.get("url")}

    added_count = 0
    for j in all_matched:
        url = j["url"]
        if url not in existing_urls:
            app_id = f"app_remote_in_{int(time.time())}_{added_count:02d}"
            j["applicationId"] = app_id
            apps_dict[app_id] = j
            existing_urls.add(url)
            added_count += 1
            print(f"  -> Staged: {j['companyName']} - {j['jobTitle']} ({j['atsType']})")

    data["applications"] = apps_dict
    APPS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[DONE] Successfully staged {added_count} new remote roles into {APPS_PATH}")


if __name__ == "__main__":
    discover_and_stage()
