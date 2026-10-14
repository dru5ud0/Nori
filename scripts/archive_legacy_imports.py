"""Archive only the audited legacy junk imports; retain a full backup."""
import json
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.src.tools.tsenta_pipeline import _load_store, _save_store, _store_lock


def main():
    path = ROOT / 'loot' / 'state' / 'applications.json'
    with _store_lock(str(path)):
        store = _load_store(str(path))
        selected = []
        for job in store['applications'].values():
            if job.get('submitted') or job.get('status') == 'applied' or job.get('archived'):
                continue
            url = urlsplit(job.get('url') or '')
            non_job = url.hostname in ('skool.com', 'tryhackme.com', 'join.theengineers.club', 'www.herodevs.com')
            off_target = url.hostname == 'www.iitjobs.com' and 'india' in url.path
            old_demo = '/mozilla/jobs/' in url.path and not job.get('jobTitle')
            if not (non_job or off_target or old_demo):
                continue
            selected.append(job)
        if selected:
            backup = path.with_name(f'applications.before-cleanup-{int(time.time())}.json')
            shutil.copy2(path, backup)
            for job in selected:
                job['archived'] = True
                job['archiveReason'] = 'Audited legacy test, non-job, or off-target import'
            _save_store(store, str(path))
            print(json.dumps({'archived': len(selected), 'backup': str(backup),
                              'ids': [job['applicationId'] for job in selected]}))
        else:
            print(json.dumps({'archived': 0}))


if __name__ == '__main__':
    main()
