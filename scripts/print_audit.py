import json

with open('loot/audited_jobs_validation.json', 'r', encoding='utf-8') as f:
    audit = json.load(f)

by_verdict = {}
for a in audit:
    by_verdict.setdefault(a['verdict'], []).append(a)

for v, items in by_verdict.items():
    print(f"\n==========================================")
    print(f"  {v.upper()} ({len(items)})")
    print(f"==========================================")
    for x in items:
        print(f"* [{x['company']}] {x['title']}")
        print(f"  Job ID: {x['job_id']}")
        print(f"  Live: {x['is_live']} | Min YOE: {x.get('min_yoe')}")
        print(f"  Audit Reason: {x['reason']}")
        print(f"  Profile Tags: {', '.join(x.get('fit_tags', []))}")
        print(f"  URL: {x['url']}")
