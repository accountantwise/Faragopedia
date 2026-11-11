"""Deeper recon: get main content area DOM for Sources and Wiki views."""
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
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    page.screenshot(path=f"{SCREENSHOTS}/recon2_sources.png", full_page=False)

    # Get the main content area (not the nav sidebar)
    content_html = page.evaluate("""() => {
        // Get all top-level children of root div
        const root = document.getElementById('root');
        if (!root) return 'no root';
        const mainFlex = root.firstElementChild;
        if (!mainFlex) return 'no mainFlex';
        // The second child should be the main content area (after the nav sidebar)
        const children = Array.from(mainFlex.children);
        return children.map((c, i) => `CHILD[${i}] tag=${c.tagName} class=${c.className.substring(0,80)} innerHTML_len=${c.innerHTML.length}`).join('\\n');
    }""")
    print("=== TOP LEVEL CHILDREN ===")
    print(content_html)

    # Get the main content HTML
    main_html = page.evaluate("""() => {
        const root = document.getElementById('root');
        const mainFlex = root?.firstElementChild;
        const children = mainFlex ? Array.from(mainFlex.children) : [];
        // Get the largest child (likely the content area)
        let largest = null, maxLen = 0;
        children.forEach(c => { if (c.innerHTML.length > maxLen) { maxLen = c.innerHTML.length; largest = c; }});
        return largest ? largest.innerHTML.substring(0, 4000) : 'not found';
    }""")
    print("\n=== MAIN CONTENT HTML (Sources) ===")
    print(main_html[:4000])

    # Count all inputs and divs with specific patterns
    all_inputs = page.locator("input[type='checkbox']").count()
    all_divs_with_filename = page.locator("div[class*='cursor'], div[class*='hover'], button[class*='cursor']").count()
    print(f"\nCheckboxes on page: {all_inputs}")
    print(f"Cursor/hover divs: {all_divs_with_filename}")

    # Look at all text content in the page (to see if sources loaded)
    all_text = page.evaluate("() => document.body.innerText.substring(0, 1000)")
    print(f"\nPage text: {all_text}")

    browser.close()
