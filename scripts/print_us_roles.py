import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
with open(ROOT / 'loot' / 'us_cyber_company_roles.json', 'r', encoding='utf-8') as f:
    roles = json.load(f)

exclude_words = ['product manager', 'social media', 'collections', 'front desk', 'gtm',
                 'strategy', 'customer success', 'taipei', 'taiwan', 'costa rica',
                 'manager, security operations center', 'sr. manager', 'senior manager',
                 'director', 'vp']

clean = []
for r in roles:
    t_low = r['title'].lower()
    l_low = r['location'].lower()
    if any(w in t_low or w in l_low for w in exclude_words):
        continue
    clean.append(r)

print('Strict technical cybersecurity roles in US:', len(clean))
by_wp = {}
for r in clean:
    by_wp.setdefault(r['workplace'], []).append(r)

for wp in ['Remote', 'Hybrid', 'In-Person / Onsite']:
    items = by_wp.get(wp, [])
    print(f"\n==========================================")
    print(f"  US {wp.upper()} ({len(items)})")
    print(f"==========================================")
    for i, r in enumerate(items, 1):
        print(f"{i:02d}. [{r['company']}] {r['title']}")
        print(f"    Job ID: {r['job_id']}")
        print(f"    Location: {r['location']}")
        print(f"    Company Careers URL: {r['company_url']}")
