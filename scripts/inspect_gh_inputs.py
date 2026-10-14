import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://job-boards.greenhouse.io/alphasense/jobs/8634067002', timeout=45000)
    page.wait_for_timeout(3000)
    
    inputs = page.query_selector_all('input, select, textarea')
    for el in inputs:
        fid = el.get_attribute('id') or el.get_attribute('name') or el.get_attribute('data-testid') or 'no-id'
        tag = el.evaluate('el => el.tagName')
        el_type = el.get_attribute('type') or ''
        placeholder = el.get_attribute('placeholder') or ''
        aria_label = el.get_attribute('aria-label') or ''
        val = el.input_value() if hasattr(el, 'input_value') else ''
        print(f"[{tag}:{el_type}] id={fid} | aria={aria_label} | placeholder={placeholder} | val={repr(val)}")

    browser.close()
