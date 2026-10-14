import sys
sys.stdout.reconfigure(encoding='utf-8')
import urllib.request
import urllib.parse
import re
import json
import time

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

def get_jobs_for_query(keyword):
    jobs = []
    page = 1
    while page <= 6:
        url = f"https://jobs.paloaltonetworks.com/en/search-jobs?k={urllib.parse.quote(keyword)}&al=6252001&p={page}"
        req = urllib.request.Request(url, headers=headers)
        try:
            html = urllib.request.urlopen(req).read().decode('utf-8', errors='ignore')
            matches = re.findall(r'<a class="section29__search-results-link" href="(/en/job/[^"]+)" data-job-id="(\d+)">\s*<h2 class="section29__search-results-job-title">([^<]+)</h2>.*?<span class="section29__result-location[^"]*">([^<]+)</span>', html, re.S)
            if not matches:
                break
            for link, jid, title, loc in matches:
                jobs.append({
                    'id': jid,
                    'title': title.strip(),
                    'location': loc.strip(),
                    'url': f"https://jobs.paloaltonetworks.com{link}"
                })
            if 'class="next"' not in html:
                break
            page += 1
        except Exception as e:
            break
    return jobs

def parse_job_detail(job_url):
    req = urllib.request.Request(job_url, headers=headers)
    try:
        html = urllib.request.urlopen(req).read().decode('utf-8', errors='ignore')
        
        # Look for Req ID / Reference ID (e.g. JR-...)
        req_id_match = re.search(r'Job ID\s*[:#]?\s*([A-Za-z0-9_-]+)', html, re.I)
        if not req_id_match:
            req_id_match = re.search(r'Reference\s*(?:ID|#)?\s*[:#]?\s*([A-Za-z0-9_-]+)', html, re.I)
        if not req_id_match:
            req_id_match = re.search(r'(JR-\d+)', html)
            
        req_id = req_id_match.group(1) if req_id_match else "PANW-" + job_url.split('/')[-1]

        # Check for citizenship / clearance restrictions
        text_lower = html.lower()
        requires_citizenship = any(term in text_lower for term in [
            'u.s. citizenship is required', 'us citizenship is required',
            'must be a u.s. citizen', 'must be a us citizen',
            'u.s. citizens only', 'us citizens only'
        ])
        
        requires_clearance = any(term in text_lower for term in [
            'active secret', 'active top secret', 'ts/sci', 'clearance required',
            'must possess an active security clearance', 'ability to obtain a security clearance',
            'polygraph required'
        ])

        # Check for remote flexibility
        is_remote = any(term in text_lower for term in ['remote', 'work from home', 'flexwork'])

        # Check YOE
        yoe_matches = re.findall(r'(\d+)\+?\s*(?:-\s*(\d+))?\s*(?:years|yrs)(?:\s+of)?\s+experience', text_lower)
        min_yoe = None
        if yoe_matches:
            try:
                numbers = [int(m[0]) for m in yoe_matches if m[0].isdigit()]
                if numbers:
                    min_yoe = min(numbers)
            except:
                pass

        return {
            'req_id': req_id,
            'requires_citizenship': requires_citizenship,
            'requires_clearance': requires_clearance,
            'is_remote': is_remote,
            'min_yoe': min_yoe,
            'html_len': len(html)
        }
    except Exception as e:
        return None

def main():
    print("Collecting PANW US security jobs...")
    raw_jobs = {}
    for kw in ['security', 'risk', 'analyst', 'compliance', 'soc', 'cloud security', 'incident']:
        res = get_jobs_for_query(kw)
        for j in res:
            raw_jobs[j['id']] = j

    print(f"Total raw jobs collected: {len(raw_jobs)}")

    # Filter by relevant title keywords
    target_terms = [
        'analyst', 'risk', 'compliance', 'security engineer', 'soc', 'grc',
        'detection', 'incident', 'threat', 'cloud security', 'vulnerability',
        'information security', 'cyber', 'infosec', 'trust'
    ]
    exclude_terms = [
        'director', 'vp', 'vice president', 'head of', 'account executive',
        'sales', 'marketing', 'hardware', 'asic', 'fpga', 'tax', 'payroll',
        'counsel', 'attorney', 'intern', 'recruiter'
    ]

    filtered_candidates = []
    for jid, job in raw_jobs.items():
        title_low = job['title'].lower()
        if any(ex in title_low for ex in exclude_terms):
            continue
        if any(tar in title_low for tar in target_terms):
            filtered_candidates.append(job)

    print(f"Candidate jobs matching profile titles: {len(filtered_candidates)}")

    valid_panw_jobs = []
    for idx, job in enumerate(filtered_candidates):
        print(f"Auditing [{idx+1}/{len(filtered_candidates)}]: {job['title']}...")
        details = parse_job_detail(job['url'])
        if not details:
            continue
        
        job['req_id'] = details['req_id']
        job['is_remote'] = details['is_remote']
        job['min_yoe'] = details['min_yoe']
        
        # Disqualification checks
        if details['requires_citizenship']:
            print(f"  [DISQUALIFIED] Citizenship required: {job['title']}")
            continue
        if details['requires_clearance']:
            print(f"  [DISQUALIFIED] Clearance required: {job['title']}")
            continue
        if details['min_yoe'] and details['min_yoe'] > 8:
            print(f"  [DISQUALIFIED] High YOE ({details['min_yoe']}+): {job['title']}")
            continue

        print(f"  [VALID MATCH] Req: {job['req_id']} | {job['title']} | {job['location']}")
        valid_panw_jobs.append(job)
        time.sleep(0.3)

    print(f"\n==========================================")
    print(f"FOUND {len(valid_panw_jobs)} VALID PALO ALTO NETWORKS ROLES:")
    print(f"==========================================")
    for v in valid_panw_jobs:
        print(f"Role: {v['title']}")
        print(f"Job ID: {v['req_id']}")
        print(f"Location: {v['location']}")
        print(f"Link: {v['url']}")
        print("-" * 40)

    # Save to json
    with open('loot/panw_valid_jobs.json', 'w', encoding='utf-8') as f:
        json.dump(valid_panw_jobs, f, indent=2)

if __name__ == '__main__':
    main()
