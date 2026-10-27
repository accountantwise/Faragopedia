---
name: faragopedia-enrich-companies
description: Rebuild and enrich Faragopedia company pages (schema sections, contacts, job history, status, Wikidata/Wikipedia profile, Outreach Log meeting history, researched news) on a live wiki. Use when company pages look thin or stale, after new callsheets or CRM rows land, or when asked to enrich/refresh companies.
---

# Enrich Faragopedia company pages

Toolkit: `Faragopedia-Sales/tools/wiki_maintenance/`. **Read its README.md first**: it holds
Nick's rules (no RocketReach, 18-month status rule, industry never changed, Farago's own
pages skipped, notes rule) and the pitfalls that already broke production once.

## 1. Rebuild from free data (no model tokens)

```
cd Faragopedia-Sales/tools/wiki_maintenance
python enrich_companies.py --all --out out/dry            # dry run: renders + diffs, writes nothing
```

Read `out/dry/report.json` before going further:
- `error` entries: stop and fix.
- `possible duplicate`: a callsheet credits another company page for this company's people.
  Report it to the user; never merge on your own (see `faragopedia-fix-and-merge`).
- `no verified public profile`: expected for small agencies and people filed as companies.
- Spot-check several `.diff` files, including at least one hand-written page (they must keep
  their prose) and one page with Outreach Log entries.

Then back up and write:

```
python -c "from pathlib import Path; import wikiapi; print(wikiapi.export_backup(Path('backups/pre-enrich.zip')))"
python enrich_companies.py --all --out out/live --live     # also runs the notes cleanup
```

## 2. Prove it is idempotent

Run again on pages with outreach and jobs, e.g.
`python enrich_companies.py --only vuori mango abbvie zara --out out/check` — every line must
say `same`. If anything changes, a generated line isn't being recognised: fix
`GENERATED_MEETING` / `GENERATED_CONTACT` before any further live run.

## 3. Researched websites and news (optional, costs tokens)

Only for pages worth it: Farago clients and prospects with recent outreach, never person-named
pages. Give each research agent (Haiku is enough) a JSON list of
`{slug, name, website, industry, context}` where `context` says what the company did on Farago
jobs; that context is what stops it picking a namesake. Ask for, per slug:
`{"website": url|null, "website_evidence": str|null, "news": [{"date": "YYYY-MM", "headline", "summary", "url", "source"}]}`,
max 2 searches per company, items dated within the last 12 months, `[]` is fine.

**Filter the output before use** (every one of these was needed on real output):
- website must be a root domain (no path), not a directory/social site (models.com, LinkedIn,
  Instagram, …), must resolve, and its page title should contain the company name;
  for CRM companies it must match the staff email domain;
- drop news outside the date window, without a URL, self-descriptions, articles *by* a
  magazine rather than *about* it, and all news for a company with no confirmed website
  (namesake risk);
- anything matched by name only gets a `HUMAN:` note.

Then `python enrich_companies.py --only <slugs> --research research.json --live`.

## Report back

Pages changed, verified Wikidata matches, flags needing a human, and the backup path.
Update `Faragopedia-Sales/docs/status.md`.
