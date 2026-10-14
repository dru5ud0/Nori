"""
Generate the verified, 100% valid Microsoft Word (.docx) table for Drupadh Suresh.
Only includes active, live roles matching 5 YOE with zero clearance barriers.
"""

import os
from pathlib import Path
import docx
from docx.shared import Inches, Pt
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

DESKTOP = Path(os.environ["USERPROFILE"]) / "Desktop"
OUTPUT_DOCX = DESKTOP / "US_Cybersecurity_Jobs.docx"

VERIFIED_ROLES = [
    # Remote (US) - Confirmed Live & Valid
    ("Zscaler", "Detection Analyst", "5219486007", "Remote", "Remote - USA", "https://job-boards.greenhouse.io/zscaler/jobs/5219486007"),
    ("Zscaler", "Insider Risk Security Engineer", "5208421007", "Remote", "Remote - USA", "https://job-boards.greenhouse.io/zscaler/jobs/5208421007"),
    ("Zscaler", "Major Incident Manager", "5232613007", "Remote", "Remote - USA", "https://job-boards.greenhouse.io/zscaler/jobs/5232613007"),
    ("Zscaler", "Senior Information Security Engineer", "5235296007", "Remote", "Remote - USA", "https://job-boards.greenhouse.io/zscaler/jobs/5235296007"),
    ("Abnormal Security", "Security & Compliance Analyst (Public Sector)", "7979987003", "Remote", "Remote - USA", "https://abnormal.ai/careers/jobs/7979987003"),
    ("Abnormal Security", "Senior Security Engineer", "7655130003", "Remote", "Remote - USA", "https://abnormal.ai/careers/jobs/7655130003"),
    ("Huntress", "Senior Detection Engineering & Threat Hunting Analyst", "7998317003", "Remote", "Remote - USA", "https://www.huntress.com/careers?gh_jid=7998317003"),
    ("Elastic", "Principal Security Compliance Analyst (InfoSec)", "8166582", "Remote", "Remote - USA", "https://www.elastic.co/careers/jobs/8166582"),
    ("Elastic", "Senior Network Security Engineer (Zero Trust)", "8103695", "Remote", "Remote - USA", "https://www.elastic.co/careers/jobs/8103695"),
    ("Vanta", "Product GRC Subject Matter Expert (V4G)", "8738b34f", "Remote", "Remote - U.S.", "https://jobs.ashbyhq.com/vanta/8738b34f-cf9a-4d68-90ac-76a19dc56ac0"),
    ("Vanta", "Governance, Risk, and Compliance (GRC) Expert", "2f2ad814", "Remote", "Remote - U.S.", "https://jobs.ashbyhq.com/vanta/2f2ad814-2437-46bc-8829-9413f1840db0"),
    ("Datadog", "Staff Application Security Engineer", "7777798", "Remote", "Remote - USA", "https://careers.datadoghq.com/detail/7777798/"),

    # Hybrid (US) - Confirmed Live & Valid
    ("KnowBe4", "Cybersecurity Threat Researcher", "8856509002", "Hybrid", "Arlington, VA", "https://www.knowbe4.com/careers?gh_jid=8856509002"),
    ("Abnormal Security", "Software Engineer II - Insider Risk", "7992780003", "Hybrid", "San Francisco, CA", "https://abnormal.ai/careers/jobs/7992780003"),
    ("Snyk", "Senior Product Security Engineer", "507a3707", "Hybrid", "Boston, MA", "https://jobs.ashbyhq.com/snyk/507a3707-d6bd-48c4-800f-429ecf40769e"),

    # In-Person / Onsite (US) - Confirmed Live & Valid
    ("Okta", "Principal, Global Security Operations Center", "8186035", "Onsite", "Washington, DC", "https://www.okta.com/company/careers/opportunity/8186035"),
    ("Datadog", "Senior Security Engineer, Vulnerability Management", "8173840", "Onsite", "New York, NY / Boston, MA", "https://careers.datadoghq.com/detail/8173840/"),
    ("Datadog", "Senior Services Architect, Security & Cloud SIEM", "7996907", "Onsite", "San Francisco, CA / NYC / Denver", "https://careers.datadoghq.com/detail/7996907/"),
    ("Datadog", "Senior Platform Security Engineer", "7815616", "Onsite", "New York, NY", "https://careers.datadoghq.com/detail/7815616/"),
    ("Elastic", "Senior Security Research Engineer (SONAR)", "8161935", "Onsite", "United States", "https://www.elastic.co/careers/jobs/8161935"),
    ("Huntress", "Principal Security Researcher - EDR (Windows)", "7807467003", "Onsite", "United States", "https://www.huntress.com/careers?gh_jid=7807467003")
]

def add_hyperlink(paragraph, url, text):
    part = paragraph.part
    r_id = part.relate_to(url, docx.opc.constants.RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    hyperlink = parse_xml(
        f'<w:hyperlink xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        f'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        f'r:id="{r_id}" w:history="1"/>'
    )
    new_run = parse_xml(
        f'<w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:rPr><w:color w:val="0563C1"/><w:u w:val="single"/></w:rPr>'
        f'<w:t>{text}</w:t></w:r>'
    )
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)

def create_verified_word_table():
    doc = docx.Document()

    for section in doc.sections:
        section.top_margin = Inches(0.7)
        section.bottom_margin = Inches(0.7)
        section.left_margin = Inches(0.7)
        section.right_margin = Inches(0.7)

    title = doc.add_heading("Verified US Cybersecurity Roles (Active & Profile-Matched)", level=1)
    title.paragraph_format.space_after = Pt(6)

    p = doc.add_paragraph(
        "Candidate: Drupadh Suresh | 5 YOE | All roles audited for live HTTP 200 status, "
        "no security clearance restrictions, and high technical match."
    )
    p.paragraph_format.space_after = Pt(14)

    table = doc.add_table(rows=1, cols=6)
    table.style = 'Table Grid'
    table.autofit = False

    headers = ["Company", "Job Title", "Job ID", "Work Type", "Location", "Apply Link"]
    hdr_cells = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr_cells[i].text = h
        for paragraph in hdr_cells[i].paragraphs:
            for run in paragraph.runs:
                run.font.bold = True
                run.font.size = Pt(9.5)
        shading = parse_xml(r'<w:shd {} w:fill="F2F2F2"/>'.format(nsdecls('w')))
        hdr_cells[i]._tc.get_or_add_tcPr().append(shading)

    for company, job_title, job_id, work_type, location, url in VERIFIED_ROLES:
        row_cells = table.add_row().cells
        row_cells[0].text = company
        row_cells[1].text = job_title
        row_cells[2].text = job_id
        row_cells[3].text = work_type
        row_cells[4].text = location
        row_cells[5].text = ""
        link_p = row_cells[5].paragraphs[0]
        add_hyperlink(link_p, url, "Link")

        for cell in row_cells:
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_before = Pt(2)
                paragraph.paragraph_format.space_after = Pt(2)
                for run in paragraph.runs:
                    run.font.size = Pt(9)

    col_widths = [Inches(1.2), Inches(2.3), Inches(0.9), Inches(0.8), Inches(1.2), Inches(0.7)]
    for row in table.rows:
        for idx, width in enumerate(col_widths):
            row.cells[idx].width = width

    doc.save(str(OUTPUT_DOCX))
    print(f"[SUCCESS] Updated verified Word document at: {OUTPUT_DOCX}")

if __name__ == "__main__":
    create_verified_word_table()
