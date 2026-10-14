import urllib.request
import re
import json

urls = [
    "https://jobs.paloaltonetworks.com/en/job/santa-clara/mdr-shift-analyst-unit-42-west-coast-remote/47263/100407276944",
    "https://jobs.paloaltonetworks.com/en/job/california/threat-hunting-researcher-unit-42/47263/101043907984",
    "https://jobs.paloaltonetworks.com/en/job/texas/senior-msiam-soc-engineer-unit-42/47263/97170833744",
    "https://jobs.paloaltonetworks.com/en/job/austin/threat-hunter-researcher/47263/99405382640",
    "https://jobs.paloaltonetworks.com/en/job/illinois/principal-consultant-soc-transformation-and-xsiam-deployment/47263/96174881920"
]

headers = {'User-Agent': 'Mozilla/5.0'}

panw_verified = []
for u in urls:
    try:
        req = urllib.request.Request(u, headers=headers)
        html = urllib.request.urlopen(req, timeout=5).read().decode('utf-8', errors='ignore')
        m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        if m:
            d = json.loads(m.group(1))
            panw_verified.append({
                'title': d.get('title'),
                'req_id': d.get('identifier'),
                'url': u,
                'loc': 'Remote - USA' if 'remote' in d.get('title','').lower() or 'remote' in str(d.get('jobLocation','')).lower() else 'Hybrid / Onsite - USA'
            })
    except Exception as e:
        print(f"Error for {u}: {e}")

print("RESULTS:")
for p in panw_verified:
    print(p)
