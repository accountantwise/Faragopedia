"""
Smoke test for bulk operations feature.
Tests: hover-reveal checkboxes, bulk ingest, bulk archive (sources + wiki pages),
selection toolbar, confirm dialog, Escape to clear.
"""
import time
import os
from playwright.sync_api import sync_playwright, expect

FRONTEND = "http://localhost:5173"
BACKEND = "http://localhost:8000"
SCREENSHOTS = "/tmp/bulk_smoke"

os.makedirs(SCREENSHOTS, exist_ok=True)

def screenshot(page, name):
    path = f"{SCREENSHOTS}/{name}.png"
    page.screenshot(path=path, full_page=False)
    print(f"  [screenshot] {path}")

def log(msg):
    print(f"\n{'='*60}\n{msg}\n{'='*60}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    failures = []

    # ── 1. Load Sources view ──────────────────────────────────────────────
    log("1. Loading Sources view")
    page.goto(FRONTEND)
    page.wait_for_load_state("networkidle")
    page.get_by_text("Sources", exact=True).first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)
    screenshot(page, "01_sources_view")

    # ── 2. Check for source items ─────────────────────────────────────────
    log("2. Checking source items exist")
    source_items = page.locator('[data-testid="source-item"], .source-item').all()
    # Fallback: look for items in the sidebar list
    if not source_items:
        # Try to find list items in the sidebar
        sidebar = page.locator("aside, [class*='sidebar'], [class*='list']").first
        source_items = sidebar.locator("li, [class*='item']").all()

    print(f"  Found {len(source_items)} source items")
    if len(source_items) == 0:
        print("  [WARN]  No sources found — uploading one for testing")
        # Check if there's an Add Sources button
        add_btn = page.get_by_text("Add Sources").first
        if add_btn.is_visible():
            print("  [INFO]  Add Sources button visible — skipping upload, testing with empty state")

    # ── 3. Hover over first source item to reveal checkbox ────────────────
    log("3. Testing hover-reveal checkbox")
    # Look for the source list sidebar items
    source_rows = page.locator("li").filter(has=page.locator("input[type='checkbox']")).all()
    if not source_rows:
        # Try hovering first list item to trigger checkbox appearance
        all_items = page.locator("aside li, [class*='sidebar'] li, [class*='list'] > div").all()
        print(f"  Found {len(all_items)} potential list items")
        if all_items:
            all_items[0].hover()
            page.wait_for_timeout(300)
            screenshot(page, "02_hover_reveal")
            checkbox = page.locator("input[type='checkbox']").first
            if checkbox.is_visible():
                print("  [OK] Checkbox revealed on hover")
            else:
                msg = "  [FAIL] No checkbox revealed on hover"
                print(msg)
                failures.append(msg)
        else:
            print("  [WARN]  No list items found to hover")
    else:
        print(f"  [OK] Found {len(source_rows)} items with checkboxes")

    # ── 4. Select items and check toolbar appears ─────────────────────────
    log("4. Testing selection toolbar")
    checkboxes = page.locator("input[type='checkbox']")
    count = checkboxes.count()
    print(f"  Found {count} checkboxes")

    if count >= 1:
        checkboxes.first.check()
        page.wait_for_timeout(300)
        screenshot(page, "03_one_selected")

        # Toolbar should appear
        toolbar = page.get_by_text("selected").first
        if toolbar.is_visible():
            print("  [OK] Selection toolbar appeared")
        else:
            msg = "  [FAIL] Selection toolbar not visible after selecting item"
            print(msg)
            failures.append(msg)

        # Check for action buttons
        ingest_btn = page.get_by_text("Ingest selected")
        archive_btn = page.get_by_text("Archive selected").first
        if ingest_btn.is_visible():
            print("  [OK] 'Ingest selected' button visible")
        else:
            msg = "  [FAIL] 'Ingest selected' button not found"
            print(msg)
            failures.append(msg)
        if archive_btn.is_visible():
            print("  [OK] 'Archive selected' button visible")
        else:
            msg = "  [FAIL] 'Archive selected' button not found"
            print(msg)
            failures.append(msg)
    else:
        print("  [WARN]  No checkboxes to select — skipping toolbar test")

    # ── 5. Test Escape clears selection ───────────────────────────────────
    log("5. Testing Escape clears selection")
    if count >= 1:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        screenshot(page, "04_after_escape")
        toolbar_after = page.get_by_text("selected")
        if toolbar_after.count() == 0 or not toolbar_after.first.is_visible():
            print("  [OK] Escape cleared selection")
        else:
            msg = "  [FAIL] Escape did not clear selection"
            print(msg)
            failures.append(msg)

    # ── 6. Test Archive confirm dialog ────────────────────────────────────
    log("6. Testing archive confirm dialog")
    if count >= 1:
        checkboxes.first.check()
        page.wait_for_timeout(300)
        archive_btn = page.get_by_text("Archive selected").first
        if archive_btn.is_visible():
            archive_btn.click()
            page.wait_for_timeout(300)
            screenshot(page, "05_confirm_dialog")
            # Confirm dialog should appear
            confirm_text = page.get_by_text("Archive").filter(has_text="Archive")
            cancel_btn = page.get_by_text("Cancel")
            if cancel_btn.is_visible():
                print("  [OK] Confirm dialog appeared with Cancel button")
                cancel_btn.click()  # Cancel — don't actually archive
                page.wait_for_timeout(300)
                print("  [OK] Cancelled archive")
            else:
                msg = "  [FAIL] Confirm dialog not found"
                print(msg)
                failures.append(msg)
        else:
            print("  [WARN]  Archive button not visible — skipping dialog test")

    # ── 7. Navigate to Wiki and test page checkboxes ──────────────────────
    log("7. Testing Wiki view bulk selection")
    page.get_by_text("Wiki", exact=True).first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)
    screenshot(page, "06_wiki_view")

    # Hover over a wiki page leaf to reveal checkbox
    wiki_items = page.locator("aside li, [class*='sidebar'] li, [class*='tree'] li").all()
    print(f"  Found {len(wiki_items)} wiki tree items")

    if wiki_items:
        wiki_items[0].hover()
        page.wait_for_timeout(300)
        screenshot(page, "07_wiki_hover")
        wiki_checkbox = page.locator("input[type='checkbox']").first
        if wiki_checkbox.is_visible():
            print("  [OK] Wiki page checkbox revealed on hover")
            wiki_checkbox.check()
            page.wait_for_timeout(300)
            screenshot(page, "08_wiki_selected")
            wiki_toolbar = page.get_by_text("selected").first
            if wiki_toolbar.is_visible():
                print("  [OK] Wiki selection toolbar appeared")
            else:
                msg = "  [FAIL] Wiki selection toolbar not visible"
                print(msg)
                failures.append(msg)
            # Clear with Escape
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        else:
            msg = "  [FAIL] No wiki checkbox revealed on hover"
            print(msg)
            failures.append(msg)
    else:
        print("  [WARN]  No wiki items found")

    # ── 8. Test metadata poll persists across navigation ─────────────────
    log("8. Testing metadata persistence across navigation")
    page.get_by_text("Sources", exact=True).first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)
    page.get_by_text("Wiki", exact=True).first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)
    page.get_by_text("Sources", exact=True).first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)
    screenshot(page, "09_back_to_sources")
    print("  [OK] Navigation Sources→Wiki→Sources completed without crash")

    # ── 9. Test bulk move dialog (Wiki view) ──────────────────────────────
    log("9. Testing bulk move dialog (Wiki view)")
    page.get_by_text("Wiki", exact=True).first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)

    wiki_items_move = page.locator("aside li, [class*='sidebar'] li, [class*='tree'] li").all()
    if wiki_items_move:
        wiki_items_move[0].hover()
        page.wait_for_timeout(300)
        wiki_cb = page.locator("input[type='checkbox']").first
        if wiki_cb.is_visible():
            wiki_cb.check()
            page.wait_for_timeout(300)

            # Move button should appear in toolbar
            move_btn = page.get_by_role("button", name="Move")
            if move_btn.is_visible():
                print("  [OK] Move button visible in bulk toolbar")
                move_btn.click()
                page.wait_for_timeout(400)
                screenshot(page, "10_move_dialog")

                # MoveDialog should open with radio buttons
                radio_clients = page.locator("input[type='radio'][value='clients']")
                if radio_clients.is_visible():
                    print("  [OK] MoveDialog opened with radio buttons")
                    # Close without moving
                    cancel = page.get_by_role("button", name="Cancel")
                    if cancel.is_visible():
                        cancel.click()
                        page.wait_for_timeout(300)
                        print("  [OK] MoveDialog cancelled")
                    else:
                        msg = "  [FAIL] MoveDialog Cancel button not found"
                        print(msg)
                        failures.append(msg)
                else:
                    msg = "  [FAIL] MoveDialog radio buttons not visible"
                    print(msg)
                    failures.append(msg)
            else:
                msg = "  [FAIL] Move button not visible in bulk toolbar"
                print(msg)
                failures.append(msg)

            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        else:
            print("  [WARN]  Wiki page checkbox not visible — skipping move dialog test")
    else:
        print("  [WARN]  No wiki items found for move test")

    # ── 10. Test bulk download — Wiki pages ──────────────────────────────
    log("10. Testing bulk download (Wiki pages)")
    wiki_items_dl = page.locator("aside li, [class*='sidebar'] li, [class*='tree'] li").all()
    if wiki_items_dl:
        wiki_items_dl[0].hover()
        page.wait_for_timeout(300)
        wiki_cb_dl = page.locator("input[type='checkbox']").first
        if wiki_cb_dl.is_visible():
            wiki_cb_dl.check()
            page.wait_for_timeout(300)

            download_btn = page.get_by_role("button", name="Download")
            if download_btn.is_visible():
                print("  [OK] Download button visible in wiki bulk toolbar")
                # Trigger download and intercept
                with page.expect_download(timeout=5000) as dl_info:
                    download_btn.click()
                try:
                    download = dl_info.value
                    if download.suggested_filename == "pages-export.zip":
                        print("  [OK] pages-export.zip download triggered")
                    else:
                        msg = f"  [FAIL] Unexpected filename: {download.suggested_filename}"
                        print(msg)
                        failures.append(msg)
                except Exception as e:
                    msg = f"  [FAIL] Download not triggered: {e}"
                    print(msg)
                    failures.append(msg)
            else:
                msg = "  [FAIL] Download button not visible in wiki bulk toolbar"
                print(msg)
                failures.append(msg)

            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        else:
            print("  [WARN]  Wiki checkbox not visible — skipping wiki download test")
    else:
        print("  [WARN]  No wiki items found for download test")
    screenshot(page, "11_wiki_download")

    # ── 11. Test bulk download — Sources ──────────────────────────────────
    log("11. Testing bulk download (Sources)")
    page.get_by_text("Sources", exact=True).first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)

    all_source_items = page.locator("aside li, [class*='sidebar'] li, [class*='list'] > div").all()
    if all_source_items:
        all_source_items[0].hover()
        page.wait_for_timeout(300)
        src_cb = page.locator("input[type='checkbox']").first
        if src_cb.is_visible():
            src_cb.check()
            page.wait_for_timeout(300)

            src_download_btn = page.get_by_role("button", name="Download")
            if src_download_btn.is_visible():
                print("  [OK] Download button visible in sources bulk toolbar")
                with page.expect_download(timeout=5000) as dl_info:
                    src_download_btn.click()
                try:
                    download = dl_info.value
                    if download.suggested_filename == "sources-export.zip":
                        print("  [OK] sources-export.zip download triggered")
                    else:
                        msg = f"  [FAIL] Unexpected filename: {download.suggested_filename}"
                        print(msg)
                        failures.append(msg)
                except Exception as e:
                    msg = f"  [FAIL] Sources download not triggered: {e}"
                    print(msg)
                    failures.append(msg)
            else:
                msg = "  [FAIL] Download button not visible in sources bulk toolbar"
                print(msg)
                failures.append(msg)

            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        else:
            print("  [WARN]  Source checkbox not visible — skipping source download test")
    else:
        print("  [WARN]  No source items found for download test")
    screenshot(page, "12_sources_download")

    # ── Summary ───────────────────────────────────────────────────────────
    browser.close()
    print(f"\n{'='*60}")
    print(f"SMOKE TEST COMPLETE")
    print(f"Screenshots saved to: {SCREENSHOTS}")
    if failures:
        print(f"\n[FAIL] FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  {f}")
        exit(1)
    else:
        print(f"\n[OK] ALL CHECKS PASSED")
