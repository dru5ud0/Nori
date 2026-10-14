from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://localhost:9222")
    context = browser.contexts[0]
    page = context.pages[0]
    print("Active URL:", page.url)
    print("Page Title:", page.title())

    inputs = page.query_selector_all("input, select, textarea")
    print(f"Total inputs found: {len(inputs)}")
    for i, el in enumerate(inputs, 1):
        try:
            tag = el.evaluate("(e) => e.tagName")
            name = el.evaluate("(e) => e.name || e.id || ''")
            lbl = page.evaluate("(e) => (el) => el.closest('label, div')?.textContent?.trim()?.slice(0, 50) || ''", el)
            val = el.input_value() if tag in ('INPUT', 'TEXTAREA') else el.evaluate("(e) => e.value")
            print(f"[{i:02d}] {name} ({tag}): val='{val}'")
        except Exception as e:
            print(f"[{i:02d}] error: {e}")

    page.screenshot(path="loot/reports/user_screen_inspect.png")
    print("Captured screenshot to loot/reports/user_screen_inspect.png")
finally:
    pw.stop()
