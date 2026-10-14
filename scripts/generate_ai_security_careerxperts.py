"""
Generate tailored 1-Page PDF Resume, Cover Letter, and Email Application for:
Role: AI Security Engineer (3–5 yrs) | Bengaluru
Client / Recruiter: Careerxperts (Agentic AI Guardrail Startup)
Email: AISecurity@Careerxperts.com
"""

import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend" / "src"))
sys.path.insert(0, str(ROOT / "backend" / "src" / "tools"))

from backend.src.tools.tsenta_documents import render_document_pdf
from backend.src.tools.tsenta_llm import chat_completion, llm_config

DESKTOP = Path(os.environ["USERPROFILE"]) / "Desktop"

RESUME_TEXT = """DRUPADH SURESH
Bengaluru, Karnataka, India | +91 9980993977 | sureshdrupadh@gmail.com | linkedin.com/in/drupadhsuresh | github.com/Drupadh

PROFESSIONAL SUMMARY
Cybersecurity & Detection Engineer with 5 years of experience across EDR/XDR telemetry, OS internals (Windows/Linux), behavioral attack analysis, and agentic AI architectures. Proven background in hunting endpoint abuse, writing custom detection logic for process execution and shell parentage, and analyzing the full LLM attack surface (prompt -> agent -> tool call -> shell execution -> exfiltration). B.E. in Computer Science and M.S. in Cybersecurity (DePaul University).

CORE TECHNICAL SKILLS
* AI & Agentic Security: LLM Prompt Injection Defenses, Model Context Protocol (MCP) Audit, Tool-Use Hijacking, Agent Trace Analysis, Sandboxing & Guardrails.
* Detection Engineering & Telemetry: EDR/XDR Behavioral Detections, Process Trees & Command-Line Telemetry, MITRE ATT&CK, Parent-Child Process Anomaly Hunting.
* Systems & Scripting: Windows & Linux Internals, Python, PowerShell, Bash, Regex, API Security, Process Monitoring (Sysmon/Auditd).
* Security Operations & Cloud: SIEM (Splunk, Microsoft Sentinel), Palo Alto Prisma Cloud, AWS/Azure IAM, Vulnerability Management (Nessus, Qualys).
* Certifications: CompTIA Security+, Cisco CCNA, Microsoft SC-900.

EXPERIENCE
PNC Financial Services | Cybersecurity Analyst (SOC & Detection)
Chicago, IL | Jul 2025 – Present
* Triaged and investigated 50+ endpoint and network security alerts per shift across EDR, SIEM, and NGFW systems, correlating suspicious process trees, unusual PowerShell/Bash invocations, and IOCs.
* Developed detection queries and operational threat dashboards across SIEM and telemetry sources, identifying Living-off-the-Land (LotL) execution patterns and anomalous credential access.
* Partnered with infrastructure and cloud engineering to validate security baselines across AWS/Azure environments, automating compliance and remediation pipelines via Security-as-Code.
* Evaluated third-party application attack surfaces and vendor access vectors, mapping threat vectors to NIST CSF and MITRE ATT&CK frameworks.

HackerOne | Independent Security Researcher (AI & Web Workflows)
Remote | 2026 – Present
* Researched emerging attack techniques targeting AI-assisted developer workflows, tool-calling APIs, and OAuth integrations, analyzing execution paths from prompt input to backend execution.
* Constructed reproducible proofs-of-concept (PoCs) demonstrating token race conditions, webhook injection, and unauthorized API invocation across public bug bounty scopes.
* Documented precise attack scenarios, CVSS scoring, and actionable engineering remediation for product teams.

Accenture | Cybersecurity Analyst (Associate Software Engineer)
Bengaluru, India | Aug 2022 – May 2023
* Monitored enterprise SIEM events, analyzing endpoint telemetry for anomalous process execution, command-line obfuscation, and unauthorized network egress.
* Supported incident response investigations into malware, credential theft, and script-based intrusions, reconstructing chronological activity across endpoint event logs.
* Coordinated vulnerability assessments and remediation workflows across 30+ production systems.

CodeNest Solution | Associate Cybersecurity Analyst
Bengaluru, India | Jul 2021 – Jul 2022
* Conducted vulnerability assessments and endpoint compliance reviews, tracking remediation of high-severity CVEs across Windows and Linux environments.

EDUCATION
* DePaul University (Chicago, IL) – M.S. in Cybersecurity, Network Security Focus (2025)
* P.E.S.C.E (Karnataka, India) – B.E. in Computer Science & Engineering (2022)
"""

