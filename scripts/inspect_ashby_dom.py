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
    
    inputs = page.query_selector_all('input, select, textarea')
    for el in inputs:
        fid = el.get_attribute('id') or el.get_attribute('name') or el.get_attribute('data-nori-field') or 'no-id'
        tag = el.evaluate('el => el.tagName')
        el_type = el.get_attribute('type') or ''
        
        # Test label extraction
        lbl = page.evaluate("""el => {
            const entry = el.closest('[class*="fieldEntry"], [class*="_fieldEntry_"], fieldset, div[class*="field"], div[class*="question"]');
            if (entry) {
                // If yes/no
                const yn = el.closest('.ashby-application-form-input-yesno, [class*="yesno"]');
                const titleNode = entry.querySelector('legend, label, h1, h2, h3, h4, h5, [class*="title"], [class*="label"], p');
                let txt = titleNode?.textContent?.replace(/[*✱\\s]+$/, '')?.trim() || '';
                if (!txt) {
                    const raw = entry.innerText || '';
                    const firstLine = raw.split('\\n')[0]?.replace(/[*✱\\s]+$/, '')?.trim();
                    if (firstLine && !['yes', 'no', 'start typing...', 'upload file'].includes(firstLine.toLowerCase())) {
                        txt = firstLine;
                    }
                }
                return txt;
            }
            return '';
        }""", el)
        print(f"[{tag}:{el_type}] fid={fid} -> extracted_label={repr(lbl)}")

    browser.close()
