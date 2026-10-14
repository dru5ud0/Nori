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
    
    # Fill all required fields
    page.fill("input[name='_systemfield_name']", "Drupadh Suresh")
    page.fill("input[name='_systemfield_email']", "sureshdrupadh@gmail.com")
    
    phone = page.query_selector("input[type='tel']")
    if phone:
        phone.fill("9980993977")
        
    page.set_input_files("input[id='_systemfield_resume']", r"C:\Users\Dru\Desktop\Drupadh_Suresh_Resume.pdf")
    page.wait_for_timeout(1000)
    
    # Employer field
    emp = page.query_selector("input[id='cbbd5a13-01f9-4540-b40d-813d3291d939']")
    print("Testing employer field fill + events...")
    emp.click()
    emp.fill("PNC Financial Services")
    emp.press("Tab")
    emp.dispatch_event("input")
    emp.dispatch_event("change")
    emp.dispatch_event("blur")
    
    # LinkedIn
    page.fill("input[name='25f315e3-c7c1-45d5-9c20-6ec1797813b0']", "https://linkedin.com/in/drupadhsuresh")
    
    # Yes/No buttons
    b_yes = page.query_selector("div:has(> input[name='82a4f449-afbd-4af0-9a50-47d27383b8aa']) button[data-option='yes']")
    if b_yes: b_yes.click()
    
    b_no = page.query_selector("div:has(> input[name='d08ece9c-97f3-454a-baf9-b23b31480c66']) button[data-option='no']")
    if b_no: b_no.click()
    
    # Comp
    page.fill("input[name='7a81f921-67d4-459d-b97f-30e8577209aa']", "18 LPA")
    
    # How did you hear
    how = page.query_selector_all("input[placeholder*='Start typing']")[1]
    how.click()
    how.fill("LinkedIn")
    page.wait_for_timeout(500)
    opt = page.query_selector("[role='option']")
    if opt: opt.click()
    
    # Textareas
    tas = page.query_selector_all("textarea")
    if len(tas) >= 2:
        tas[0].fill("I developed an automated threat detection tool using Python.")
        tas[1].fill("I managed third-party risk and compliance.")
        
    # Zero trust yes/no
    zt_no = page.query_selector("div:has(> input[name='e72e18b6-fd09-4e75-9799-934f3b5dbd16']) button[data-option='no']")
    if zt_no: zt_no.click()
    
    # Checkbox
    cb = page.query_selector("input[type='checkbox'][id*='labeled-checkbox']")
    if cb and not cb.is_checked(): cb.check()
    
    page.wait_for_timeout(1000)
    
    # Click submit
    print("Clicking submit...")
    page.click("button:has-text('Submit application')", timeout=5000)
    page.wait_for_timeout(3000)
    
    banner = page.query_selector("div:has-text('Missing entry for required field')")
    if banner:
        print("Banner STILL present:", banner.inner_text())
    else:
        print("SUCCESS! No validation error banner present!")
        
    page.screenshot(path=r"loot\reports\test_ashby_submit_result.png", full_page=True)
    browser.close()
