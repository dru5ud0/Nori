"""Targeted scanner for high-paying remote security & analyst roles on Ashby and Greenhouse."""

import json
import urllib.request
from pathlib import Path

ASHBY_TARGETS = [
    "signoz", "devrev", "hasura", "appsmith", "dyte", "together-ai",
    "atlan", "pragmatike", "incident-io", "linear", "supabase", "vercel",
    "perplexity", "sentry", "anyscale", "modal", "replit", "cursor"
]

GH_TARGETS = [
    "alphasense", "postman", "browserstack", "razorpay", "swiggy",
    "cred", "slice", "pine-labs", "urban-company", "inmobi", "gitlab",
    "grafana", "elastic", "snyk", "cloudflare", "datadog", "okta",
    "zscaler", "mongodb", "canonical", "automattic"
]

def scan_ashby():
    print("--- SCANNING ASHBY BOARDS ---")
    results = []
    for company in ASHBY_TARGETS:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{company}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            res = json.loads(urllib.request.urlopen(req, timeout=5).read().decode("utf-8"))
            jobs = res.get("jobs", [])
            for j in jobs:
                title = j.get("title", "")
                loc = j.get("location", "")
                workplace = j.get("workplaceType", "")
                t_lower = title.lower()
                l_lower = loc.lower()
                w_lower = workplace.lower()
                
                # Check for security / analyst roles
                is_sec = any(k in t_lower for k in (
                    "security", "risk", "compliance", "grc", "privacy", "soc",
                    "analyst", "trust", "cyber", "infosec", "incident", "vulnerability"
                ))
                is_remote = "remote" in w_lower or "remote" in l_lower or "remote" in t_lower or "anywhere" in l_lower
                is_in_or_anywhere = any(k in l_lower for k in ("india", "anywhere", "worldwide", "global", "us", "americas"))
                
                if is_sec and is_remote:
                    item = {
                        "company": company.capitalize(),
                        "title": title,
                        "location": loc,
                        "workplaceType": workplace,
                        "ats": "ashby",
                        "url": j.get("jobUrl")
                    }
                    results.append(item)
                    print(f"[{company.upper()}] {title} | {loc} ({workplace}) -> {j.get('jobUrl')}")
        except Exception as e:
            pass
    return results

def scan_greenhouse():
    print("\n--- SCANNING GREENHOUSE BOARDS ---")
    results = []
    for company in GH_TARGETS:
        url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            res = json.loads(urllib.request.urlopen(req, timeout=5).read().decode("utf-8"))
            jobs = res.get("jobs", [])
            for j in jobs:
                title = j.get("title", "")
                loc = (j.get("location", {}) or {}).get("name", "")
                t_lower = title.lower()
                l_lower = loc.lower()
                
                is_sec = any(k in t_lower for k in (
                    "security", "risk", "compliance", "grc", "privacy", "soc",
                    "analyst", "trust", "cyber", "infosec", "incident", "vulnerability"
                ))
                is_remote = "remote" in l_lower or "remote" in t_lower or "anywhere" in l_lower
                
                if is_sec and is_remote:
                    item = {
                        "company": company.capitalize(),
                        "title": title,
                        "location": loc,
                        "ats": "greenhouse",
                        "url": j.get("absolute_url")
                    }
                    results.append(item)
                    print(f"[{company.upper()}] {title} | {loc} -> {j.get('absolute_url')}")
        except Exception as e:
            pass
    return results

if __name__ == "__main__":
    ashby_res = scan_ashby()
    gh_res = scan_greenhouse()
    total = len(ashby_res) + len(gh_res)
    print(f"\nTOTAL MATCHED REMOTE SECURITY/ANALYST ROLES: {total}")
