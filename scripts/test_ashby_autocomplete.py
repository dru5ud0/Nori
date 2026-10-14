import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://jobs.ashbyhq.com/atlan/b2b880ed-63cd-4f56-8313-87f143fa9807/application', timeout=45000)
    page.wait_for_timeout(3000)
    
    phone_input = page.query_selector('input[type="tel"]')
    if phone_input:
        print("Phone input found:", phone_input)
        phone_input.click()
        phone_input.fill("+91 9980993977")
        print("Phone input filled value:", phone_input.input_value())
            
    browser.close()
