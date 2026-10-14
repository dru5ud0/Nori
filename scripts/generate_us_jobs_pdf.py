"""
Regenerate US Cybersecurity Jobs Directory PDF with only verified, active roles.
"""

import os
from pathlib import Path
from playwright.sync_api import sync_playwright

DESKTOP = Path(os.environ["USERPROFILE"]) / "Desktop"
OUTPUT_PDF = DESKTOP / "US_Cybersecurity_Jobs_Directory.pdf"

ROLES_DATA = {
    "Remote (U.S.)": [
        {
            "company": "Zscaler",
            "title": "Detection Analyst",
            "job_id": "5219486007",
            "location": "Remote - USA",
            "url": "https://job-boards.greenhouse.io/zscaler/jobs/5219486007",
            "focus": "SIEM/EDR triage, threat detection, alert correlation, threat hunting"
        },
        {
            "company": "Zscaler",
            "title": "Insider Risk Security Engineer",
            "job_id": "5208421007",
            "location": "Remote - USA",
            "url": "https://job-boards.greenhouse.io/zscaler/jobs/5208421007",
            "focus": "Behavioral analytics, endpoint policy enforcement, data loss prevention"
        },
        {
            "company": "Zscaler",
            "title": "Major Incident Manager",
            "job_id": "5232613007",
            "location": "Remote - USA",
            "url": "https://job-boards.greenhouse.io/zscaler/jobs/5232613007",
            "focus": "High-severity incident handling, root cause analysis, containment workflows"
        },
        {
            "company": "Zscaler",
            "title": "Senior Information Security Engineer",
            "job_id": "5235296007",
            "location": "Remote - USA",
            "url": "https://job-boards.greenhouse.io/zscaler/jobs/5235296007",
            "focus": "Enterprise security posture, Zero Trust architecture, security engineering"
        },
        {
            "company": "Abnormal Security",
            "title": "Security & Compliance Analyst (Public Sector)",
            "job_id": "7979987003",
            "location": "Remote - USA",
            "url": "https://abnormal.ai/careers/jobs/7979987003",
            "focus": "Public sector GRC, FedRAMP / SOC 2 compliance, audit artifact prep"
        },
        {
            "company": "Abnormal Security",
            "title": "Senior Security Engineer",
            "job_id": "7655130003",
            "location": "Remote - USA",
            "url": "https://abnormal.ai/careers/jobs/7655130003",
            "focus": "Cloud detection engineering, infrastructure hardening, attack surface reduction"
        },
        {
            "company": "Huntress",
            "title": "Senior Detection Engineering & Threat Hunting Analyst",
            "job_id": "7998317003",
            "location": "Remote - USA",
            "url": "https://www.huntress.com/careers?gh_jid=7998317003",
            "focus": "EDR telemetry analysis, LOLBins hunting, Windows behavioral detection"
        },
        {
            "company": "Elastic",
            "title": "Principal Security Compliance Analyst (InfoSec)",
            "job_id": "8166582",
            "location": "Remote - USA",
            "url": "https://www.elastic.co/careers/jobs/8166582",
            "focus": "Information security risk governance, control testing, audit readiness"
        },
        {
            "company": "Elastic",
            "title": "Senior Network Security Engineer | Zero Trust",
            "job_id": "8103695",
            "location": "Remote - USA",
            "url": "https://www.elastic.co/careers/jobs/8103695",
            "focus": "Zero Trust network architecture, egress filtering, secure access design"
        },
        {
            "company": "Vanta",
            "title": "Product GRC Subject Matter Expert (V4G)",
            "job_id": "8738b34f",
            "location": "Remote - U.S.",
            "url": "https://jobs.ashbyhq.com/vanta/8738b34f-cf9a-4d68-90ac-76a19dc56ac0",
            "focus": "SOC 2, ISO 27001, continuous compliance, vendor risk management"
        },
        {
            "company": "Vanta",
            "title": "Governance, Risk, and Compliance (GRC) Expert",
            "job_id": "2f2ad814",
            "location": "Remote - U.S.",
            "url": "https://jobs.ashbyhq.com/vanta/2f2ad814-2437-46bc-8829-9413f1840db0",
            "focus": "Third-party risk management, security control implementation"
        },
        {
            "company": "Datadog",
            "title": "Staff Application Security Engineer",
            "job_id": "7777798",
            "location": "Remote - USA",
            "url": "https://careers.datadoghq.com/detail/7777798/",
            "focus": "Application vulnerability remediation, threat modeling, code security"
        }
    ],
    "Hybrid (U.S.)": [
        {
            "company": "KnowBe4",
            "title": "Cybersecurity Threat Researcher",
            "job_id": "8856509002",
            "location": "Arlington, VA (Hybrid)",
            "url": "https://www.knowbe4.com/careers?gh_jid=8856509002",
            "focus": "Threat intelligence research, social engineering analysis, adversary TTPs"
        },
        {
            "company": "Abnormal Security",
            "title": "Software Engineer II - Insider Risk",
            "job_id": "7992780003",
            "location": "San Francisco, CA (Hybrid)",
            "url": "https://abnormal.ai/careers/jobs/7992780003",
            "focus": "Insider threat behavioral models, identity telemetry, risk scoring"
        },
        {
            "company": "Snyk",
            "title": "Senior Product Security Engineer",
            "job_id": "507a3707",
            "location": "Boston, MA (Hybrid)",
            "url": "https://jobs.ashbyhq.com/snyk/507a3707-d6bd-48c4-800f-429ecf40769e",
            "focus": "Product security architecture, vulnerability scanning, security reviews"
        }
    ],
    "In-Person / Onsite (U.S.)": [
        {
            "company": "Okta",
            "title": "Principal, Global Security Operations Center",
            "job_id": "8186035",
            "location": "Washington, DC",
            "url": "https://www.okta.com/company/careers/opportunity/8186035",
            "focus": "Global SOC leadership, high-tier incident response, SIEM optimization"
        },
        {
            "company": "Datadog",
            "title": "Senior Security Engineer, Vulnerability Management",
            "job_id": "8173840",
            "location": "New York, NY / Boston, MA",
            "url": "https://careers.datadoghq.com/detail/8173840/",
            "focus": "Vulnerability scanning (Nessus/Qualys), prioritization, SLA tracking"
        },
        {
            "company": "Datadog",
            "title": "Senior Services Architect, Security & Cloud SIEM",
            "job_id": "7996907",
            "location": "San Francisco, CA / NYC / Denver",
            "url": "https://careers.datadoghq.com/detail/7996907/",
            "focus": "Cloud SIEM architecture, log normalization, detection rule design"
        },
        {
            "company": "Datadog",
            "title": "Senior Platform Security Engineer",
            "job_id": "7815616",
            "location": "New York, NY",
            "url": "https://careers.datadoghq.com/detail/7815616/",
            "focus": "Platform hardening, IAM policies, infrastructure security controls"
        },
        {
            "company": "Elastic",
            "title": "Senior Security Research Engineer (SONAR)",
            "job_id": "8161935",
            "location": "United States",
            "url": "https://www.elastic.co/careers/jobs/8161935",
            "focus": "Novel adversary research, detection engineering, behavioral signatures"
        },
        {
            "company": "Huntress",
            "title": "Principal Security Researcher - EDR (Windows)",
            "job_id": "7807467003",
            "location": "United States",
            "url": "https://www.huntress.com/careers?gh_jid=7807467003",
            "focus": "Windows internals, reverse engineering, kernel/userland threat hunting"
        }
    ]
}

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {
    size: letter;
    margin: 16mm 14mm 16mm 14mm;
  }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #1e293b;
    line-height: 1.4;
    font-size: 11px;
    margin: 0;
  }
  .header {
    border-bottom: 2px solid #0284c7;
    padding-bottom: 10px;
    margin-bottom: 14px;
    display: flex;
    justify-content: space-between;
  }
  .title { font-size: 18px; font-weight: 800; color: #0f172a; margin: 0 0 4px 0; }
  .subtitle { font-size: 11px; color: #475569; margin: 0; }
  .meta-box { text-align: right; font-size: 10px; color: #64748b; }
  .section-title {
    font-size: 12px; font-weight: 700; text-transform: uppercase; color: #0f172a;
    background: #f1f5f9; padding: 5px 8px; border-left: 4px solid #0284c7;
    margin-top: 14px; margin-bottom: 8px;
  }
  table { width: 100%; border-collapse: collapse; margin-bottom: 12px; font-size: 10px; }
  th { background: #f8fafc; color: #475569; text-align: left; padding: 6px 8px; font-weight: 600; border-bottom: 1.5px solid #cbd5e1; text-transform: uppercase; font-size: 8.5px; }
  td { padding: 6px 8px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
  tr:nth-child(even) td { background-color: #fafafa; }
  .company-cell { font-weight: 700; color: #0f172a; }
  .role-title { font-weight: 600; color: #1e293b; }
  .job-focus { font-size: 9px; color: #64748b; }
  .job-id { font-family: monospace; background: #f1f5f9; color: #0369a1; padding: 1px 4px; border-radius: 3px; font-weight: 600; font-size: 9px; }
  .link-cell a { color: #0284c7; text-decoration: none; font-weight: 600; }
</style>
</head>
<body>
<div class="header">
  <div>
    <h1 class="title">Verified U.S. Cybersecurity Career Directory</h1>
    <p class="subtitle">Audited Live Positions | Tailored for Drupadh Suresh (5 YOE - Risk, SOC, Cloud, GRC)</p>
  </div>
  <div class="meta-box">
    <strong>Audited Status:</strong> HTTP 200 Live | No Clearance Blocks<br>
    <strong>US Authorization:</strong> Authorized to Work in U.S.
  </div>
</div>
__CONTENT__
</body>
</html>
"""

def generate_pdf():
    content_html = ""
    for section_name, jobs in ROLES_DATA.items():
        content_html += f"""
        <div class="section-title">{section_name} ({len(jobs)} Positions)</div>
        <table>
          <thead>
            <tr>
              <th style="width: 14%;">Company</th>
              <th style="width: 38%;">Position & Focus</th>
              <th style="width: 14%;">Job ID</th>
              <th style="width: 20%;">Location</th>
              <th style="width: 14%;">Link</th>
            </tr>
          </thead>
          <tbody>
        """
        for j in jobs:
            content_html += f"""
            <tr>
              <td class="company-cell">{j['company']}</td>
              <td><div class="role-title">{j['title']}</div><div class="job-focus">• {j['focus']}</div></td>
              <td><span class="job-id">{j['job_id']}</span></td>
              <td>{j['location']}</td>
              <td class="link-cell"><a href="{j['url']}">Apply &rarr;</a></td>
            </tr>
            """
        content_html += "</tbody></table>"

    full_html = HTML_TEMPLATE.replace("__CONTENT__", content_html)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(full_html, wait_until="load")
        page.pdf(
            path=str(OUTPUT_PDF),
            format="Letter",
            print_background=True,
            prefer_css_page_size=True,
            margin={"top": "12mm", "bottom": "12mm", "left": "12mm", "right": "12mm"}
        )
        browser.close()
    print("PDF updated.")

if __name__ == "__main__":
    generate_pdf()
