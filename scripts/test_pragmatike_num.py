import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://jobs.ashbyhq.com/pragmatike/52d1af0c-6b0b-456f-b277-46cca879cb1d/application', timeout=45000)
    page.wait_for_timeout(3000)
    
    num_inputs = page.query_selector_all("input[type='number']")
    for idx, inp in enumerate(num_inputs):
        parent_txt = page.evaluate("el => el.closest('fieldset, div[class*=\"field\"]')?.innerText", inp)
        print(f"NUM {idx}: parent={repr(parent_txt)}")
        print(f"  placeholder={inp.get_attribute('placeholder')}, min={inp.get_attribute('min')}, max={inp.get_attribute('max')}")
    browser.close()
