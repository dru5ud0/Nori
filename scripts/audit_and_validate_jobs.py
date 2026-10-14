"""
Audit every single job URL:
1. Verify HTTP status and that the posting is currently open/live.
2. Fetch full job description.
3. Check candidate fit for Drupadh Suresh:
   - Profile: 5 YOE (Cybersecurity Risk Analyst, TPRM, SOC, SIEM, Cloud Security Prisma Cloud/AWS/Azure, GRC).
   - Check if Active Security Clearance / TS/SCI is required (disqualifying).
   - Check YOE requirements (flag if asks for 8-10+ YOE).
   - Check if role is pure developer vs cybersecurity analyst/engineer.
"""

import urllib.request
import json
import re

JOBS_TO_AUDIT = [
    # Zscaler
    {"company": "Zscaler", "title": "Detection Analyst", "id": "5219486007", "board": "zscaler", "ats": "greenhouse", "url": "https://job-boards.greenhouse.io/zscaler/jobs/5219486007"},
    {"company": "Zscaler", "title": "Insider Risk Security Engineer", "id": "5208421007", "board": "zscaler", "ats": "greenhouse", "url": "https://job-boards.greenhouse.io/zscaler/jobs/5208421007"},
    {"company": "Zscaler", "title": "Major Incident Manager", "id": "5232613007", "board": "zscaler", "ats": "greenhouse", "url": "https://job-boards.greenhouse.io/zscaler/jobs/5232613007"},
    {"company": "Zscaler", "title": "Security Compliance Architect", "id": "5140589007", "board": "zscaler", "ats": "greenhouse", "url": "https://job-boards.greenhouse.io/zscaler/jobs/5140589007"},
    {"company": "Zscaler", "title": "Senior Information Security Engineer", "id": "5235296007", "board": "zscaler", "ats": "greenhouse", "url": "https://job-boards.greenhouse.io/zscaler/jobs/5235296007"},
    {"company": "Zscaler", "title": "Senior Consultant - Zero Trust Cloud Specialist", "id": "5210021007", "board": "zscaler", "ats": "greenhouse", "url": "https://job-boards.greenhouse.io/zscaler/jobs/5210021007"},
    {"company": "Zscaler", "title": "Architect, Software Development (L7 Proxy)", "id": "5239093007", "board": "zscaler", "ats": "greenhouse", "url": "https://job-boards.greenhouse.io/zscaler/jobs/5239093007"},
    
    # Abnormal Security
    {"company": "Abnormal Security", "title": "Security & Compliance Analyst (Public Sector)", "id": "7979987003", "board": "abnormalsecurity", "ats": "greenhouse", "url": "https://abnormal.ai/careers/jobs/7979987003"},
    {"company": "Abnormal Security", "title": "Senior Security Engineer", "id": "7655130003", "board": "abnormalsecurity", "ats": "greenhouse", "url": "https://abnormal.ai/careers/jobs/7655130003"},
    {"company": "Abnormal Security", "title": "Software Engineer II - Insider Risk", "id": "7992780003", "board": "abnormalsecurity", "ats": "greenhouse", "url": "https://abnormal.ai/careers/jobs/7992780003"},

    # Huntress
    {"company": "Huntress", "title": "Senior Detection Engineering & Threat Hunting Analyst", "id": "7998317003", "board": "huntress", "ats": "greenhouse", "url": "https://www.huntress.com/careers?gh_jid=7998317003"},
    {"company": "Huntress", "title": "Principal Security Researcher - EDR (Windows)", "id": "7807467003", "board": "huntress", "ats": "greenhouse", "url": "https://www.huntress.com/careers?gh_jid=7807467003"},

    # Elastic
    {"company": "Elastic", "title": "Principal Security Compliance Analyst (InfoSec)", "id": "8166582", "board": "elastic", "ats": "greenhouse", "url": "https://www.elastic.co/careers/jobs/8166582"},
    {"company": "Elastic", "title": "Senior Network Security Engineer (Zero Trust)", "id": "8103695", "board": "elastic", "ats": "greenhouse", "url": "https://www.elastic.co/careers/jobs/8103695"},
    {"company": "Elastic", "title": "Senior Security Research Engineer (SONAR)", "id": "8161935", "board": "elastic", "ats": "greenhouse", "url": "https://www.elastic.co/careers/jobs/8161935"},
    {"company": "Elastic", "title": "Senior Software Engineer - EDR Workflows", "id": "8099226", "board": "elastic", "ats": "greenhouse", "url": "https://www.elastic.co/careers/jobs/8099226"},

    # Datadog
    {"company": "Datadog", "title": "Staff Application Security Engineer", "id": "7777798", "board": "datadog", "ats": "greenhouse", "url": "https://careers.datadoghq.com/detail/7777798/"},
    {"company": "Datadog", "title": "Senior Security Engineer, Vulnerability Management", "id": "8173840", "board": "datadog", "ats": "greenhouse", "url": "https://careers.datadoghq.com/detail/8173840/"},
    {"company": "Datadog", "title": "Senior Services Architect, Security & Cloud SIEM", "id": "7996907", "board": "datadog", "ats": "greenhouse", "url": "https://careers.datadoghq.com/detail/7996907/"},
    {"company": "Datadog", "title": "Senior Platform Security Engineer", "id": "7815616", "board": "datadog", "ats": "greenhouse", "url": "https://careers.datadoghq.com/detail/7815616/"},

    # KnowBe4
    {"company": "KnowBe4", "title": "Cybersecurity Threat Researcher", "id": "8856509002", "board": "knowbe4", "ats": "greenhouse", "url": "https://www.knowbe4.com/careers?gh_jid=8856509002"},

    # Okta
    {"company": "Okta", "title": "Staff Security Engineer - Federal", "id": "7571064", "board": "okta", "ats": "greenhouse", "url": "https://www.okta.com/company/careers/opportunity/7571064"},
    {"company": "Okta", "title": "Principal, Global Security Operations Center", "id": "8186035", "board": "okta", "ats": "greenhouse", "url": "https://www.okta.com/company/careers/opportunity/8186035"},

    # Vanta
    {"company": "Vanta", "title": "Product GRC Subject Matter Expert (V4G)", "id": "8738b34f-cf9a-4d68-90ac-76a19dc56ac0", "board": "vanta", "ats": "ashby", "url": "https://jobs.ashbyhq.com/vanta/8738b34f-cf9a-4d68-90ac-76a19dc56ac0"},
    {"company": "Vanta", "title": "Governance, Risk, and Compliance (GRC) Expert", "id": "2f2ad814-2437-46bc-8829-9413f1840db0", "board": "vanta", "ats": "ashby", "url": "https://jobs.ashbyhq.com/vanta/2f2ad814-2437-46bc-8829-9413f1840db0"},

    # Snyk
    {"company": "Snyk", "title": "Senior Product Security Engineer", "id": "507a3707-d6bd-48c4-800f-429ecf40769e", "board": "snyk", "ats": "ashby", "url": "https://jobs.ashbyhq.com/snyk/507a3707-d6bd-48c4-800f-429ecf40769e"},
]

