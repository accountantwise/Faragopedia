---
name: faragopedia-notes-cleanup
description: Standing rule for the Faragopedia wiki - after ANY AI processing that writes pages (ingest, enrichment, merges, one-off fixes), clear the notes field on contact and company pages, keeping only notes flagged "HUMAN:". Use at the end of every such task, or when notes look like a copy of the Overview.
---

# Faragopedia notes cleanup

Rule (Nick, 2026-09-25): `notes:` must not become a second, drifting copy of the Overview. It
stays empty unless a note is flagged for a human — its value starts with `HUMAN:`. Those are
never cleared. People can use the same prefix to protect a note of their own.

```
cd Faragopedia-Sales/tools/wiki_maintenance
python clear_notes.py          # dry run: counts + every HUMAN: note that is kept
python clear_notes.py --live
```

`enrich_companies.py` and `correction_pass.py` already run it on the pages they wrote at the end
of a `--live` run. Anything else that writes pages — including a backend ingest run or a manual
script — must run it by hand before the work is reported done.

When you write a note yourself, only ever write a `HUMAN:` flag, and say exactly what a person
should check: `HUMAN: check surname spelling - page says 'Hanh', CRM email is madison.hahn@...`.

The script handles multi-line values and repairs orphaned continuation lines left by an older
version; it touches nothing but the notes block.
