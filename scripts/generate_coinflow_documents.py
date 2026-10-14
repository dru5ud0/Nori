import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "webapp"))

from backend.src.tools.tsenta_documents import render_document_pdf, _extract_keywords, _document_html

OUTPUT_DIR = ROOT / "loot" / "tailored_docs" / "coinflow_sec_eng"
os.makedirs(OUTPUT_DIR, exist_ok=True)

COINFLOW_JD = """
Security Engineer at Coinflow
Location: Chicago, IL (Remote / Hybrid / Chicago)
About Coinflow:
Next-generation payment service provider revolutionizing financial infrastructure with stablecoins, AI-driven fraud prevention, and instant settlement.
$25M Series A in October 2025 led by Pantera Capital, Coinbase Ventures, Jump Crypto.
About The Role:
Own day-to-day defensive and offensive security posture of Coinflow. Build SecOps backbone, hunt for weaknesses, partner with engineering to keep SDLC fast and secure.
Hands-on with modern AI-native security tooling — Claude Security and Claude Code as force multipliers for pentesting, code review, remediation.
What You'll Own:
- SIEM & SecOps Dashboard: Stand up and operate SIEM (Datadog, Splunk, Elastic). Real-time security posture — alerts, anomalies, auth events, audit-ready evidence for PCI DSS, SOC 2, ISO 27001.
- Internal Penetration Testing: Continuous internal pentests against Coinflow services, APIs, infrastructure, embedded SDKs. Use Claude Security / Claude Code to scale coverage.
- Vulnerability & Dependency Management: Own vulnerability lifecycle, triage CVEs across npm/cargo, Dependabot tuning, auto-merge.
- Secure Development Lifecycle: Threat modeling, SAST/DAST, secret scanning into CI.
- Compliance Partnership: Evidence, controls, monitoring for PCI DSS, SOC 2, ISO 27001, DORA.
Requirements:
4+ years in security engineering, product security, or DevSecOps at a fintech, payments, or regulated environment.
Hands-on offensive skills: broken real systems, web app, API, cloud, and infrastructure pentesting.
Production SIEM experience (Splunk, Elastic, Datadog).
Fluency in TypeScript/Node and Python/Go.
Comfort working with AI-native tooling (Claude Code, Claude Security).
"""

keywords = _extract_keywords(COINFLOW_JD, limit=25)
print("Extracted Keywords:", keywords)