def audit():
    results = []
    print("--- STARTING DEEP AUDIT OF ALL ROLES ---")

    for item in JOBS_TO_AUDIT:
        cid = item["id"]
        board = item["board"]
        ats = item["ats"]
        co = item["company"]
        ti = item["title"]

        is_live = False
        content_text = ""
        location = ""
        
        # 1. Fetch from Greenhouse API
        if ats == "greenhouse":
            api_url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{cid}"
            try:
                req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
                res = urllib.request.urlopen(req, timeout=4)
                if res.status == 200:
                    data = json.loads(res.read().decode("utf-8"))
                    is_live = True
                    content_text = (data.get("content") or "") + " " + (data.get("title") or "")
                    location = (data.get("location") or {}).get("name", "")
            except Exception as e:
                is_live = False

        # 2. Fetch from Ashby API
        elif ats == "ashby":
            api_url = f"https://api.ashbyhq.com/posting-api/job-board/{board}"
            try:
                req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
                res = urllib.request.urlopen(req, timeout=4)
                if res.status == 200:
                    data = json.loads(res.read().decode("utf-8"))
                    for j in data.get("jobs", []):
                        if cid in (j.get("id", "") + j.get("jobUrl", "")):
                            is_live = True
                            content_text = (j.get("descriptionHtml") or "") + " " + (j.get("title") or "")
                            location = j.get("location") or ""
                            break
            except Exception as e:
                is_live = False

        # Clean text
        text_clean = re.sub(r"<[^>]+>", " ", content_text).lower()

        # Check Clearances
        clearance_req = bool(re.search(r"\b(active\s+)?(ts[/ ]sci|top\s+secret|secret\s+clearance|polygraph|us\s+citizenship\s+required|must\s+be\s+a\s+u\.?s\.?\s+citizen)\b", text_clean))
        
        # Check YOE
        yoe_matches = [int(m) for m in re.findall(r"\b(\d{1,2})\+?\s*(?:-\s*\d{1,2})?\s*years?(?:\s+of)?\s+experience\b", text_clean)]
        min_yoe = min(yoe_matches) if yoe_matches else None
        max_yoe = max(yoe_matches) if yoe_matches else None

        # Check domain relevance to Drupadh (5 YOE, Risk, TPRM, SOC, Cloud, GRC)
        fit_score = 0
        fit_tags = []
        if any(k in text_clean for k in ("soc", "siem", "splunk", "sentinel", "incident response", "triage", "alerts")):
            fit_score += 25
            fit_tags.append("SOC/SIEM")
        if any(k in text_clean for k in ("risk", "tprm", "third party", "vendor", "nist", "soc 2", "grc", "compliance")):
            fit_score += 25
            fit_tags.append("Risk/GRC/TPRM")
        if any(k in text_clean for k in ("cloud security", "aws", "azure", "prisma", "posture", "iam")):
            fit_score += 25
            fit_tags.append("Cloud Security")
        if any(k in text_clean for k in ("vulnerability", "nessus", "qualys", "remediation", "patch")):
            fit_score += 20
            fit_tags.append("Vulnerability Mgmt")
        if any(k in text_clean for k in ("detection", "edr", "hunting", "xdr", "telemetry")):
            fit_score += 20
            fit_tags.append("Detection/EDR")

        # Determine Verdict
        verdict = "VALID"
        reason = "Excellent match for your 5 YOE background."
        
        if not is_live:
            verdict = "EXPIRED"
            reason = "Job posting is no longer active."
        elif clearance_req and ("clearance" in text_clean or "citizenship" in text_clean):
            # Check if clearance is hard requirement
            if "security clearance" in text_clean or "ts/sci" in text_clean:
                verdict = "CLEARANCE REQUIRED"
                reason = "Requires active U.S. government security clearance."
            elif "u.s. citizen" in text_clean or "citizenship required" in text_clean:
                verdict = "CITIZENSHIP RESTRICTION"
                reason = "Requires U.S. Citizenship (not just work authorization)."
        elif min_yoe and min_yoe > 7:
            verdict = "SENIOR STRETCH"
            reason = f"Requires {min_yoe}+ years of experience (Principal/Architect level)."
        elif any(k in item["title"].lower() for k in ("architect, software", "software engineer - edr workflows")):
            verdict = "DEV FOCUSED"
            reason = "Primarily C++/Go/Rust software engineering rather than cyber analyst/engineering."

        results.append({
            "company": co,
            "title": ti,
            "job_id": cid,
            "is_live": is_live,
            "location": location,
            "min_yoe": min_yoe,
            "verdict": verdict,
            "reason": reason,
            "fit_tags": fit_tags,
            "url": item["url"]
        })

    # Output Summary
    print(f"\nAUDIT COMPLETE: Tested {len(results)} jobs.")
    
    # Save audit log
    with open("loot/audited_jobs_validation.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    return results

if __name__ == "__main__":
    audit()
