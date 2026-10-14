import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright

url = "https://jobs.ashbyhq.com/atlan/254c1250-953b-4323-8d18-9fe5e41d8d7d/application"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, timeout=45000)
    page.wait_for_timeout(3000)
    
    # Find employer input
    inputs = page.query_selector_all("input[type='text']")
    emp_input = None
    for inp in inputs:
        parent_txt = page.evaluate("el => el.closest('fieldset, div[class*=\"field\"]')?.innerText", inp)
        if parent_txt and "employer" in parent_txt.lower():
            emp_input = inp
            break
            
    print("Found emp_input:", emp_input)
    if emp_input:
        # Test 1: fill + blur
        emp_input.click()
        emp_input.fill("PNC Financial Services")
        emp_input.press("Tab")
        page.wait_for_timeout(500)
        
        # Test clicking submit to see if validation passes on this field
        sub = page.query_selector("button:has-text('Submit Application')")
        sub.click()
        page.wait_for_timeout(1000)
        
        banner = page.query_selector("div:has-text('Missing entry for required field')")
        print("Banner text after fill + Tab:", repr(banner.inner_text() if banner else None))
        
        # Test 2: type with keyboard
        emp_input.click()
        emp_input.press("Control+A")
        emp_input.press("Backspace")
        emp_input.type("PNC Financial Services", delay=30)
        emp_input.press("Tab")
        page.wait_for_timeout(500)
        sub.click()
        page.wait_for_timeout(1000)
        
        banner2 = page.query_selector("div:has-text('Missing entry for required field')")
        print("Banner text after type + Tab:", repr(banner2.inner_text() if banner2 else None))

    browser.close()
