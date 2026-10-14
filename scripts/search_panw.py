import urllib.request
import re
import time

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

def get_jobs_for_query(keyword):
    jobs = []
    page = 1
    while page <= 5: # check first 5 pages
        url = f"https://jobs.paloaltonetworks.com/en/search-jobs?k={urllib.parse.quote(keyword)}&al=6252001&p={page}"
        req = urllib.request.Request(url, headers=headers)
        try:
            html = urllib.request.urlopen(req).read().decode('utf-8')
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
            # check if there is a next page
            if 'class="next"' not in html:
                break
            page += 1
        except Exception as e:
            print(f"Error on page {page}: {e}")
            break
    return jobs

if __name__ == '__main__':
    all_jobs = {}
    for kw in ['security', 'risk', 'analyst', 'compliance', 'soc', 'cloud']:
        print(f"Searching for {kw}...")
        results = get_jobs_for_query(kw)
        for j in results:
            all_jobs[j['id']] = j
        print(f"Found {len(results)} jobs for {kw}. Total unique: {len(all_jobs)}")

    print(f"\n--- TOTAL UNIQUE PANW US JOBS: {len(all_jobs)} ---")
    for jid, j in list(all_jobs.items())[:20]:
        print(f"[{jid}] {j['title']} | {j['location']}")