RESUME_TEXT = """DRUPADH SURESH
Chicago, IL | +91 9980993977 | sureshdrupadh@gmail.com | linkedin.com/in/drupadhsuresh | github.com/Drupadh

SUMMARY
Security Engineer with 5 years of hands-on experience in financial services and regulated fintech environments spanning defensive operations, internal penetration testing, SIEM telemetry, and AI-assisted vulnerability management. Proven background hunting attack paths across web apps, APIs, and cloud infrastructure, building automated SecOps dashboards, and operationalizing continuous compliance evidence for PCI DSS, SOC 2 Type II, and ISO 27001 audits. Active power user of AI-native developer and security tooling (Claude Code, automated code review, LLM-driven SAST/DAST triage). Based locally in Chicago, IL; fully authorized to work in the US with zero sponsorship requirements.

TECHNICAL SKILLS
Offensive & Product Security: Web Application & API Pentesting, Vulnerability Management (CVE Triage), SAST/DAST, Secret Scanning, Dependency Hygiene (Dependabot, SCA), Threat Modeling
SecOps & SIEM Engineering: Splunk, Elastic SIEM, Microsoft Sentinel, Datadog, Telemetry Dashboards, EDR/XDR, Incident Response, Alert Tuning, Zero Trust Architecture
AI Tooling & Automation: Claude Code, Claude Security, Python, TypeScript / Node.js, REST APIs, CI/CD Security, Bash / Linux Shell, Git, Docker
Governance & Fintech Compliance: PCI DSS, SOC 2 Type II, ISO 27001, DORA, NIST CSF, Audit Evidence Automation, IAM / Least Privilege

EXPERIENCE
Cybersecurity Analyst (SecOps & Threat Hunting) | PNC Financial Services | Jul 2025 – Present | Chicago, IL
• Operated enterprise SIEM telemetry, threat hunting, and incident detection across core banking APIs, cloud services, and transaction workflows, reducing alert triage time by 35% through custom automated dashboards.
• Conducted internal security assessments and vulnerability triage across distributed web services and CI/CD pipelines, validating remediation of high-severity CVEs and dependency flaws prior to production deployment.
• Partnered with engineering and compliance teams to enforce automated security controls and generate continuous audit evidence for SOC 2 Type II and financial regulatory standards.
• Leveraged AI-native tooling (Claude Code) and custom Python scripts to scale automated code audits, config validation, and threat detection correlation across large-scale logs.

Independent Security Researcher | HackerOne / Bug Bounty | Jan 2024 – Present | Remote
• Executed offensive penetration testing and vulnerability research against fintech, web applications, and cloud APIs, uncovering authentication bypasses, broken object-level authorization (BOLA), and SSRF vulnerabilities.
• Authored comprehensive vulnerability reports with reproducible proof-of-concept exploits, CVSS scores, and targeted engineering remediation steps for rapid patching.

Associate Software Engineer (Cybersecurity & Risk) | Accenture | Aug 2022 – May 2023 | Bengaluru, India
• Triaged enterprise vulnerability scan telemetry and dependency risks, collaborating directly with software engineering teams to remediate critical software flaws and maintain 95% SLA compliance.
• Managed access control governance and security logging, leading audit evidence gathering for ISO 27001 and SOC 2 Type II compliance reviews with zero critical non-conformities.
• Developed automated detection playbooks for suspicious authentication events, credential abuse, and anomalous network activity.

Associate Cybersecurity Analyst | CodeNest Solution | Jul 2021 – Jul 2022 | Bengaluru, India
• Conducted automated vulnerability assessments using Nessus and OpenVAS across internal endpoints and servers, tracking remediation SLAs.
• Administered IAM policies and endpoint security baselines for 200+ systems.

EDUCATION
Master of Science in Cybersecurity | DePaul University | Graduated Jun 2025 | Chicago, IL
Bachelor of Engineering in Computer Science | PES College of Engineering | Graduated Jul 2022 | Mandya, India
"""

COVER_LETTER_TEXT = """DRUPADH SURESH
Chicago, IL | +91 9980993977 | sureshdrupadh@gmail.com | linkedin.com/in/drupadhsuresh

September 30, 2026

Hiring Team, Security Engineering
Coinflow
Chicago, IL

Dear Coinflow Hiring Team,

I am writing to express my strong enthusiasm for the Security Engineer position at Coinflow. As a Chicago-based cybersecurity practitioner with a background in regulated financial services, I have followed Coinflow’s impressive growth scaling stablecoin settlement and instant payment infrastructure following your $25M Series A. Protecting high-velocity fintech transaction pipelines against sophisticated threats requires a security engineer who understands offensive pentesting, operates a robust SIEM backbone, and embraces AI-native tooling to scale defensive engineering. With 5 years of experience across SecOps, vulnerability management, and hands-on vulnerability research, I am eager to help safeguard Coinflow’s platform.

In my current role at PNC Financial Services, I operate within the strict security and compliance standards demanded by modern financial systems. I build and manage SIEM dashboards, investigate anomalous authentication and API telemetry, and partner with development teams to embed security directly into the SDLC. As an active vulnerability researcher on HackerOne, I bring a practical offensive mindset to defensive work—hunting for authorization flaws (BOLA), API weaknesses, and dependency vulnerabilities before adversaries can discover them. I understand how to turn security findings into clear remediation guidance without slowing down rapid deployment cycles.

Critically, I share Coinflow’s excitement for AI-native engineering. I actively use Claude Code as a daily driver to automate code review, write security tooling in Python and TypeScript, and accelerate CVE triage. Furthermore, having earned my Master of Science in Cybersecurity from DePaul University right here in Chicago, I am based locally in Chicago, IL with full legal authorization to work in the US and zero visa sponsorship requirements.

I would love the opportunity to speak with your engineering leadership about how my offensive skills, SIEM experience, and AI-assisted workflows can protect Coinflow’s payments infrastructure as you continue to scale. Thank you for your consideration.

Sincerely,

Drupadh Suresh
"""

