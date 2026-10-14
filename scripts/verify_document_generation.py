"""Exercise configured document generation without applying or modifying a profile."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.src.tools.tsenta_documents import documents_for_application, fetch_job_context


def main():
    profile = json.loads((ROOT / 'loot/state/profile.json').read_text(encoding='utf-8'))
    context = fetch_job_context('https://job-boards.greenhouse.io/voyagertechnologiesinc/jobs/4379662009')
    documents = documents_for_application(profile, {'optimizationMode': 'honest', 'coverLetterMode': 'generated'}, context)
    for key, text_key in [('resume', 'resumeText'), ('coverLetter', 'coverLetterText')]:
        doc = documents[key]
        text = doc.get(text_key) or ''
        print(json.dumps({'document': key, 'status': doc.get('status'), 'words': len(text.split()),
            'qualityIssues': doc.get('qualityIssues'), 'metadata': doc.get('resumeMetadata') or doc.get('coverLetterMetadata')}))
        assert text and doc.get('status') == 'COMPLETED', doc
    print('COVER LETTER QUALITY SAMPLE\n' + documents['coverLetter']['coverLetterText'])


if __name__ == '__main__':
    main()
