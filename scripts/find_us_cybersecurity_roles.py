"""
Fetch strictly US-based cybersecurity roles at popular cybersecurity companies.
Extracts:
- Company Name
- Job Title
- Official Job ID / Requisition ID
- Location (US specific: Remote, Hybrid, In-Person)
- Direct Official Company Website Careers URL
"""

import sys
import os
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GH_TARGETS = {
    'Zscaler': ('zscaler', 'https://job-boards.greenhouse.io/zscaler/jobs/{id}'),
    'Okta': ('okta', 'https://www.okta.com/company/careers/opportunity/{id}'),
    'Cloudflare': ('cloudflare', 'https://www.cloudflare.com/careers/jobs/?gh_jid={id}'),
    'Datadog': ('datadog', 'https://careers.datadoghq.com/detail/{id}/'),
    'Elastic': ('elastic', 'https://www.elastic.co/careers/jobs/{id}'),
    'Rubrik': ('rubrik', 'https://www.rubrik.com/company/careers/departments/job.{id}'),
    'Netskope': ('netskope', 'https://www.netskope.com/company/careers/jobs/{id}'),
    'Abnormal Security': ('abnormalsecurity', 'https://abnormal.ai/careers/jobs/{id}'),
    'Huntress': ('huntress', 'https://www.huntress.com/careers?gh_jid={id}'),
    'KnowBe4': ('knowbe4', 'https://www.knowbe4.com/careers?gh_jid={id}'),
    'Axonius': ('axonius', 'https://job-boards.greenhouse.io/axonius/jobs/{id}')
}

ASHBY_TARGETS = {
    'Vanta': ('vanta', 'https://www.vanta.com/careers?jobId={id}', 'https://jobs.ashbyhq.com/vanta/{id}'),
    'Drata': ('drata', 'https://drata.com/careers?jobId={id}', 'https://jobs.ashbyhq.com/drata/{id}'),
    'Snyk': ('snyk', 'https://snyk.io/careers?jobId={id}', 'https://jobs.ashbyhq.com/snyk/{id}'),
    'Material Security': ('materialsecurity', 'https://material.security/careers?jobId={id}', 'https://jobs.ashbyhq.com/materialsecurity/{id}')
}

SEC_KEYWORDS = [
    'security', 'risk', 'grc', 'compliance', 'tprm', 'third party',
    'cloud security', 'soc', 'incident', 'vulnerability', 'infosec',
    'threat', 'trust', 'cyber', 'detection'
]

NEGATIVES = [
    'sales', 'account executive', 'bdr', 'sdr', 'recruiter', 'marketing',
    'legal counsel', 'tax', 'payroll', 'finance manager', 'customer success manager',
    'director', 'vice president', 'vp of', 'head of', 'quote', 'customer support',
    'front desk', 'office operations'
]

def scan_us_roles():
    us_roles = []

    # 1. Greenhouse Companies
    for company, (board, url_tmpl) in GH_TARGETS.items():
        url = f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            res = urllib.request.urlopen(req, timeout=4)
            data = json.loads(res.read().decode('utf-8'))
            for j in data.get('jobs', []):
                title = j.get('title', '')
                t_low = title.lower()
                if any(n in t_low for n in NEGATIVES):
                    continue
                if not any(k in t_low for k in SEC_KEYWORDS):
                    continue

                loc = (j.get('location', {}) or {}).get('name', '')
                l_low = loc.lower()

                # US Locations check
                is_us = any(k in l_low for k in (
                    'united states', 'usa', 'remote - usa', 'remote - us', 'remote u.s.',
                    'remote, us', 'chicago', 'il', 'san francisco', 'california', 'ca',
                    'new york', 'ny', 'austin', 'texas', 'tx', 'washington', 'dc',
                    'seattle', 'wa', 'boston', 'ma', 'virginia', 'va', 'colorado', 'co',
                    'arlington', 'remote, usa', 'remote - united states'
                )) and not any(k in l_low for k in (
                    'india', 'uk', 'united kingdom', 'ireland', 'canada', 'germany', 'france',
                    'australia', 'japan', 'brazil', 'mexico', 'netherlands', 'singapore', 'spain'
                ))

                if is_us:
                    job_id = str(j.get('id', ''))
                    comp_url = url_tmpl.format(id=job_id)
                    
                    wp = 'In-Person / Onsite'
                    if 'remote' in l_low or 'remote' in t_low:
                        wp = 'Remote'
                    elif 'hybrid' in l_low or 'hybrid' in t_low:
                        wp = 'Hybrid'

                    us_roles.append({
                        'company': company,
                        'title': title,
                        'job_id': job_id,
                        'location': loc,
                        'workplace': wp,
                        'company_url': comp_url
                    })
        except Exception:
            pass

    # 2. Ashby Companies
    for company, (board, web_tmpl, ashby_tmpl) in ASHBY_TARGETS.items():
        url = f'https://api.ashbyhq.com/posting-api/job-board/{board}'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            res = urllib.request.urlopen(req, timeout=4)
            data = json.loads(res.read().decode('utf-8'))
            for j in data.get('jobs', []):
                title = j.get('title', '')
                t_low = title.lower()
                if any(n in t_low for n in NEGATIVES):
                    continue
                if not any(k in t_low for k in SEC_KEYWORDS):
                    continue

                loc = j.get('location') or ''
                raw_wp = (j.get('workplaceType') or '').lower()
                l_low = f"{loc} {raw_wp}".lower()

                is_us = any(k in l_low for k in (
                    'united states', 'usa', 'remote u.s.', 'remote - us', 'remote us',
                    'u.s.', 'california', 'san francisco', 'new york', 'chicago'
                )) and not any(k in l_low for k in (
                    'canada', 'uk', 'united kingdom', 'ireland', 'germany', 'australia'
                ))

                if is_us:
                    job_id = str(j.get('id') or j.get('jobUrl', '').split('/')[-1])
                    comp_url = ashby_tmpl.format(id=job_id)
                    wp = 'Remote' if 'remote' in raw_wp else ('Hybrid' if 'hybrid' in raw_wp else 'In-Person / Onsite')

                    us_roles.append({
                        'company': company,
                        'title': title,
                        'job_id': job_id,
                        'location': loc,
                        'workplace': wp,
                        'company_url': comp_url
                    })
        except Exception:
            pass

    return us_roles

if __name__ == '__main__':
    roles = scan_us_roles()
    print(f"Total US Cybersecurity roles at major cyber companies: {len(roles)}")
    
    # Save to loot
    out_path = ROOT / "loot" / "us_cyber_company_roles.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(roles, f, indent=2)

    by_wp = {}
    for r in roles:
        by_wp.setdefault(r['workplace'], []).append(r)

    for wp in ['Remote', 'Hybrid', 'In-Person / Onsite']:
        items = by_wp.get(wp, [])
        print(f"\n==========================================")
        print(f"  US {wp.upper()} ROLES ({len(items)})")
        print(f"==========================================")
        for i, r in enumerate(items, 1):
            print(f"{i:02d}. [{r['company']}] {r['title']}")
            print(f"    Job ID: {r['job_id']}")
            print(f"    Location: {r['location']}")
            print(f"    Company Careers URL: {r['company_url']}")