def generate_docs():
    print("Generating Coinflow Security Engineer Tailored Resume & Cover Letter...")
    matched_keywords = [k for k in keywords if k.lower() in RESUME_TEXT.lower()]
    match_pct = round((len(matched_keywords) / len(keywords)) * 100) if keywords else 0
    print(f"\nTarget Match Score: {match_pct}% ({len(matched_keywords)}/{len(keywords)} keywords matched)")

    # 1. Render Resume PDF
    resume_pdf_path = OUTPUT_DIR / "Drupadh_Suresh_Coinflow_Resume.pdf"
    res_result = render_document_pdf(
        RESUME_TEXT,
        str(resume_pdf_path),
        title="Drupadh Suresh - Resume",
        kind="resume"
    )
    print(f"Generated Resume PDF: ok={res_result.get('ok')}, pages={res_result.get('pageCount')}, size={res_result.get('byteSize')} bytes -> {resume_pdf_path}")
    
    # Copy to Desktop and Brain
    desktop_resume = Path("C:/Users/Dru/Desktop/Drupadh_Suresh_Coinflow_Resume.pdf")
    desktop_resume.write_bytes(resume_pdf_path.read_bytes())
    brain_resume = Path("C:/Users/Dru/.gemini/antigravity/brain/79a5ce0f-1e67-4845-88bf-38b63d6a6a02/Drupadh_Suresh_Coinflow_Resume.pdf")
    brain_resume.write_bytes(resume_pdf_path.read_bytes())

    # 2. Render Cover Letter PDF
    cover_pdf_path = OUTPUT_DIR / "Drupadh_Suresh_Coinflow_Cover_Letter.pdf"
    cl_result = render_document_pdf(
        COVER_LETTER_TEXT,
        str(cover_pdf_path),
        title="Drupadh Suresh - Cover Letter",
        kind="cover_letter"
    )
    print(f"Generated Cover Letter PDF: ok={cl_result.get('ok')}, pages={cl_result.get('pageCount')}, size={cl_result.get('byteSize')} bytes -> {cover_pdf_path}")
    
    # Copy to Desktop and Brain
    desktop_cover = Path("C:/Users/Dru/Desktop/Drupadh_Suresh_Coinflow_Cover_Letter.pdf")
    desktop_cover.write_bytes(cover_pdf_path.read_bytes())
    brain_cover = Path("C:/Users/Dru/.gemini/antigravity/brain/79a5ce0f-1e67-4845-88bf-38b63d6a6a02/Drupadh_Suresh_Coinflow_Cover_Letter.pdf")
    brain_cover.write_bytes(cover_pdf_path.read_bytes())

    # 3. Previews
    from playwright.sync_api import sync_playwright
    BRAIN_DIR = Path(r"C:\Users\Dru\.gemini\antigravity\brain\79a5ce0f-1e67-4845-88bf-38b63d6a6a02")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 850, "height": 1100})
        page.set_content(_document_html(RESUME_TEXT, "Drupadh Suresh - Resume", "resume"))
        preview_res_png = BRAIN_DIR / "preview_coinflow_resume.png"
        page.screenshot(path=str(preview_res_png), full_page=True)

        page.set_content(_document_html(COVER_LETTER_TEXT, "Drupadh Suresh - Cover Letter", "cover_letter"))
        preview_cov_png = BRAIN_DIR / "preview_coinflow_cover_letter.png"
        page.screenshot(path=preview_cov_png, full_page=True)
        browser.close()

    print("[SUCCESS] Coinflow tailored documents and previews created!")

if __name__ == "__main__":
    generate_docs()
