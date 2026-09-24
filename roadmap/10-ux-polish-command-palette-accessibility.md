# 10 — UX Polish: Command Palette, Onboarding, Feedback & Accessibility

| Field | Value |
| --- | --- |
| Priority | P2 — high-ROI adoption polish; ship incrementally alongside everything else |
| Effort | M (2–3 sessions; many independent quick wins) |
| Dependencies | 06 (routing) for palette navigation; otherwise standalone |
| Repo | `Faragopedia-Sales` |
| Branches touched | new `feature/ux-polish` (or fold quick wins into other branches) |
| Review status | **UPGRADED & APPROVED** 2026-07-07 — several problem claims corrected against code: 8 aria-labels exist (not 1), loading spinners/skeletons exist widely (the gap is consistency, not absence), Wiki search **already shows a result count**, the sidebar **already highlights the active view** (missing only `aria-current`), and the mojibake placeholder could not be found in the code. Focus-trap absence and missing favorites/recents confirmed. Modal strategy updated (native `<dialog>`/Radix preferred over focus-trap-react). See `00-review-log.md`. |

## Problem (verified state)

The live-app and frontend reviews surfaced real UX/a11y gaps, but the original list overstated several — corrected here so a build session fixes real things:

- **Accessibility is thin but not absent**: 8 `aria-label`s exist (App.tsx:494, ErrorToast, LinkView ×2, SetupWizard ×4); 20+ icon-only buttons (close/X, arrows, action icons) have **no accessible name**. First task is an audit that produces the actual list.
- **No focus management anywhere** (verified): none of the 9 dialogs/drawers (ConfirmDialog, MoveDialog, AddSourcesModal, ImportWikiModal, SettingsDrawer, Delete/Duplicate/Rename workspace modals) trap focus, handle Escape, or restore focus on close.
- **Feedback is inconsistent, not missing**: `Loader2`/`animate-spin` appears in 20+ places and LintView has a skeleton — but coverage is patchy (e.g. initial page-tree load, save/move actions), errors still vanish through silent catches (structural fix in 06), and there are no success toasts for save/move/delete.
- **No command palette (Cmd+K)**, no discoverable keyboard shortcuts — table stakes (VS Code, Linear, Notion, Obsidian). Esc handling exists piecemeal (LinkView, SourcesView, WikiView clear-selection) but nothing global.
- **Empty states exist in LinkView and ArchiveView** (verified strings); Wiki and Sources views lack guidance + a primary action.
- **Active view**: the sidebar already highlights the active item visually (Sidebar.tsx:58-61, blue bg) — add `aria-current="page"`, don't rebuild.
- **No breadcrumbs**; **Wiki search already shows "N results"** (WikiView.tsx:1025) and LinkView shows "N of M" — the counter gap, if any, is Sources search only.
- **No favorites/recents** (verified absent).
- ~~Search placeholder mojibake~~ — **could not be reproduced in the code** (no U+FFFD or mojibake byte patterns in any `placeholder=`). Spend 10 minutes verifying against the live site (it may have been a data artifact or already fixed); drop the item if unreproducible.

## Design

### A. Command palette (Cmd/Ctrl+K)

- A modal fuzzy-search palette: jump to any page, switch view, switch workspace, run actions (New Page, Ingest, Lint, Settings, Toggle Theme), and search content (wired to semantic search from 09 when available, keyword index until then).
- Build on the router (06) — selecting a result `navigate()`s. Use **`cmdk`** (verified maintained, React 18/19 compatible, built-in scoring is sufficient — no extra fuzzy lib needed). Keyboard-first, fully accessible (roving focus, aria-activedescendant come with cmdk).

### B. Keyboard shortcuts + help

- Global: `Cmd+K` palette, `?` shortcuts help overlay, `g w`/`g s`/`g l` view jumps, `n` new page, `e` edit, `Esc` closes panels (unify the existing piecemeal handlers into one layer).
- A shortcuts help modal listing them (discoverability). Suppress single-key shortcuts while focus is in an input/textarea/contenteditable.

### C. Feedback & states

- **Audit-first**: list every async action and its current feedback; fill gaps — skeletons for page tree/lists, disabled+spinner on buttons mid-action (match the existing `Loader2` idiom rather than inventing a new one).
- Route all errors through the toast layer (the silent-catch fix from 06); success toasts for save/move/delete/ingest.
- Add `aria-current="page"` to the existing sidebar active state.
- Empty states for Wiki and Sources (LinkView/Archive already have them): message + primary action ("Add your first source", "Create a page").
- Onboarding: a short first-run tour (after the setup wizard / admin creation) highlighting Wiki, Sources, Chat, Links. Store "seen" in user prefs (03) or localStorage.

### D. Accessibility pass

- `aria-label` (+ tooltip) on every icon-only button surfaced by the audit (~20+, exact list from task 1).
- **Modal focus management** — preferred: migrate dialogs to the **native `<dialog>` element** (focus trap, Esc, and top-layer for free; fully supported in the 2026 browser baseline) or **Radix UI Dialog** if richer composition is wanted; `focus-trap-react` only as a shim for anything hard to migrate. All 9 dialogs get: trap, Esc-to-close, return-focus-to-trigger.
- Visible, high-contrast focus rings across button variants.
- Color contrast in light + dark to WCAG AA (audit the gray-on-gray secondary text).
- Semantic headings per view (the review found flat/missing `h1`s).

### E. Small wins

- Breadcrumbs in Wiki (`Workspace / Entity / Page`).
- Result count for Sources search (Wiki and LinkView already have counts).
- Favorites/recents: star a page; "Recent" and "Starred" sections in the sidebar (per-user once 03 lands, else localStorage).
- Verify-or-drop the search-placeholder encoding report against the live site.

## Implementation plan

1. **A11y audit + quick wins** (independent, low-risk): enumerate unlabeled icon buttons, add aria-labels + tooltips; fix focus rings; add `aria-current`; check the placeholder report. *Can be merged immediately.*
2. **Modal focus management** across all 9 dialogs (native `<dialog>` or Radix); Esc-to-close consistency; return focus on close.
3. **Feedback layer**: gap-audit then skeletons + spinners + consistent success/error toasts (depends on 06's error routing; coordinate).
4. **Empty states** for Wiki + Sources.
5. **Command palette** (`cmdk` + router): navigation + actions + content search; full keyboard a11y.
6. **Shortcuts + help overlay** (unify Esc handling; input-focus suppression).
7. **Onboarding tour** (first-run, dismissible, per-user).
8. **Breadcrumbs, Sources result count, favorites/recents.**
9. **Verify** with webapp-testing incl. a keyboard-only pass (Tab through app, operate palette, open/close modals) and a light/dark contrast check.

## Acceptance criteria

- `Cmd+K` opens a palette that can navigate to any page/view and run key actions by keyboard alone.
- Every icon-only button has an accessible name; tabbing shows a clear focus ring; all 9 modals trap focus, close on Esc, and restore focus on close.
- Async actions show loading state; failures show a toast (nothing fails silently); saves/moves/deletes show success feedback.
- The active view exposes `aria-current="page"`.
- Empty Wiki/Sources show guidance + a primary action.
- Sources search shows a result count (Wiki/LinkView already did).
- Light and dark modes pass a WCAG AA contrast spot-check.

## Notes

- Many items (a11y labels, `aria-current`, counts) are <1h and can ride along in other branches rather than waiting for a dedicated pass.
- The command palette gets dramatically better once semantic search (09) is in — wire it to fall back to keyword search until then.
