"""
Search for open Cybersecurity roles across popular cybersecurity companies and top employers.
Filters for Remote, Hybrid, and In-Person roles matching Drupadh Suresh's profile:
- 5 YOE: Cybersecurity Risk Analyst, TPRM, SOC, Cloud Security (AWS/Azure), GRC, Vulnerability Management.
- Locations: US (Chicago, Remote US), India (Bengaluru, Remote India), and Global/Remote.
"""

import sys
import os
import json
import urllib.request
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GH_COMPANIES = {
    'Zscaler': 'zscaler',
    'Cloudflare': 'cloudflare',
    'Okta': 'okta',
    'Datadog': 'datadog',
    'Elastic': 'elastic',
    'Rubrik': 'rubrik',
    'Netskope': 'netskope',
    'Abnormal Security': 'abnormalsecurity',
    'Axonius': 'axonius',
    'Huntress': 'huntress',
    'KnowBe4': 'knowbe4',
    'Cybereason': 'cybereason',
    'Druva': 'druva',
    'AlphaSense': 'alphasense'
}

ASHBY_COMPANIES = {
    'Snyk': 'snyk',
    'Drata': 'drata',
    'Vanta': 'vanta',
    'Secureframe': 'secureframe',
    'Material Security': 'materialsecurity',
    'Atlan': 'atlan',
    'Pragmatike': 'pragmatike'
}

SEC_KEYWORDS = [
    'security analyst', 'risk analyst', 'grc', 'compliance', 'tprm', 'third party',
    'cloud security', 'soc', 'incident', 'vulnerability', 'infosec', 'threat',
    'security operations', 'trust', 'information security', 'cybersecurity'
]

NEGATIVES = [
    'sales', 'account executive', 'bdr', 'sdr', 'recruiter', 'marketing',
    'legal counsel', 'tax', 'payroll', 'finance manager', 'customer success manager',
    'director', 'vice president', 'vp of', 'head of'
]

def classify_workplace(title_loc: str) -> str:
    s = title_loc.lower()
    if 'remote' in s or 'anywhere' in s or 'telecommute' in s or 'home' in s:
        return 'Remote'
    if 'hybrid' in s or 'flexible' in s:
        return 'Hybrid'
    return 'In-Person / Onsite'

def classify_region(loc: str) -> str:
    l = loc.lower()
    if any(k in l for k in ('india', 'bengaluru', 'bangalore', 'pune', 'hyderabad', 'delhi', 'mumbai', 'noida', 'gurgaon')):
        return 'India'
    if any(k in l for k in ('united states', 'us', 'usa', 'chicago', 'illinois', 'san francisco', 'new york', 'austin', 'seattle', 'boston', 'virginia')):
        return 'United States'
    if 'singapore' in l:
        return 'Singapore'
    if 'remote' in l and not any(k in l for k in ('emea', 'europe', 'uk', 'canada', 'latam', 'brazil', 'japan', 'australia')):
        return 'Remote (US/Global)'
    return 'International / Regional'

def scan_all():
    results = []

    # 1. Greenhouse
    for cname, board in GH_COMPANIES.items():
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
                if any(k in t_low for k in SEC_KEYWORDS):
                    loc = (j.get('location', {}) or {}).get('name', '') or 'Location Unspecified'
                    combined = f"{title} {loc}"
                    wp = classify_workplace(combined)
                    region = classify_region(loc)
                    results.append({
                        'company': cname,
                        'title': title,
                        'location': loc,
                        'workplace': wp,
                        'region': region,
                        'url': j.get('absolute_url'),
                        'ats': 'greenhouse'
                    })
        except Exception as e:
            pass

    # 2. Ashby
    for cname, board in ASHBY_COMPANIES.items():
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
                if any(k in t_low for k in SEC_KEYWORDS):
                    loc = j.get('location') or 'Location Unspecified'
                    raw_wp = j.get('workplaceType') or ''
                    combined = f"{title} {loc} {raw_wp}"
                    wp = raw_wp.capitalize() if raw_wp else classify_workplace(combined)
                    region = classify_region(loc)
                    results.append({
                        'company': cname,
                        'title': title,
                        'location': loc,
                        'workplace': wp,
                        'region': region,
                        'url': j.get('jobUrl'),
                        'ats': 'ashby'
                    })
        except Exception as e:
            pass

    return results

if __name__ == '__main__':
    jobs = scan_all()
    print(f"Total matched cybersecurity roles found: {len(jobs)}")
    
    # Save to loot
    out_file = ROOT / "loot" / "popular_cyber_roles.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2)
    print(f"Saved full job list to {out_file}")

    # Exclude non-security or junior support titles
    non_sec = ['quote', 'customer support', 'counsel', 'ethics and compliance manager',
               'tax', 'sales', 'product manager', 'customer success']
    clean_jobs = [j for j in jobs if not any(n in j['title'].lower() for n in non_sec)]
    print(f"Total highly targeted technical cybersecurity roles: {len(clean_jobs)}")

    # Breakdown by Region and Workplace
    by_cat = {}
    for j in clean_jobs:
        reg = j['region']
        wp = j['workplace']
        key = f"{reg} | {wp}"
        by_cat.setdefault(key, []).append(j)

    for cat in sorted(by_cat.keys()):
        items = by_cat[cat]
        print(f"\n==========================================")
        print(f"  {cat.upper()} ({len(items)} roles)")
        print(f"==========================================")
        for i, item in enumerate(items[:6], 1):
            co = item['company']
            ti = item['title']
            loc = item['location']
            u = item['url']
            print(f"  {i:02d}. [{co}] {ti}")
            print(f"      Location: {loc}")
            print(f"      Apply URL: {u}")
