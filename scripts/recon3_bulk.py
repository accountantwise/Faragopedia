"""Recon 3: wait for content to load, then inspect main content area."""
import os
from playwright.sync_api import sync_playwright

SCREENSHOTS = "C:/tmp/bulk_smoke"
os.makedirs(SCREENSHOTS, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})

    page.goto("http://localhost:5173")
    page.wait_for_load_state("networkidle")
    page.get_by_text("Sources", exact=True).first.click()

    # Wait until "Loading" disappears
    try:
        page.wait_for_selector("text=Loading", state="hidden", timeout=10000)
    except:
        pass
    page.wait_for_timeout(3000)
    page.screenshot(path=f"{SCREENSHOTS}/recon3_sources.png", full_page=False)

    page_text = page.evaluate("() => document.body.innerText.substring(0, 500)")
    print("=== PAGE TEXT ===")
    print(page_text)

    # Get CHILD[1] — the main content area
    main_html = page.evaluate("""() => {
        const root = document.getElementById('root');
        const mainFlex = root?.firstElementChild;
        const main = mainFlex?.children[1];
        return main ? main.innerHTML.substring(0, 5000) : 'not found';
    }""")
    print("\n=== MAIN CONTENT HTML ===")
    print(main_html)

    # Find all interactive elements in main content
    items_info = page.evaluate("""() => {
        const root = document.getElementById('root');
        const mainFlex = root?.firstElementChild;
        const main = mainFlex?.children[1];
        if (!main) return 'no main';
        const els = main.querySelectorAll('button, [role="button"], div[class*="cursor-pointer"], div[class*="hover:bg"]');
        return Array.from(els).slice(0, 20).map(el =>
            `tag=${el.tagName} class="${el.className.substring(0,60)}" text="${el.innerText.substring(0,40).replace(/\\n/g,' ')}"`
        ).join('\\n');
    }""")
    print("\n=== INTERACTIVE ELEMENTS IN MAIN ===")
    print(items_info)

    print(f"\nCheckboxes: {page.locator('input[type=checkbox]').count()}")

    browser.close()
