import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from backend.src.tools.tsenta_apply import _form_frame, collect_fields, _index_field_elements

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://jobs.ashbyhq.com/atlan/b2b880ed-63cd-4f56-8313-87f143fa9807/application', timeout=45000)
    page.wait_for_timeout(3000)
    frame = _form_frame(page)
    
    fields = collect_fields(frame, timeout_ms=10000)
    indexed = _index_field_elements(frame)
    for fid in ('nori-field-8', 'nori-field-16'):
        el = indexed.get(fid)
        print(f"{fid} in indexed:", el)
        if el:
            print(f"  tag={el[0].evaluate('el => el.tagName')}, class={el[0].get_attribute('class')}, placeholder={el[0].get_attribute('placeholder')}")
            
    browser.close()
