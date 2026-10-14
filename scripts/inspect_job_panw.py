import urllib.request
import re
import json

url = 'https://jobs.paloaltonetworks.com/en/job/santa-clara/mdr-shift-analyst-unit-42-west-coast-remote/47263/100407276944'
headers = {'User-Agent': 'Mozilla/5.0'}
html = urllib.request.urlopen(urllib.request.Request(url, headers=headers)).read().decode('utf-8', errors='ignore')

json_ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
desc = json_ld['description']

# Strip html tags
clean_desc = re.sub(r'<[^>]+>', ' ', desc)

print("Title:", json_ld['title'])
print("Identifier:", json_ld['identifier'])
print("Location:", json_ld['jobLocation'])
print("\nDescription excerpt:\n", clean_desc[:1200])

for term in ['citizen', 'clearance', 'experience', 'years']:
    print(f"\n--- Matches for '{term}': ---")
    for s in clean_desc.split('.'):
        if term in s.lower():
            print("  *", s.strip())
