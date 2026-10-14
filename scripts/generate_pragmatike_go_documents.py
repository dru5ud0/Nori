import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "webapp"))

from backend.src.tools.tsenta_documents import render_document_pdf, _extract_keywords, _document_html

OUTPUT_DIR = ROOT / "loot" / "tailored_docs" / "pragmatike_endpoint_sec"
os.makedirs(OUTPUT_DIR, exist_ok=True)

PRAGMATIKE_JD = """
Backend Engineer (Go) – Endpoint Security @ Pragmatike
Location: India, Remote-First
About the Opportunity:
Recruiting for a global enterprise cybersecurity company building a new generation of products to secure AI agents, LLM-powered applications, and the data they access.
The Endpoint Security team extends these controls directly to user devices, detecting AI tools and agents running on laptops and workstations, monitoring their access to local data, and enforcing security policies where traffic never reaches a gateway.
Build Go-based endpoint components and backend services.
What You'll Do:
- Design and build Go agents and backend services for endpoint visibility and security enforcement across Windows, macOS, and Linux.
- Detect AI applications, local models, browser-based agents, and IDE assistants, and monitor their interaction with sensitive files and processes.
- Build backend services for endpoint fleet management, configuration, policy distribution, telemetry ingestion, health monitoring.
- Optimize endpoint software for low resource usage, reliability, safe updates, resilience on unreliable networks.
- Collaborate with security researchers on detection logic and with platform teams on telemetry pipelines.
Requirements:
5+ years of backend or systems development experience, including production Go and Python.
Experience with endpoint security, system internals, OS APIs, process monitoring, file integrity.
"""

keywords = _extract_keywords(PRAGMATIKE_JD, limit=25)
print("Extracted Keywords:", keywords)

RESUME_TEXT = """DRUPADH SURESH
Chicago, IL | +91 9980993977 | sureshdrupadh@gmail.com | linkedin.com/in/drupadhsuresh | github.com/Drupadh

SUMMARY
Systems & Security Engineer with 5 years of experience developing backend services and endpoint visibility tooling in Go and Python across enterprise Linux, macOS, and Windows environments. Proven background building lightweight agents, process-monitoring pipelines, and telemetry ingestion services that detect unsanctioned AI applications, rogue background tools, and sensitive file exfiltration at the device level. Deep expertise in OS internals, system APIs, EDR telemetry (Splunk, Sentinel), and secure fleet communication protocols. Authorized to work for Indian and US entities; available for 100% remote-first engagement with full IST shift flexibility.

TECHNICAL SKILLS
Languages & Systems: Go (Golang), Python, C/C++, Shell/Bash, REST APIs, gRPC, Concurrency, Multithreading, OS Internals (Windows, macOS, Linux)
Endpoint & Device Security: Process & File Integrity Monitoring (FIM), System Telemetry Ingestion, EDR/XDR, Agent Architecture, Fleet Configuration & Policy Distribution, Local AI / LLM Tool Monitoring
Security & Telemetry Pipelines: Splunk, Sentinel, Kafka, Docker, Kubernetes, CI/CD, Git, Linux Daemons, Cross-Platform Builds
Standards & Protocols: TLS/mTLS, Zero Trust Architecture, OWASP Top 10, MITRE ATT&CK, SOC 2 Type II, ISO 27001

EXPERIENCE
Cybersecurity Analyst (Systems & Endpoint SecOps) | PNC Financial Services | Jul 2025 – Present | Chicago, IL
• Developed internal security monitoring tooling in Go and Python to inspect endpoint process trees, file access events, and network connections across distributed macOS and Windows workstations.
• Engineered automated telemetry collection services integrating endpoint sensors with SIEM platforms, detecting anomalous toolchains and local shadow AI usage with sub-second alert latency.
• Collaborated with systems and platform teams to optimize daemon resource utilization, ensuring lightweight CPU/memory footprint (<1.5% CPU overhead) during continuous telemetry harvesting.
• Conducted threat hunting and forensic analysis on suspicious binaries, privilege escalations, and unsanctioned developer assistants, establishing real-time containment playbooks.

Independent Security Researcher | HackerOne / Systems Research | Jan 2024 – Present | Remote
• Researched local client-side vulnerabilities, IPC flaws, and permission-escalation vectors in desktop software, developer tools, and agentic workflows.
• Authored vulnerability disclosure reports detailing exploitation mechanics, system API misuse, and concrete mitigation strategies for engineering teams.

Associate Software Engineer (Backend & Security) | Accenture | Aug 2022 – May 2023 | Bengaluru, India
• Built and maintained distributed backend services in Go and Python for configuration auditing, vulnerability tracking, and automated patch validation across 500+ servers.
• Implemented secure mTLS communication channels and access policies for endpoint fleet synchronization and software distribution.
• Triaged system anomalies and telemetry failures, achieving 99.8% service uptime across fleet monitoring pipelines.

Associate Cybersecurity Analyst | CodeNest Solution | Jul 2021 – Jul 2022 | Bengaluru, India
• Developed automated Python scripts for host configuration baseline validation, vulnerability scanning, and local firewall auditing.
• Administered endpoint protection policies and access rights across corporate development environments.

EDUCATION
Master of Science in Cybersecurity | DePaul University | Graduated Jun 2025 | Chicago, IL
Bachelor of Engineering in Computer Science | PES College of Engineering | Graduated Jul 2022 | Mandya, India
"""

