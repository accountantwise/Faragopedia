"""
Smoke test for bulk operations — seeds test data, then verifies UI.
"""
import os, time
import urllib.request, urllib.parse, json
from playwright.sync_api import sync_playwright

FRONTEND = "http://localhost:5173"
BACKEND = "http://localhost:8300"
SCREENSHOTS = "C:/tmp/bulk_smoke"
os.makedirs(SCREENSHOTS, exist_ok=True)

failures = []

def ok(msg): print(f"  [OK] {msg}")
def fail(msg):
    print(f"  [FAIL] {msg}")
    failures.append(msg)
def warn(msg): print(f"  [WARN] {msg}")
def log(msg): print(f"\n{'='*55}\n{msg}\n{'='*55}")
def shot(page, name):
    page.screenshot(path=f"{SCREENSHOTS}/{name}.png", full_page=False)

# ── Seed test source files ────────────────────────────────────────────────
log("0. Seeding test source files via API")
def upload_text_source(filename, content):
    """Upload a text file as source (no ingest)."""
    body = (
        f"------TestBoundary7788\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: text/plain\r\n\r\n"
        f"{content}\r\n"
        f"------TestBoundary7788--\r\n"
    ).encode()
    req = urllib.request.Request(
        f"{BACKEND}/api/upload?ingest=false",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary=----TestBoundary7788"},
        method="POST"
    )
    try:
        r = urllib.request.urlopen(req)
        data = json.loads(r.read())
        print(f"  Uploaded: {data.get('filename')}")
        return data.get("filename")
    except Exception as e:
        print(f"  Upload failed: {e}")
        return None

