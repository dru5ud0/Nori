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

    # 1. Fill First Name, Last Name, Preferred Name, Email via keyboard typing
    for sel, val in [
        ('#first_name', 'Drupadh'),
        ('#last_name', 'Suresh'),
        ('#preferred_name', 'Drupadh'),
        ('#email', 'sureshdrupadh@gmail.com')
    ]:
        el = page.query_selector(sel)
        if el:
            el.click()
            el.fill("")
            el.type(val, delay=20)
            page.wait_for_timeout(100)

    # 2. Select Country: click country input, type India, press ArrowDown, press Enter
    c_input = page.query_selector('#country')
    if c_input:
        c_input.click()
        c_input.fill("")
        c_input.type("India", delay=30)
        page.wait_for_timeout(500)
        c_input.press("ArrowDown")
        page.wait_for_timeout(200)
        c_input.press("Enter")
        page.wait_for_timeout(500)

    # 3. Fill Phone via keyboard typing
    phone = page.query_selector('#phone')
    if phone:
        phone.click()
        phone.fill("")
        phone.type("9980993977", delay=30)
        page.wait_for_timeout(300)

    # 4. Fill Location: click, type Bengaluru, wait, press ArrowDown, press Enter
    loc = page.query_selector('#candidate-location')
    if loc:
        loc.click()
        loc.fill("")
        loc.type("Bengaluru", delay=30)
        page.wait_for_timeout(800)
        loc.press("ArrowDown")
        page.wait_for_timeout(200)
        loc.press("Enter")
        page.wait_for_timeout(500)

    # 5. Attach Resume via file input
    resume_path = "C:/Users/Dru/Desktop/Drupadh_Suresh_AlphaSense_Resume.pdf"
    res_input = page.query_selector("input#resume")
    if res_input:
        res_input.set_input_files(resume_path)
        page.wait_for_timeout(1000)

    # 6. Attach Cover Letter via file input
    cover_path = "C:/Users/Dru/Desktop/Drupadh_Suresh_AlphaSense_Cover_Letter.pdf"
    cov_input = page.query_selector("input#cover_letter")
    if cov_input:
        cov_input.set_input_files(cover_path)
        page.wait_for_timeout(1000)

    # 7. Fill LinkedIn via keyboard typing
    li = page.query_selector("input#question_37337520002")
    if li:
        li.click()
        li.fill("")
        li.type("https://linkedin.com/in/drupadhsuresh", delay=20)
        page.wait_for_timeout(300)

    # Check for any errors
    errors = page.query_selector_all("[id*='error'], .field-error, .text-error")
    for err in errors:
        if err.is_visible() and err.text_content().strip():
            print("Visible error:", err.text_content().strip())

    page.screenshot(path="loot/reports/test_gh_react18_result.png", full_page=True)
    print("Screenshot saved to loot/reports/test_gh_react18_result.png")
    browser.close()
