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

OUTPUT_DIR = ROOT / "loot" / "tailored_docs" / "alphasense_ai_sec"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 1. AlphaSense AI Security Analyst JD Text
ALPHASENSE_JD = """
AI Security Analyst at AlphaSense
Location: Remote - India
About the Role:
We are building an AI Security and Governance capability and need an AI Security Analyst to be the front line for detecting, investigating, and containing risk across every AI tool, agent, and model touching AlphaSense's environment.
Monitor enterprise AI usage end to end, hunt for unauthorized ("shadow") AI and rogue agent activity, and turn raw AI telemetry into triaged findings.
Primary contributor to the evidence base underpinning our ISO 42001 certification and our broader AI risk posture.
Key Responsibilities:
- AI Tool Discovery & Shadow AI Monitoring: CASB/SWG, OAuth, endpoint telemetry to discover unsanctioned AI tools, browser extensions, API-level agents. Classify findings by risk tier.
- Rogue Agent Detection & Investigation: Alerts related to autonomous agents, anomalous tool chains, unexpected data access, credential misuse, agent-based attack patterns (OpenClaw, etc.).
- AI Data Exfiltration Detection & DLP: Monitor DLP and AI logs for sensitive data leaving through AI tools (prompts, uploads, plugins, MCP connectors). Tune detection rules.
- Developer AI Tool Governance: Monitor developer-facing AI tools (GitHub Copilot, Claude Code, Codex) for compliance, credential exposure, non-human identity risk.
- AI Logging, Retention & Audit Support: Evidence supporting ISO 42001 audits, EU AI Act readiness, internal AI impact assessments.
- Detection Tuning: MITRE ATT&CK, MITRE ATLAS, OWASP LLM Top 10. Scripting in Python, SQL, SPL/KQL.
- Hands-on AI/LLM risk testing: prompt injection testing, model/agent misuse, agent tool-use pipelines (LangChain, AutoGen, CrewAI, MCP servers).
"""

keywords = _extract_keywords(ALPHASENSE_JD, limit=25)
print("Extracted Keywords:", keywords)

