"""Dedicated scanner for open cybersecurity, risk, and analyst roles at Indian Tech Startups & Unicorns."""
import urllib.request
import json
from pathlib import Path

def get_indian_startup_jobs() -> list[dict]:
    ashby_targets = ['atlan', 'pragmatike', 'hasura', 'signoz', 'devrev', 'invideo', 'toplyne']
    gh_targets = ['alphasense', 'druva', 'highradius', 'inmobi', 'chargebee', 'whatfix', 'browserstack']
    lever_targets = ['meesho', 'razorpay', 'cred', 'groww']
    
    results = []
    
    # 1. Ashby
    for c in ashby_targets:
        url = f'https://api.ashbyhq.com/posting-api/job-board/{c}'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            data = json.loads(urllib.request.urlopen(req, timeout=4).read().decode())
            for j in data.get('jobs', []):
                loc = (j.get('location') or '').lower()
                title = (j.get('title') or '').lower()
                workplace = (j.get('workplaceType') or '').lower()
                is_in = any(k in loc for k in ('india', 'bengaluru', 'bangalore', 'pune', 'hyderabad', 'delhi', 'remote'))
                is_sec = any(k in title for k in ('security', 'risk', 'compliance', 'analyst', 'cyber', 'soc'))
                if is_sec and is_in:
                    results.append({
                        'company': c.capitalize(),
                        'title': j.get('title'),
                        'location': f"{j.get('location')} ({workplace})",
                        'url': j.get('jobUrl'),
                        'ats': 'ashby'
                    })
        except Exception:
            pass

    # 2. Greenhouse
    for c in gh_targets:
        url = f'https://boards-api.greenhouse.io/v1/boards/{c}/jobs'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            data = json.loads(urllib.request.urlopen(req, timeout=4).read().decode())
            for j in data.get('jobs', []):
                loc = (j.get('location', {}).get('name') or '').lower()
                title = (j.get('title') or '').lower()
                is_in = any(k in loc for k in ('india', 'bengaluru', 'bangalore', 'pune', 'hyderabad', 'delhi', 'remote'))
                is_us = any(k in loc for k in ('united states', 'canada', 'uk', 'ireland', 'london', 'new york'))
                is_sec = any(k in title for k in ('security', 'risk', 'compliance', 'analyst', 'cyber', 'soc'))
                if is_sec and is_in and not is_us:
                    results.append({
                        'company': c.capitalize(),
                        'title': j.get('title'),
                        'location': j.get('location', {}).get('name'),
                        'url': j.get('absolute_url'),
                        'ats': 'greenhouse'
                    })
        except Exception:
            pass

    # 3. Lever
    for c in lever_targets:
        url = f'https://api.lever.co/v0/postings/{c}'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            data = json.loads(urllib.request.urlopen(req, timeout=4).read().decode())
            for j in data:
                loc = (j.get('categories', {}).get('location') or '').lower()
                title = (j.get('text') or '').lower()
                is_in = any(k in loc for k in ('india', 'bengaluru', 'bangalore', 'pune', 'hyderabad', 'delhi', 'remote'))
                is_sec = any(k in title for k in ('security', 'risk', 'compliance', 'analyst', 'cyber', 'soc'))
                if is_sec and is_in:
                    results.append({
                        'company': c.capitalize(),
                        'title': j.get('text'),
                        'location': j.get('categories', {}).get('location'),
                        'url': j.get('applyUrl'),
                        'ats': 'lever'
                    })
        except Exception:
            pass

    return results

if __name__ == '__main__':
    jobs = get_indian_startup_jobs()
    print(f"Total Indian Startup roles found: {len(jobs)}")
    for idx, j in enumerate(jobs, 1):
        print(f"{idx}. {j['company']} — {j['title']} ({j['location']})")
        print(f"   URL: {j['url']}")
