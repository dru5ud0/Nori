import sys
sys.stdout.reconfigure(encoding='utf-8')
import urllib.request
import urllib.parse
import json
import re
import time

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

def get_job_urls():
    urls = set()
    keywords = ['analyst', 'security', 'risk', 'compliance', 'soc', 'threat', 'cloud', 'incident', 'grc']
    for kw in keywords:
        page = 1
        while page <= 6:
            u = f"https://jobs.paloaltonetworks.com/en/search-jobs?k={urllib.parse.quote(kw)}&al=6252001&p={page}"
            try:
                req = urllib.request.Request(u, headers=headers)
                html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8', errors='ignore')
                links = re.findall(r'<a class="section29__search-results-link" href="(/en/job/[^"]+)"', html)
                if not links:
                    break
                for l in links:
                    urls.add(f"https://jobs.paloaltonetworks.com{l}")
                if 'class="next"' not in html:
                    break
                page += 1
            except Exception as e:
                break
    return list(urls)

def audit_url(url):
    try:
        req = urllib.request.Request(url, headers=headers)
        html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8', errors='ignore')
        
        m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        if not m:
            return None
        
        data = json.loads(m.group(1))
        
        # Verify Country is US
        loc_list = data.get('jobLocation', [])
        is_us = False
        loc_str = ""
        for loc in loc_list:
            addr = loc.get('address', {})
            country = addr.get('addressCountry', '')
            if country == 'US' or 'United States' in str(loc):
                is_us = True
                loc_str = f"{addr.get('addressLocality', '')}, {addr.get('addressRegion', '')}".strip(', ')
                break
        
        if not is_us:
            return None
        
        title = data.get('title', '').strip()
        job_id = data.get('identifier', '').strip()
        desc = data.get('description', '')
        clean_desc = re.sub(r'<[^>]+>', ' ', desc).lower()
        title_lower = title.lower()

        # Exclude non-target disciplines
        exclude_words = [
            'director', 'vp', 'vice president', 'account executive', 'sales',
            'legal', 'counsel', 'tax', 'payroll', 'hardware', 'asic', 'fpga',
            'intern', 'revenue analyst', 'business system analyst', 'finance'
        ]
        if any(w in title_lower for w in exclude_words):
            return None
        
        # Must match security / risk / analyst domains
        target_words = ['security', 'analyst', 'threat', 'soc', 'risk', 'compliance', 'incident', 'grc', 'cloud']
        if not any(w in title_lower for w in target_words):
            return None
            
        # Citizenship check
        if any(w in clean_desc for w in ['u.s. citizenship is required', 'us citizenship is required', 'must be a u.s. citizen', 'must be a us citizen', 'u.s. citizens only']):
            return None
            
        # Clearance check
        if any(w in clean_desc for w in ['active secret', 'active top secret', 'ts/sci', 'clearance required', 'polygraph required', 'must possess an active security clearance']):
            return None
            
        # YOE check
        # Extract years of experience
        yoe_list = [int(n) for n in re.findall(r'(\d+)\+?\s*(?:-\s*\d+)?\s*(?:years|yrs)(?:\s+of)?\s+experience', clean_desc)]
        min_yoe = min(yoe_list) if yoe_list else 3
        if min_yoe > 8:
            return None

        # Determine Workday Apply Link
        wd_apply = f"https://paloaltonetworks.wd5.myworkdayjobs.com/panwexternalcareers/job/{job_id}/apply"
        
        # Check if remote
        location_type = "Remote" if "remote" in title_lower or "remote" in clean_desc[:500] or "flexwork" in clean_desc else "Onsite/Hybrid"
        display_loc = f"{location_type} - {loc_str}" if loc_str else location_type

        return {
            'company': 'Palo Alto Networks',
            'title': title,
            'job_id': job_id,
            'location': display_loc,
            'url': url,
            'min_yoe': min_yoe
        }
    except Exception as e:
        return None

def main():
    print("Collecting PANW URLs...")
    urls = get_job_urls()
    print(f"Total candidate URLs to audit: {len(urls)}")

    matched = []
    for idx, u in enumerate(urls):
        res = audit_url(u)
        if res:
            print(f"[{len(matched)+1}] MATCH: {res['title']} | ID: {res['job_id']} | {res['location']}")
            matched.append(res)
        time.sleep(0.1)

    print(f"\n==========================================")
    print(f"TOTAL MATCHES FOUND: {len(matched)}")
    print(f"==========================================")
    for m in matched:
        print(f"Company: Palo Alto Networks")
        print(f"Role: {m['title']}")
        print(f"Job ID: {m['job_id']}")
        print(f"Location: {m['location']}")
        print(f"Link: {m['url']}")
        print()

    with open('loot/panw_final_matches.json', 'w', encoding='utf-8') as f:
        json.dump(matched, f, indent=2)

if __name__ == '__main__':
    main()
