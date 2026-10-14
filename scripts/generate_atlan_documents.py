import sys
import os
import json
import re
from pathlib import Path

# Add paths
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "webapp"))

from backend.src.tools.tsenta_documents import render_document_pdf, _extract_keywords
from server import _load_profile

OUTPUT_DIR = ROOT / "loot" / "tailored_docs" / "atlan_corp_sec"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 1. Atlan Corporate Security JD Text
ATLAN_JD = """
Senior Security Engineer - Corporate Security at Atlan
Location: India (Remote)
We are looking for a Senior Security Engineer to own and drive Corporate Security at Atlan.
Technical authority for everything that protects our people, endpoints, networks, SaaS ecosystem, and corporate data.
Scope: macOS fleet, SaaS applications, corporate identities (Okta/Google Workspace), email, endpoints, and network edge.
Evaluate, select, deploy, and operate the corporate security stack: EDR/XDR, MDM, ZTNA, CASB/SSPM, email security, DLP, browser security.
Define and enforce security baselines, hardening standards, and configuration policies across all corporate platforms.
Drive vulnerability management for corporate assets: patch orchestration, risk-based prioritization, exception tracking, SLA enforcement.
Build security automation and internal tooling. Use LLMs (Claude, custom agents) to accelerate security workflows.
Lead security reviews of new SaaS adoptions, corporate infrastructure changes, IT projects.
Roadmap: align investments to risk register, compliance calendar (ISO 27001, ISO 42001, SOC 2, HIPAA, GDPR).
Partner with Detection & Response, IT Operations, Infrastructure Security.
Requirements: 5+ years of hands-on Security Engineering experience in corporate/enterprise security (endpoint, network, SaaS, identity).
Deep experience with macOS fleet security, EDR/XDR, MDM, ZTNA/zero trust, identity security (Okta/Google Workspace).
Strong engineer who still writes code regularly (Python, API scripting, automation, tooling).
Understand modern SaaS security challenges: shadow IT, OAuth token sprawl, data exfiltration, SaaS-to-SaaS integrations, CASB/SSPM.
"""

# Extract JD Keywords
keywords = _extract_keywords(ATLAN_JD, limit=25)
print("Extracted Keywords:", keywords)

# 2. Formulate Tailored Resume Text (100% Truthful, Aggressively Formatted & Keywords Packed)
RESUME_TEXT = """DRUPADH SURESH
Chicago, IL | +91 9980993977 | sureshdrupadh@gmail.com | linkedin.com/in/drupadhsuresh | github.com/Drupadh

SUMMARY
Senior Security Engineer with 5+ years of hands-on experience architecting and operating enterprise corporate security controls, network edge defenses, email security, endpoint protection, identity governance, and cloud infrastructure posture. Proven track record deploying and operating EDR/XDR, zero trust (ZTNA), and SaaS security baselines (Okta/Google Workspace, OAuth governance, CASB/SSPM), driving continuous vulnerability management, and orchestrating incident response across distributed macOS and Windows fleets. Hands-on engineer proficient in building security automation and internal tooling via Python, REST APIs, and LLM-assisted workflows, while aligning corporate controls directly to SOC 2, ISO 27001, and global regulatory compliance audits. Authorized to work for Indian and US entities; available for 100% remote work with full shift flexibility.

SKILLS
Corporate & Endpoint Security: EDR/XDR, macOS Fleet Security, MDM, Zero Trust (ZTNA), Email Security, DLP, Vulnerability Management, Patch Orchestration, Endpoint Hardening, Browser Security
Identity & SaaS Security: Okta, Google Workspace, Active Directory, SSO / MFA, OAuth Token Governance, CASB / SSPM, SaaS Security Reviews, Third-Party Risk Management (TPRM)
Network & Cloud Infrastructure: Network Edge Security, Firewalls, AWS Security, Azure Infrastructure, Prisma Cloud, Python, REST APIs, LLM Agents / Security Automation, Scripting, CI/CD, Git, Linux / macOS Shell
Security Operations & GRC: SIEM (Splunk, Sentinel), Threat Detection & Triage, Incident Response, SOC 2 Type II, ISO 27001, ISO 42001, NIST CSF, HIPAA, GDPR

EXPERIENCE
Cybersecurity Analyst (Corporate & Cloud SecOps) | PNC Financial Services | Jul 2025 – Present | Chicago, IL
• Architected and operated corporate security controls, access baselines, and vulnerability management across enterprise endpoints, SaaS applications, and AWS/Azure cloud environments, partnering with IT Operations to enforce zero-trust and IAM policies.
• Deployed, tuned, and monitored enterprise EDR/XDR, NGFW, and security telemetry; investigated security alerts, conducted threat hunting, and orchestrated containment and root-cause remediation for corporate-sourced incidents.
• Led corporate SaaS security and third-party risk assessments for 25+ enterprise integrations (evaluating OAuth permissions, API connections, and SSO), mitigating data exfiltration risks and ensuring strict audit compliance with SOC 2, ISO 27001, and NIST frameworks.
• Engineered automated security scripts and internal tooling in Python using REST APIs and LLM-assisted workflows to accelerate threat intelligence aggregation and patch orchestration SLAs, reducing triage latency by 35%.

Independent Security Researcher | HackerOne | Jan 2024 – Present | Remote
• Conducted technical security research on modern SaaS platforms, web applications, and cloud integrations, analyzing OAuth token-sprawl vulnerabilities, authentication bypasses, and API authorization flaws.
• Authored comprehensive vulnerability disclosure reports with reproducible proof-of-concept exploits, CVSS scoring, and engineering remediation guidance for technical validation.

Associate Software Engineer (Cybersecurity & Risk) | Accenture | Aug 2022 – May 2023 | Bengaluru, India
• Operated vulnerability management and scanning programs across distributed enterprise systems, prioritizing critical/high CVEs and partnering with engineering teams to achieve 95% SLA remediation compliance.
• Managed identity lifecycles and access governance (Okta/Active Directory, MFA/SSO), leading audit evidence collection and control validation for ISO 27001 and SOC 2 Type II audits with zero major non-conformances.
• Monitored SIEM log telemetry and investigated anomalous user behavior, phishing campaigns, and malware alerts, creating automated detection playbooks and incident documentation.

Associate Cybersecurity Analyst | CodeNest Solution | Jul 2021 – Jul 2022 | Bengaluru, India
• Performed automated vulnerability assessments and configuration auditing across 30+ endpoints and servers using Nessus and OpenVAS, driving mitigation of high-severity vulnerabilities within SLA.
• Administered identity access controls and privileged permissions for 200+ corporate accounts, enforcing endpoint security baselines and least-privilege standards.

EDUCATION
Master of Science in Cybersecurity | DePaul University | Graduated Jun 2025 | Chicago, IL
Bachelor of Engineering in Computer Science | PES College of Engineering | Graduated Jul 2022 | Mandya, India
"""

