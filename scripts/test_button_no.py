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
    
    spons = page.query_selector("input[name='fe1da0ac-9d69-4859-93c8-1dfcaf93c867']")
    container = page.evaluate_handle("el => el.closest('.ashby-application-form-input-yesno, [class*=\"yesno\"]')", spons).as_element()
    btn_no = container.query_selector("button[data-option='no']")
    print("Before click: aria-pressed=", btn_no.get_attribute("aria-pressed"), "class=", btn_no.get_attribute("class"))
    btn_no.click()
    page.wait_for_timeout(300)
    print("After click: aria-pressed=", btn_no.get_attribute("aria-pressed"), "class=", btn_no.get_attribute("class"))
    browser.close()
