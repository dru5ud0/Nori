import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from backend.src.tools.tsenta_apply import _click_custom_option

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://jobs.ashbyhq.com/atlan/b2b880ed-63cd-4f56-8313-87f143fa9807/application', timeout=45000)
    page.wait_for_timeout(3000)
    
    # Find how did you learn input
    ac_inputs = page.query_selector_all('input[placeholder*="Start typing"]')
    how_input = ac_inputs[1]
    res = _click_custom_option(page, how_input, "LinkedIn", "LinkedIn")
    print("_click_custom_option result:", res)
    print("how_input input_value:", repr(how_input.input_value()))
    
    browser.close()
