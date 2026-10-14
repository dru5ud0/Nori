import sys
import json
from pathlib import Path

ROOT = Path('.').resolve()
sys.path.insert(0, str(ROOT / 'backend' / 'src'))
sys.path.insert(0, str(ROOT / 'backend' / 'src' / 'tools'))
sys.path.insert(0, str(ROOT / 'webapp'))

from tsenta_hiringcafe import search_hiringcafe
from server import _load_profile

profile = _load_profile()
res = search_hiringcafe('security analyst', profile, limit=20, remote_only=True, location='India')
print(f"HiringCafe search results count: {len(res.get('jobs', []))}")
for j in res.get('jobs', [])[:10]:
    title = j.get('title')
    comp = j.get('companyName')
    score = j.get('matchScore')
    url = j.get('url')
    print(f"- {title} @ {comp} (Score: {score}%) -> {url}")