# 2. Formulate Tailored Resume Text (1-Page Packed, Truthful, Highly Relevant)
RESUME_TEXT = """DRUPADH SURESH
Chicago, IL | +91 9980993977 | sureshdrupadh@gmail.com | linkedin.com/in/drupadhsuresh | github.com/Drupadh

SUMMARY
AI Security Analyst & SecOps Engineer with 5 years of experience detecting, investigating, and mitigating cyber risk across enterprise AI models, autonomous agents, SaaS ecosystems, and cloud environments. Proven expertise hunting shadow AI tools and rogue agent behaviors, analyzing prompt injection vectors and data exfiltration channels across LLM workflows (MCP connectors, APIs, plugins), and governing non-human identities (OAuth tokens, service accounts). Strong hands-on background operating CASB/SWG, DLP, and SIEM platforms (Splunk, Microsoft Sentinel), tuning detection logic against MITRE ATLAS and OWASP LLM Top 10 frameworks, and structuring audit-ready evidence for ISO 42001 and ISO 27001 certifications. Proficient in Python, SQL, and API telemetry analysis; available 100% remote with full IST/US shift flexibility.

TECHNICAL SKILLS
AI & LLM Security: Shadow AI Discovery, Rogue Agent Detection, Prompt Injection Testing, Model Misuse Investigation, MCP Connectors, Agent Tool Chains, OWASP LLM Top 10, MITRE ATLAS, ISO 42001, AI Data Exfiltration & DLP
Security Operations & Telemetry: CASB / SWG, Splunk, Microsoft Sentinel, EDR/XDR, Non-Human Identity Governance (OAuth, Service Accounts, API Keys), Threat Hunting, Incident Containment, Root Cause Analysis
Infrastructure & Tooling: Python, REST APIs, SQL, SPL / KQL, AWS Security, Azure Infrastructure, Docker, Git, CI/CD Security, Linux / macOS Shell
Compliance & Governance: ISO 42001, EU AI Act Readiness, SOC 2 Type II, ISO 27001, NIST CSF, AI Risk Assessments, Audit Evidence Collection

EXPERIENCE
Cybersecurity Analyst (AI Risk & Cloud SecOps) | PNC Financial Services | Jul 2025 – Present | Chicago, IL
• Monitored enterprise application and cloud telemetry across AWS and SaaS environments to detect unsanctioned AI tools, unauthorized browser extensions, and rogue API-level agents, categorizing risks and enforcing governance containment.
• Investigated high-risk alerts involving autonomous workflows, non-human service accounts, and OAuth token sprawl, identifying anomalous tool-chain executions and preventing unauthorized data exfiltration.
• Evaluated LLM and agentic integrations against OWASP LLM Top 10 risks (prompt injection, insecure plugin design, sensitive information disclosure), collaborating with engineering teams to tune DLP filters and security guardrails.
• Built automated Python and SQL scripts to correlate SIEM telemetry (Splunk/Sentinel) and API logs, reducing false-positive rates by 30% and generating verifiable evidence for corporate risk assessments and compliance audits.

Independent AI Security Researcher | HackerOne / Bug Bounty | Jan 2024 – Present | Remote
• Conducted vulnerability research and threat modeling on modern LLM applications, API gateways, and agent tool-use pipelines, focusing on prompt injection bypasses, SSRF via MCP/plugins, and privilege escalation via API keys.
• Documented reproducible proof-of-concept exploits mapped to MITRE ATLAS, delivering remediation guidance on input sanitization, token scoping, and non-human identity protection.

Associate Software Engineer (Cybersecurity & Risk) | Accenture | Aug 2022 – May 2023 | Bengaluru, India
• Operated CASB, DLP, and SIEM monitoring across enterprise systems, triaging data leak alerts and enforcing corporate DLP policies on cloud storage and collaboration tooling.
• Governed non-human identities, OAuth permissions, and privileged service accounts across enterprise directories, leading technical evidence collection for ISO 27001 and SOC 2 Type II audits.
• Investigated anomalous user activities, credential misuse, and phishing campaigns, developing incident response playbooks and detection logic.

Associate Cybersecurity Analyst | CodeNest Solution | Jul 2021 – Jul 2022 | Bengaluru, India
• Conducted automated vulnerability assessments and configuration reviews across 30+ endpoints and cloud workloads using Nessus and OpenVAS.
• Administered access control policies and identity baselines for 200+ accounts, ensuring least-privilege enforcement and secure credential storage.

EDUCATION
Master of Science in Cybersecurity | DePaul University | Graduated Jun 2025 | Chicago, IL
Bachelor of Engineering in Computer Science | PES College of Engineering | Graduated Jul 2022 | Mandya, India
"""

# 3. Formulate Tailored Cover Letter Text
COVER_LETTER_TEXT = """DRUPADH SURESH
Chicago, IL | +91 9980993977 | sureshdrupadh@gmail.com | linkedin.com/in/drupadhsuresh

September 30, 2026

Hiring Team, AI Security & Governance
AlphaSense
Remote (India)

Dear AlphaSense Hiring Team,

I am writing to express my enthusiastic interest in the AI Security Analyst position at AlphaSense. As enterprise organizations increasingly entrust critical decision-making to AlphaSense’s market intelligence platform, securing every AI model, autonomous agent, and LLM integration touching your environment is paramount. With 5 years of cybersecurity analysis and SecOps experience, coupled with focused expertise investigating AI/LLM risks, non-human identities, and data exfiltration paths, I am eager to contribute directly to AlphaSense’s AI security posture and ISO 42001 certification journey.

In my recent work at PNC Financial Services and prior enterprise environments, I have specialized in turning complex telemetry into actionable security intelligence. I have monitored enterprise CASB/SWG, OAuth authorizations, and endpoint logs to discover shadow AI usage and unsanctioned tool deployments, establishing risk-tiered escalation paths for immediate containment. Furthermore, I have actively investigated threat scenarios unique to modern agentic systems—such as anomalous tool chains, credential misuse across service accounts, and prompt injection vectors that could lead to sensitive data leakage via MCP connectors or plugins. By tuning SIEM detection rules across Splunk and Sentinel and aligning alert logic with the MITRE ATLAS and OWASP LLM Top 10 frameworks, I have consistently driven down false positives while expanding coverage against novel attack surfaces.

My investigative approach is grounded in rigorous technical analysis and code. I regularly write Python and SQL scripts to query structured API telemetry, automate log correlation, and construct verifiable evidence repositories needed for ISO 42001 audits and EU AI Act readiness. Additionally, as an Indian citizen physically based in the US, I possess full legal work authorization with zero visa sponsorship requirements, along with the proven independence to thrive in a 100% remote-first team across flexible or overlapping IST schedules.

I welcome the opportunity to discuss how my hands-on AI security experience, threat investigation skills, and governance mindset can help safeguard AlphaSense’s AI environment from day one. Thank you for your time and consideration.

Sincerely,

Drupadh Suresh
"""