COVER_LETTER_TEXT = """Drupadh Suresh
Indiranagar, Bengaluru, Karnataka, India
+91 9980993977 | sureshdrupadh@gmail.com | linkedin.com/in/drupadhsuresh

To: Hiring Team / Careerxperts
Re: Application for AI Security Engineer (3–5 yrs) | Bengaluru (Ref: AISecurity@Careerxperts.com)

Dear Hiring Team,

I am writing to express my strong enthusiasm for the AI Security Engineer position in Bengaluru. When employee endpoints run autonomous coding agents and agentic apps like Claude Code, Codex, and Claude Cowork, the perimeter collapses into the agent's execution loop: prompt -> agent -> tool call -> shell -> process -> file/network -> exfiltration. Defending this exact chain requires a practitioner who understands both deep endpoint telemetry and how modern AI agents reason, invoke tools, and interface with the operating system.

Over my 5 years in cybersecurity engineering—complemented by a Master’s in Cybersecurity from DePaul University and a Computer Science degree—I have focused heavily on detection engineering, EDR/XDR behavioral telemetry, and Windows/Linux internals:

1. Behavioral Detection Across EDR & Process Trees: At PNC Financial Services and Accenture, I analyzed high-volume telemetry across SIEM and EDR platforms, hunting for anomalous command-line arguments, suspicious parent-child process lineage (e.g., dev runtimes spawning unmonitored shells), and living-off-the-land techniques.
2. Defending the Agentic Attack Chain: I actively study and model agentic risks, including indirect prompt injection via untrusted repositories, tool-calling poisoning, and Model Context Protocol (MCP) abuse where rogue servers attempt unauthorized file reads or environment credential exfiltration.
3. Rapid Scenario-to-Detection Engineering: With strong proficiency in Python, PowerShell, and OS monitoring (Sysmon, Event Logs, auditd), I enjoy turning conceptual attack vectors into concrete behavioral detection rules and programmatic guardrails that block credential/filesystem abuse without degrading developer velocity.

I am based locally in Bengaluru (Indiranagar), available on a 30-day notice period, and eager to build the foundational guardrails that protect enterprises from AI agent exploitation. I have attached my resume for your review and look forward to discussing how I can contribute to your mission.

Sincerely,
Drupadh Suresh
"""

def generate_documents():
    resume_path = DESKTOP / "Drupadh_Suresh_AI_Security_Engineer_Resume.pdf"
    cover_path = DESKTOP / "Drupadh_Suresh_AI_Security_Engineer_Cover_Letter.pdf"

    print(f"Generating 1-Page AI Security Engineer Resume -> {resume_path}...")
    res_info = render_document_pdf(RESUME_TEXT, str(resume_path), title="Drupadh Suresh - AI Security Engineer", kind="resume")
    print(f"  [Resume Result] OK: {res_info.get('ok')}, Size: {res_info.get('byteSize')} bytes")

    print(f"\nGenerating Targeted Cover Letter -> {cover_path}...")
    cov_info = render_document_pdf(COVER_LETTER_TEXT, str(cover_path), title="Cover Letter - AI Security Engineer", kind="cover_letter")
    print(f"  [Cover Letter Result] OK: {cov_info.get('ok')}, Size: {cov_info.get('byteSize')} bytes")

    return str(resume_path), str(cover_path)

if __name__ == "__main__":
    generate_documents()
