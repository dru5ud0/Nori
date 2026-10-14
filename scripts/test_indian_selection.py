import urllib.request
import json

def is_profile_fit(title: str) -> bool:
    t = title.lower()
    negative = ('writer', 'ui developer', 'frontend', 'product manager', 'sales', 'business development', 
                'bdr', 'sdr', 'marketing', 'customer support', 'content', 'entitlement', 'deal desk', 
                'order processing', 'quality analyst', 'video', 'facilities', 'financial systems', 'user lending',
                'decision science', 'r2r', 'site reliability', 'strategic alliances', 'project manager')
    if any(n in t for n in negative):
        return False
    positive = ('security', 'cyber', 'soc', 'infosec', 'threat', 'vulnerability', 'incident', 
                'cloud security', 'grc', 'risk', 'compliance', 'appsec')
    return any(p in t for p in positive)

applied = {
    'https://jobs.ashbyhq.com/pragmatike/88905b50-a8c2-4615-9f92-63dd995da3fe',
    'https://jobs.ashbyhq.com/atlan/254c1250-953b-4323-8d18-9fe5e41d8d7d',
    'https://jobs.ashbyhq.com/atlan/b2b880ed-63cd-4f56-8313-87f143fa9807',
    'https://jobs.ashbyhq.com/pragmatike/64f83880-fcba-4430-91d1-6734d24b1be1',
    'https://jobs.ashbyhq.com/pragmatike/6c4203b1-cd38-4e2f-bdf5-aa2b539663e3',
    'https://jobs.ashbyhq.com/pragmatike/52d1af0c-6b0b-456f-b277-46cca879cb1d',
}

ashby_targets = ['atlan', 'pragmatike', 'hasura', 'signoz', 'devrev', 'invideo', 'toplyne']
gh_targets = ['alphasense', 'druva', 'highradius', 'inmobi', 'chargebee', 'whatfix', 'browserstack']
lever_targets = ['meesho', 'razorpay', 'cred', 'groww']

selected = []

for c in ashby_targets:
    try:
        url = f'https://api.ashbyhq.com/posting-api/job-board/{c}'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = json.loads(urllib.request.urlopen(req, timeout=4).read().decode())
        for j in data.get('jobs', []):
            loc = (j.get('location') or '').lower()
            title = j.get('title') or ''
            workplace = (j.get('workplaceType') or '').lower()
            is_in = any(k in loc for k in ('india', 'bengaluru', 'bangalore', 'pune', 'hyderabad', 'delhi', 'remote'))
            job_url = j.get('jobUrl')
            if is_in and is_profile_fit(title) and job_url and job_url.rstrip('/') not in applied:
                selected.append((c.capitalize(), title, f"{j.get('location')} ({workplace})", job_url, 'ashby'))
    except Exception:
        pass

for c in gh_targets:
    try:
        url = f'https://boards-api.greenhouse.io/v1/boards/{c}/jobs'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = json.loads(urllib.request.urlopen(req, timeout=4).read().decode())
        for j in data.get('jobs', []):
            loc = (j.get('location', {}).get('name') or '').lower()
            title = j.get('title') or ''
            is_in = any(k in loc for k in ('india', 'bengaluru', 'bangalore', 'pune', 'hyderabad', 'delhi', 'remote'))
            is_us = any(k in loc for k in ('united states', 'canada', 'uk', 'ireland', 'london', 'new york'))
            job_url = j.get('absolute_url')
            if is_in and not is_us and is_profile_fit(title) and job_url and job_url.rstrip('/') not in applied:
                selected.append((c.capitalize(), title, j.get('location', {}).get('name'), job_url, 'greenhouse'))
    except Exception:
        pass

for c in lever_targets:
    try:
        url = f'https://api.lever.co/v0/postings/{c}'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = json.loads(urllib.request.urlopen(req, timeout=4).read().decode())
        for j in data:
            loc = (j.get('categories', {}).get('location') or '').lower()
            title = j.get('text') or ''
            is_in = any(k in loc for k in ('india', 'bengaluru', 'bangalore', 'pune', 'hyderabad', 'delhi', 'remote'))
            job_url = j.get('applyUrl')
            if is_in and is_profile_fit(title) and job_url and job_url.rstrip('/') not in applied:
                selected.append((c.capitalize(), title, j.get('categories', {}).get('location'), job_url, 'lever'))
    except Exception:
        pass

print(f"Total High-Quality Indian Startup Roles: {len(selected)}")
for idx, (co, ti, lo, u, ats) in enumerate(selected, 1):
    print(f"{idx}. {co} — {ti} ({lo}) [{ats}]")
    print(f"   URL: {u}")
