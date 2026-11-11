"""Recon script: capture screenshots and DOM snippets to discover real selectors."""
import os
from playwright.sync_api import sync_playwright

SCREENSHOTS = "C:/tmp/bulk_smoke"
os.makedirs(SCREENSHOTS, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})

    # Sources view
    page.goto("http://localhost:5173")
    page.wait_for_load_state("networkidle")
    page.get_by_text("Sources", exact=True).first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)
    page.screenshot(path=f"{SCREENSHOTS}/recon_sources.png", full_page=False)

    # Print relevant DOM
    sidebar_html = page.evaluate("""() => {
        const el = document.querySelector('aside') || document.querySelector('[class*="sidebar"]') || document.querySelector('[class*="Sidebar"]');
        return el ? el.innerHTML.substring(0, 3000) : 'NO SIDEBAR FOUND - body: ' + document.body.innerHTML.substring(0, 2000);
    }""")
    print("=== SOURCES SIDEBAR HTML ===")
    print(sidebar_html[:3000])

    # Hover first clickable item
    items = page.locator("button, li, [role='button']").all()
    print(f"\nTotal buttons/li/roles: {len(items)}")
    for i, item in enumerate(items[:10]):
        try:
            text = item.inner_text()
            cls = item.get_attribute("class") or ""
            tag = item.evaluate("el => el.tagName")
            print(f"  [{i}] <{tag}> class='{cls[:60]}' text='{text[:40]}'")
        except:
            pass

    # Wiki view
    page.get_by_text("Wiki", exact=True).first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)
    page.screenshot(path=f"{SCREENSHOTS}/recon_wiki.png", full_page=False)

    wiki_html = page.evaluate("""() => {
        const el = document.querySelector('aside') || document.querySelector('[class*="sidebar"]');
        return el ? el.innerHTML.substring(0, 3000) : 'NO SIDEBAR - body: ' + document.body.innerHTML.substring(0, 2000);
    }""")
    print("\n=== WIKI SIDEBAR HTML ===")
    print(wiki_html[:3000])

    browser.close()
    print(f"\nScreenshots: {SCREENSHOTS}/recon_*.png")