def generate_docs():
    print("Generating AlphaSense AI Security Analyst Tailored Resume & Cover Letter...")
    
    # Calculate match percentage
    matched_keywords = [k for k in keywords if k.lower() in RESUME_TEXT.lower()]
    match_pct = round((len(matched_keywords) / len(keywords)) * 100) if keywords else 0
    print(f"\nTarget Match Score: {match_pct}% ({len(matched_keywords)}/{len(keywords)} keywords matched)")
    print("Matched:", matched_keywords)

    # 1. Render Resume PDF
    resume_pdf_path = OUTPUT_DIR / "Drupadh_Suresh_AlphaSense_Resume.pdf"
    res_result = render_document_pdf(
        RESUME_TEXT,
        str(resume_pdf_path),
        title="Drupadh Suresh - Resume",
        kind="resume"
    )
    print(f"Generated Resume PDF: ok={res_result.get('ok')}, pages={res_result.get('pageCount')}, size={res_result.get('byteSize')} bytes -> {resume_pdf_path}")
    
    # Copy to Desktop and Brain
    desktop_resume = Path("C:/Users/Dru/Desktop/Drupadh_Suresh_AlphaSense_Resume.pdf")
    desktop_resume.write_bytes(resume_pdf_path.read_bytes())
    brain_resume = Path("C:/Users/Dru/.gemini/antigravity/brain/79a5ce0f-1e67-4845-88bf-38b63d6a6a02/Drupadh_Suresh_AlphaSense_Resume.pdf")
    brain_resume.write_bytes(resume_pdf_path.read_bytes())
    print(f"Copied Resume to Desktop: {desktop_resume}")
    
    # 2. Render Cover Letter PDF
    cover_pdf_path = OUTPUT_DIR / "Drupadh_Suresh_AlphaSense_Cover_Letter.pdf"
    cl_result = render_document_pdf(
        COVER_LETTER_TEXT,
        str(cover_pdf_path),
        title="Drupadh Suresh - Cover Letter",
        kind="cover_letter"
    )
    print(f"Generated Cover Letter PDF: ok={cl_result.get('ok')}, pages={cl_result.get('pageCount')}, size={cl_result.get('byteSize')} bytes -> {cover_pdf_path}")
    
    # Copy to Desktop and Brain
    desktop_cover = Path("C:/Users/Dru/Desktop/Drupadh_Suresh_AlphaSense_Cover_Letter.pdf")
    desktop_cover.write_bytes(cover_pdf_path.read_bytes())
    brain_cover = Path("C:/Users/Dru/.gemini/antigravity/brain/79a5ce0f-1e67-4845-88bf-38b63d6a6a02/Drupadh_Suresh_AlphaSense_Cover_Letter.pdf")
    brain_cover.write_bytes(cover_pdf_path.read_bytes())
    print(f"Copied Cover Letter to Desktop: {desktop_cover}")

    # 3. Generate PNG previews for inspection
    from playwright.sync_api import sync_playwright
    from backend.src.tools.tsenta_documents import _document_html
    BRAIN_DIR = Path(r"C:\Users\Dru\.gemini\antigravity\brain\79a5ce0f-1e67-4845-88bf-38b63d6a6a02")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        # Preview resume
        page = browser.new_page(viewport={"width": 850, "height": 1100})
        page.set_content(_document_html(RESUME_TEXT, "Drupadh Suresh - Resume", "resume"))
        preview_res_png = BRAIN_DIR / "preview_alphasense_resume.png"
        page.screenshot(path=str(preview_res_png), full_page=True)
        print(f"Saved resume preview: {preview_res_png}")

        # Preview cover letter
        page.set_content(_document_html(COVER_LETTER_TEXT, "Drupadh Suresh - Cover Letter", "cover_letter"))
        preview_cov_png = BRAIN_DIR / "preview_alphasense_cover_letter.png"
        page.screenshot(path=str(preview_cov_png), full_page=True)
        print(f"Saved cover letter preview: {preview_cov_png}")
        browser.close()

    print("[SUCCESS] All tailored documents and visual previews successfully created!")

if __name__ == "__main__":
    generate_docs()
