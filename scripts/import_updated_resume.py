"""Import the user's verified September resume while preserving eligibility settings."""
import json
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.src.tools.tsenta_resume import _extract_text, _parse_experience, _parse_summary
from backend.src.tools.nori_monitor import save_monitor_settings


def main():
    source = Path(r'C:\Users\Dru\Desktop\Drupadh_Suresh_Resume.pdf')
    state = ROOT / 'loot/state'
    profile_path = state / 'profile.json'
    profile = json.loads(profile_path.read_text(encoding='utf-8'))
    text = _extract_text(str(source))
    experience = _parse_experience(text)
    assert len(experience) == 5, [(j['company'], j['role']) for j in experience]
    hackerone = next(j for j in experience if j['company'] == 'HackerOne')
    assert len(hackerone['responsibilities']) == 3
    assert 'preliminary review' in ' '.join(hackerone['responsibilities'])
    categories = []
    skills_text = re.search(r'(?ms)^SKILLS\s*\n(.*?)^EXPERIENCE\s*$', text).group(1)
    for line in skills_text.splitlines():
        if ':' in line:
            name, value = line.split(':', 1)
            categories.append({'name': name.strip(), 'skills': value.strip()})
        elif categories:
            categories[-1]['skills'] += ' ' + line.strip()
    for category in categories:
        category['skills'] = [item.strip() for item in category['skills'].split(',') if item.strip()]
    assert len(categories) == 7
    stamp = int(time.time())
    shutil.copy2(profile_path, state / f'profile.before-hackerone-{stamp}.json')
    resume_path = state / 'resume.pdf'
    if resume_path.exists():
        shutil.copy2(resume_path, state / f'resume.before-hackerone-{stamp}.pdf')
    profile['workExperience'] = experience
    profile['skillCategories'] = categories
    profile['personalInformation']['summary'] = _parse_summary(text)
    profile['personalInformation']['title'] = 'Cybersecurity Risk Analyst'
    profile['resumePath'] = str(resume_path)
    profile['resumeFormat'] = 'pdf'
    profile['resumeSource'] = str(source)
    shutil.copy2(source, resume_path)
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding='utf-8')
    save_monitor_settings({'query': 'Cybersecurity', 'strictLocation': False,
                           'remoteOnly': False, 'minimumSalary': 0, 'excludedTitles': ''})
    print(json.dumps({'ok': True, 'experienceEntries': len(experience), 'hackerOneBullets': 3,
                      'skillCategories': len(categories), 'backupStamp': stamp,
                      'eligibilityPreserved': True, 'query': 'Cybersecurity'}))


if __name__ == '__main__':
    main()
