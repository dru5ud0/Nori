"""Opt-in public ATS check: fill only name fields; never upload or submit."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.src.tools.tsenta_apply import _open_form, _form_frame, collect_fields, answer_fields, _execute_actions
from backend.src.tools.tsenta_llm import make_llm_answerer
from backend.src.tools.tsenta_trace import Trace
from playwright.sync_api import sync_playwright


def main():
    profile = json.loads((ROOT / 'loot/state/profile.json').read_text(encoding='utf-8'))
    url = 'https://job-boards.greenhouse.io/voyagertechnologiesinc/jobs/4379662009'
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page()
        try:
            _open_form(page, url, 'greenhouse', 30000)
            frame = _form_frame(page)
            fields = collect_fields(frame)
            names = [field for field in fields if field['label'].lower().rstrip(' *') in ('first name', 'last name', 'full name', 'name') and not field.get('hidden')]
            assert names, 'No name inputs on this public page (posting may be closed)'
            actions = answer_fields(names, profile, {}, Trace(), make_llm_answerer(profile, llm_cfg={'api_key': ''}))
            summary = _execute_actions(frame, actions, None)
            assert not summary['field_failures'], summary['field_failures']
            assert len(summary['verified_fields']) == len(names), summary
            print(json.dumps({'ok': True, 'ats': 'greenhouse', 'fieldsCollected': len(fields),
                              'verifiedNameFields': summary['verified_fields'], 'submitted': False, 'uploaded': False}))
        finally:
            browser.close()


if __name__ == '__main__':
    main()