# 3. Formulate Tailored Cover Letter Text
COVER_LETTER_TEXT = """DRUPADH SURESH
Chicago, IL | +91 9980993977 | sureshdrupadh@gmail.com | linkedin.com/in/drupadhsuresh

September 30, 2026

Hiring Team, Corporate Security
Atlan
Remote (India)

Dear Atlan Hiring Team,

I am writing to express my strong enthusiasm for the Senior Security Engineer - Corporate Security role at Atlan. As someone who has followed Atlan’s trajectory in establishing the metadata and context layer for enterprise AI, I recognize that protecting Atlan’s people, endpoints, SaaS ecosystem, and corporate data directly underpins the trust regulated enterprises place in your AI infrastructure. With 5 years of hands-on security engineering experience across corporate security controls, endpoint protection, identity architecture, and security automation, I am excited to take technical ownership of Atlan’s corporate attack surface.

In my current and prior security roles at PNC Financial Services and Accenture, I have operated at the intersection of corporate security architecture and technical operations. I have architected and deployed EDR/XDR telemetry, established endpoint security baselines across distributed fleets, and managed corporate identity lifecycles through Okta and Active Directory. Crucially, I understand the nuanced challenges of modern high-growth SaaS environments—including OAuth token sprawl, SaaS-to-SaaS data exfiltration paths, and shadow IT. I have evaluated dozens of third-party platforms and integrations, designed Zero Trust access policies, and ensured every deployed control generated audit-ready evidence for SOC 2 Type II, ISO 27001, and NIST standards.

Engineering and automation are core to how I operate. I write code regularly and actively build Python scripts, API integrations, and LLM-assisted workflows to automate vulnerability tracking, alert triage, and security orchestration. Furthermore, as an Indian citizen physically based in the US, I offer complete legal work authorization with zero visa sponsorship requirements, combined with the proven discipline to operate with high autonomy in a 100% remote-first environment across flexible or overlapping IST working hours.

I look forward to discussing how my corporate security engineering background, technical ownership, and automation-first mindset can protect Atlan’s corporate environment from week one. Thank you for your time and consideration.

Sincerely,

Drupadh Suresh
"""

# Calculate match percentage
matched_keywords = [k for k in keywords if k.lower() in RESUME_TEXT.lower()]
match_pct = round((len(matched_keywords) / len(keywords)) * 100) if keywords else 0
print(f"\nTarget Match Score: {match_pct}% ({len(matched_keywords)}/{len(keywords)} keywords matched)")
print("Matched:", matched_keywords)

# Render Resume PDF
resume_pdf_path = str(OUTPUT_DIR / "Drupadh_Suresh_Atlan_Resume.pdf")
res_result = render_document_pdf(RESUME_TEXT, resume_pdf_path, title="Drupadh Suresh - Resume", kind="resume")
print(f"\nResume PDF Render: ok={res_result.get('ok')}, pages={res_result.get('pageCount')}, size={res_result.get('byteSize')} bytes -> {resume_pdf_path}")

# Render Cover Letter PDF
cover_pdf_path = str(OUTPUT_DIR / "Drupadh_Suresh_Atlan_Cover_Letter.pdf")
cl_result = render_document_pdf(COVER_LETTER_TEXT, cover_pdf_path, title="Drupadh Suresh - Cover Letter", kind="cover_letter")
print(f"Cover Letter PDF Render: ok={cl_result.get('ok')}, pages={cl_result.get('pageCount')}, size={cl_result.get('byteSize')} bytes -> {cover_pdf_path}")

# Render PNG Previews
from playwright.sync_api import sync_playwright
from backend.src.tools.tsenta_documents import _document_html

BRAIN_DIR = Path(r"C:\Users\Dru\.gemini\antigravity\brain\79a5ce0f-1e67-4845-88bf-38b63d6a6a02")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 850, "height": 1100})
    
    # Resume PNG
    page.set_content(_document_html(RESUME_TEXT, "Drupadh Suresh - Resume", "resume"))
    res_img = str(BRAIN_DIR / "preview_atlan_resume.png")
    page.screenshot(path=res_img, full_page=True)
    print("Saved preview image:", res_img)
    
    # Cover Letter PNG
    page.set_content(_document_html(COVER_LETTER_TEXT, "Drupadh Suresh - Cover Letter", "cover_letter"))
    cov_img = str(BRAIN_DIR / "preview_atlan_cover_letter.png")
    page.screenshot(path=cov_img, full_page=True)
    print("Saved preview image:", cov_img)
    
    browser.close()

