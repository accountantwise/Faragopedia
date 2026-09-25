---
name: faragopedia-fix-and-merge
description: Merge verified duplicate Faragopedia company pages, create missing company or contact pages (callsheet clients or CRM contacts with no page), and repair broken company/contact wikilinks, via a reviewed plan file. Use when a report flags duplicates, a callsheet client or CRM person has no page, or links like [[Very]] don't resolve.
---

# Fix, merge and fill gaps in Faragopedia

Toolkit: `Faragopedia-Sales/tools/wiki_maintenance/` — read its README.md first.

## 1. Find the gaps (read-only)

- Duplicates: `possible duplicate` flags in an `enrich_companies.py` report, or two pages with
  the same website. **Only a human can confirm a duplicate** — ask, and ask which page survives
  (prefer the one with hand-written prose; its name should match Wikidata/the brand).
- Callsheet clients with no page: a callsheet whose `client:` doesn't resolve
  (`Wiki().resolve_clients(...)` returns `[]`). Skip `unknown`.
- CRM companies with no page: CRM Contacts-tab rows whose company doesn't resolve. Skip template
  rows (e.g. "Acme Group") and rows with a job role typed as the company; report those instead.

## 2. Write the plan

Copy `example_plan.json` to `plans/<date>.json` (ignored by git: it holds contact details).
`merges` = verified pairs only. `new_companies` = name + industry following the precedent of
comparable pages (never invent a new industry) + plain-text parent. `new_contacts` = people named
only in callsheet Contact cells or the Outreach Log. CRM Contacts-tab people are created
automatically once their company has a page (first-name-only rows are skipped).

If new companies need websites, research them as in `faragopedia-enrich-companies` step 3 and
pass the filtered result with `--company-research` (`{slug: {website, hq, notes}}`; a `notes`
value is only kept if it starts with `HUMAN:`).

## 3. Dry run, check, back up, go live

```
python correction_pass.py --plan plans/<date>.json --out out/dry
```

Check `out/dry/report.json`: every `created` path, `contact_company_unresolved` (companies that
still have no page), `spelling_flags`, and a few diffs. Then back up (`wikiapi.export_backup`)
and rerun with `--live` (the notes cleanup runs automatically on written pages; merges are
appended to `merge_history.json` — commit that file).

Finish with `python enrich_companies.py --all --live` so survivors and new pages get their
sections, then verify no page links to a merged-away slug.

## Report back

What was merged/created/repaired, what still needs a human (CRM rows, unknown clients,
`HUMAN:` notes written), backup path. Update `Faragopedia-Sales/docs/status.md`.