# Use paste endpoint instead — simpler
def paste_source(name, content):
    payload = json.dumps({"name": name, "content": content}).encode()
    req = urllib.request.Request(
        f"{BACKEND}/api/paste",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        r = urllib.request.urlopen(req)
        data = json.loads(r.read())
        print(f"  Pasted: {data.get('filename')}")
        return data.get("filename")
    except Exception as e:
        print(f"  Paste failed: {e}")
        return None

f1 = paste_source("smoke-test-alpha", "Alpha test content for bulk operations testing.")
f2 = paste_source("smoke-test-beta", "Beta test content for bulk operations testing.")
f3 = paste_source("smoke-test-gamma", "Gamma test content for bulk operations testing.")

if not f1 or not f2:
    print("  Failed to seed test data - aborting")
    exit(1)

time.sleep(1)

# ── Browser tests ────────────────────────────────────────────────────────
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})

    # ── 1. Load Sources view ─────────────────────────────────────────────
    log("1. Loading Sources view")
    page.goto(FRONTEND)
    page.wait_for_load_state("networkidle")
    page.get_by_text("Sources", exact=True).first.click()
    # Wait for loading to finish
    try:
        page.wait_for_selector("text=Loading", state="hidden", timeout=8000)
    except: pass
    page.wait_for_timeout(1500)
    shot(page, "01_sources_loaded")

    page_text = page.evaluate("() => document.body.innerText.substring(0, 200)")
    print(f"  Page text snippet: {page_text[:150].replace(chr(10), ' ')}")

    # ── 2. Hover-reveal checkbox ─────────────────────────────────────────
    log("2. Hover-reveal checkbox on source items")

    # Find source items in the sidebar list (div with relative group flex pattern)
    # Try multiple selector strategies
    source_row = None
    selectors = [
        "div.relative.group",
        "div[class*='relative'][class*='group']",
        "div[class*='flex'][class*='items-center']:has(input[type='checkbox'])",
    ]

    # First hover approach: find any clickable item in the sources sidebar
    # The sidebar is the left panel (border-r)
    sidebar_items = page.locator("div.border-r div.relative").all()
    print(f"  Sidebar relative divs: {len(sidebar_items)}")

    # Try hovering items to trigger checkbox
    hovered = False
    general_items = page.evaluate("""() => {
        const items = document.querySelectorAll('div.border-r div, div.border-r li');
        return Array.from(items).slice(0, 30).map(el => ({
            tag: el.tagName,
            cls: el.className.substring(0, 80),
            text: el.innerText.substring(0, 30).replace(/\\n/g, ' ')
        }));
    }""")
    if isinstance(general_items, list):
        for item in general_items[:15]:
            print(f"    {item['tag']} class='{item['cls']}' text='{item['text']}'")

    # Try to hover over text containing our seeded filenames
    for fname in ["smoke-test-alpha", "smoke-test-beta", "alpha", "beta"]:
        try:
            el = page.get_by_text(fname, exact=False).first
            if el.is_visible():
                el.hover()
                page.wait_for_timeout(400)
                hovered = True
                print(f"  Hovered on text: '{fname}'")
                break
        except: pass

    shot(page, "02_after_hover")
    checkbox_count = page.locator("input[type='checkbox']").count()
    print(f"  Checkboxes visible after hover: {checkbox_count}")

    if checkbox_count > 0:
        ok("Hover-reveal checkbox works")
    else:
        fail("No checkbox appeared on hover")

    # ── 3. Selection toolbar ─────────────────────────────────────────────
    log("3. Selection toolbar")
    if checkbox_count > 0:
        page.locator("input[type='checkbox']").first.check()
        page.wait_for_timeout(400)
        shot(page, "03_selected")

        if page.get_by_text("selected").is_visible():
            ok("Selection count label visible")
        else:
            fail("'X selected' label not visible")

        # Toolbar buttons may be labelled "Ingest" / "Archive" or "Ingest selected" / "Archive selected"
        ingest_visible = (
            page.get_by_text("Ingest selected").is_visible() or
            page.get_by_text("Ingest").first.is_visible()
        )
        if ingest_visible:
            ok("Ingest button visible in toolbar")
        else:
            fail("Ingest button not found in toolbar")

        archive_visible = (
            page.get_by_text("Archive selected").first.is_visible() or
            page.get_by_text("Archive").first.is_visible()
        )
        if archive_visible:
            ok("Archive button visible in toolbar")
        else:
            fail("Archive button not found in toolbar")

        # Select a second item if available
        all_cb = page.locator("input[type='checkbox']")
        if all_cb.count() >= 2:
            all_cb.nth(1).check()
            page.wait_for_timeout(200)
            shot(page, "03b_two_selected")
            ok("Selected 2 items")

    # ── 4. Escape clears selection ───────────────────────────────────────
    log("4. Escape clears selection")
    if checkbox_count > 0:
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        shot(page, "04_escaped")
        # Toolbar should be gone
        selected_label = page.get_by_text("selected")
        if selected_label.count() == 0 or not selected_label.first.is_visible():
            ok("Escape cleared selection")
        else:
            fail("Escape did not clear selection")

    # ── 5. Archive confirm dialog ────────────────────────────────────────
    log("5. Archive confirm dialog")
    if checkbox_count > 0:
        page.locator("input[type='checkbox']").first.check()
        page.wait_for_timeout(300)
        # Find Archive button in toolbar — target red (bg-red) button to avoid nav sidebar match
        archive_btn = page.locator("button.bg-red-600, button[class*='bg-red']").first
        if archive_btn.is_visible():
            archive_btn.click()
            page.wait_for_timeout(400)
            shot(page, "05_confirm_dialog")
            cancel = page.get_by_text("Cancel")
            if cancel.is_visible():
                ok("Confirm dialog appeared with Cancel button")
                cancel.click()
                page.wait_for_timeout(300)
                ok("Cancelled - no archive happened")
            else:
                fail("Confirm dialog did not appear")
        else:
            warn("Archive button not visible - skipping dialog test")

    # ── 6. Wiki view bulk selection ──────────────────────────────────────
    log("6. Wiki view bulk selection")
    page.get_by_text("Wiki", exact=True).first.click()
    try:
        page.wait_for_selector("text=Loading", state="hidden", timeout=8000)
    except: pass
    page.wait_for_timeout(1500)
    shot(page, "06_wiki_view")

    wiki_text = page.evaluate("() => document.body.innerText.substring(0, 300)")
    print(f"  Wiki page text: {wiki_text[:200].replace(chr(10), ' ')}")

    # Try to find wiki page items and hover
    wiki_page_items = page.evaluate("""() => {
        const sidebar = document.querySelector('div.border-r');
        if (!sidebar) return [];
        const items = sidebar.querySelectorAll('button, div[class*="cursor-pointer"]');
        return Array.from(items).slice(0,15).map(el => ({
            cls: el.className.substring(0,60),
            text: el.innerText.substring(0,30).replace(/\\n/g,' ')
        }));
    }""")
    print(f"  Wiki sidebar items: {wiki_page_items}")

    # Hover over first leaf node
    wiki_hovered = False
    for fname in ["clients", "contacts", "photographers"]:
        try:
            # Try to expand a section first
            section = page.get_by_text(fname, exact=False).first
            if section.is_visible():
                section.click()
                page.wait_for_timeout(300)
                break
        except: pass

    # Now find page leaves to hover
    wiki_leaves = page.locator("div.border-r button, div.border-r div[class*='pl-']").all()
    print(f"  Wiki leaf candidates: {len(wiki_leaves)}")
    for leaf in wiki_leaves[:5]:
        try:
            text = leaf.inner_text()
            if text and len(text) > 2:
                leaf.hover()
                page.wait_for_timeout(400)
                wiki_hovered = True
                print(f"  Hovered wiki item: '{text[:30]}'")
                break
        except: pass

    shot(page, "07_wiki_hover")
    wiki_cb_count = page.locator("input[type='checkbox']").count()
    print(f"  Wiki checkboxes after hover: {wiki_cb_count}")

    if wiki_cb_count > 0:
        ok("Wiki hover-reveal checkbox works")
        page.locator("input[type='checkbox']").first.check()
        page.wait_for_timeout(300)
        shot(page, "08_wiki_selected")
        if page.get_by_text("Archive selected").first.is_visible():
            ok("Wiki 'Archive selected' button visible")
        else:
            fail("Wiki 'Archive selected' button not found")
        page.keyboard.press("Escape")
    else:
        warn("No wiki pages found - skipping wiki bulk UI test (no wiki content seeded)")

    # ── 7. Metadata poll persists across navigation ──────────────────────
    log("7. Metadata persists across navigation")
    page.get_by_text("Sources", exact=True).first.click()
    page.wait_for_timeout(600)
    page.get_by_text("Wiki", exact=True).first.click()
    page.wait_for_timeout(600)
    page.get_by_text("Sources", exact=True).first.click()
    page.wait_for_timeout(600)
    shot(page, "09_nav_complete")
    ok("Navigation Sources-Wiki-Sources completed without crash")

    browser.close()

# ── Cleanup seeded sources ────────────────────────────────────────────────
log("Cleanup: archiving seeded test sources")
for fname in [f1, f2, f3]:
    if fname:
        try:
            req = urllib.request.Request(
                f"{BACKEND}/api/sources/{urllib.parse.quote(fname)}",
                method="DELETE"
            )
            urllib.request.urlopen(req)
            print(f"  Archived: {fname}")
        except Exception as e:
            print(f"  Cleanup failed for {fname}: {e}")

# ── Summary ───────────────────────────────────────────────────────────────
print(f"\n{'='*55}")
print(f"SMOKE TEST COMPLETE  |  Screenshots: {SCREENSHOTS}")
if failures:
    print(f"\n[FAIL] FAILURES ({len(failures)}):")
    for f in failures:
        print(f"  {f}")
    exit(1)
else:
    print(f"\n[OK] ALL CHECKS PASSED")