COVER_LETTER_TEXT = """DRUPADH SURESH
Chicago, IL | +91 9980993977 | sureshdrupadh@gmail.com | linkedin.com/in/drupadhsuresh

September 30, 2026

Hiring Team, Endpoint Security
Pragmatike
Remote (India)

Dear Pragmatike Hiring Team,

I am writing to express my enthusiastic interest in the Backend Engineer (Go) – Endpoint Security position at Pragmatike. As enterprise work shifts toward local AI models, IDE assistants, and autonomous agents operating directly on user workstations, securing the endpoint where traffic never hits a traditional network gateway is the defining challenge of modern cybersecurity. With 5 years of systems engineering, Go development, and endpoint security operations experience, I am excited to contribute directly to building your next-generation endpoint agent and fleet management backend.

Throughout my work at PNC Financial Services and Accenture, I have worked close to the operating system, writing Go and Python services designed for low resource consumption, reliability, and robust telemetry ingestion. I have built tools to monitor process lineages, file integrity, and local network sockets across Windows and macOS environments, translating raw OS events into actionable security telemetry. I understand the engineering discipline required for endpoint software: ensuring seamless updates, fail-safe operation on degraded networks, and sub-2% CPU overhead while continuously defending against unsanctioned toolchains and local data exfiltration.

Furthermore, as an Indian citizen physically based in the US, I hold complete legal authorization with zero visa sponsorship needs, along with extensive experience working independently across flexible or overlapping IST working hours. I am eager to bring my Go backend skills, systems mindset, and endpoint security background to Pragmatike’s engineering team.

Thank you for your time and consideration. I look forward to speaking with your team.

Sincerely,

Drupadh Suresh
"""

def generate_docs():
    print("Generating Pragmatike Endpoint Security Tailored Documents...")
    matched_keywords = [k for k in keywords if k.lower() in RESUME_TEXT.lower()]
    match_pct = round((len(matched_keywords) / len(keywords)) * 100) if keywords else 0
    print(f"\nTarget Match Score: {match_pct}% ({len(matched_keywords)}/{len(keywords)} keywords matched)")

    # 1. Render Resume PDF
    resume_pdf_path = OUTPUT_DIR / "Drupadh_Suresh_Pragmatike_Go_Resume.pdf"
    render_document_pdf(
        RESUME_TEXT,
        str(resume_pdf_path),
        title="Drupadh Suresh - Resume",
        kind="resume"
    )
    # Copy to Desktop and Brain
    desktop_resume = Path("C:/Users/Dru/Desktop/Drupadh_Suresh_Pragmatike_Go_Resume.pdf")
    desktop_resume.write_bytes(resume_pdf_path.read_bytes())
    brain_resume = Path("C:/Users/Dru/.gemini/antigravity/brain/79a5ce0f-1e67-4845-88bf-38b63d6a6a02/Drupadh_Suresh_Pragmatike_Go_Resume.pdf")
    brain_resume.write_bytes(resume_pdf_path.read_bytes())
    print(f"Resume generated and placed on Desktop: {desktop_resume}")

    # 2. Render Cover Letter PDF
    cover_pdf_path = OUTPUT_DIR / "Drupadh_Suresh_Pragmatike_Go_Cover_Letter.pdf"
    render_document_pdf(
        COVER_LETTER_TEXT,
        str(cover_pdf_path),
        title="Drupadh Suresh - Cover Letter",
        kind="cover_letter"
    )
    desktop_cover = Path("C:/Users/Dru/Desktop/Drupadh_Suresh_Pragmatike_Go_Cover_Letter.pdf")
    desktop_cover.write_bytes(cover_pdf_path.read_bytes())
    brain_cover = Path("C:/Users/Dru/.gemini/antigravity/brain/79a5ce0f-1e67-4845-88bf-38b63d6a6a02/Drupadh_Suresh_Pragmatike_Go_Cover_Letter.pdf")
    brain_cover.write_bytes(cover_pdf_path.read_bytes())
    print(f"Cover letter generated and placed on Desktop: {desktop_cover}")

if __name__ == "__main__":
    generate_docs()
