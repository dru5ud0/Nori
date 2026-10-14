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
    
    img = page.query_selector('img[alt="Atlan"]')
    if img:
        print("Atlan image bounding box:", img.bounding_box())
        parents = page.evaluate("""el => {
            let res = [];
            let cur = el;
            for (let i = 0; i < 4 && cur; i++) {
                cur = cur.parentElement;
                if (cur) res.push({tag: cur.tagName, className: cur.className});
            }
            return res;
        }""", img)
        print("Atlan image parents:", parents)
        
    # Check sponsorship question buttons
    spons = page.query_selector('input[name="fe1da0ac-9d69-4859-93c8-1dfcaf93c867"]')
    if spons:
        print("Sponsorship input found:", spons)
        container = page.evaluate_handle('el => el.closest("fieldset, div[class*=\\"field\\"]")', spons)
        print("Sponsorship container text:", repr(container.as_element().inner_text()))
        print("Sponsorship container box:", container.as_element().bounding_box())
        buttons = container.as_element().query_selector_all("button")
        for b in buttons:
            print("Sponsorship button:", b.get_attribute("data-option"), b.inner_text(), "box:", b.bounding_box(), "visible:", b.is_visible())
            
    browser.close()
