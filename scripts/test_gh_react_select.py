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
    
    # 1. Fill country
    country_input = page.query_selector("input#country")
    if country_input:
        print("Clicking and typing country...")
        country_input.click()
        country_input.type("India", delay=50)
        page.wait_for_timeout(1000)
        # Select individual option
        options = page.query_selector_all("[role='option']")
        print(f"Found {len(options)} role=option elements")
        for opt in options:
            txt = opt.text_content().strip()
            print("  Option:", repr(txt))
            if txt == "India +91":
                opt.click()
                print("Clicked India +91!")
                break

    # 2. Fill phone
    phone = page.query_selector("input#phone")
    if phone:
        phone.fill("9980993977")
        page.wait_for_timeout(500)
        phone_err = page.query_selector("#phone-error")
        print("Phone error after +91:", phone_err.text_content() if phone_err else "None")

    # 3. Fill location
    loc_input = page.query_selector("input#candidate-location")
    if loc_input:
        print("\nClicking and typing location...")
        loc_input.click()
        loc_input.type("Bengaluru", delay=50)
        page.wait_for_timeout(1000)
        options = page.query_selector_all("[role='option']")
        print(f"Found {len(options)} role=option elements for location")
        for opt in options:
            txt = opt.text_content().strip()
            print("  Option:", repr(txt))
            if "Bengaluru" in txt:
                opt.click()
                print("Clicked Bengaluru option!")
                break

    page.screenshot(path="loot/reports/test_gh_react_select_fixed.png")
    print("Screenshot saved to loot/reports/test_gh_react_select_fixed.png")
    browser.close()
