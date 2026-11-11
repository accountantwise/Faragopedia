# ADR-0011: Children on callsheets are not recorded in the wiki

> **Status:** Accepted
> **Date:** 2026-11-11
> **Decided by:** Nick + Claude

## Context

The callsheet import created a contact page for every talent row, and a company page for
whatever was in the row's company column. On kids campaigns (Zara Kids and others) and on
shoots casting child actors, that meant:

- about 70 contact pages for children, mostly a first name, some with a mobile number that
  is usually a parent's;
- company pages named after the "care of" route in the company column, e.g.
  `c/o <parent's first name>, agent <name> @ <agency>`, which put a parent's name in a page
  title next to a child;
- a "MOTHER" row on a music-video job.

Nothing in the pipeline or in ADR 0009's safeguards looked for any of this. A sales wiki has
no use for children's details, and holding them is a safeguarding and data-protection risk
for Farago.

## Decision

1. **Nothing personal about a child is written to the wiki.** No contact page, no name, phone,
   age, parent name or agent-to-child link. A job page keeps one anonymous line under its
   People table: how many children and which agencies (`N child models on this job (via …)`).
2. **Who counts as a child** is inferred, since callsheets carry no ages: talent on a kids job
   (campaign, title or folder names Kids/Baby/Junior/Children), talent with a child role
   (YOUNG …, CHILD, KID, BOY, GIRL, TEEN), or talent booked through a kids agency. Parent and
   guardian roles are withheld too. It errs towards withholding: hiding an adult model's row
   on a kids job costs nothing.
3. **Where it runs:** `tools/callsheet_ingest/minors.py`, applied in `push_job.plan_job` before
   the roster is built, so withheld rows never reach rendering, page creation or quarantine.
4. **"c/o" company values:** `c/o X, agent Y @ Agency` becomes `Agency`; any other `c/o …` is
   quarantined (map it with `--aliases`).
5. **Lint backstop:** `backend/agent/data_lint.py` flags a `c/o` company page, and a talent-like
   contact whose page mentions a kids agency or a `c/o … @` route.
6. **Tests use invented names only.** This repo is public.

## Clean-up done on 2026-11-11

Live wiki on the VPS, via the API: 64 child and parent contact pages (plus 3 below) and the 5 `c/o` company pages
permanently deleted (archive emptied of them too). Eight job pages had their child rows replaced
by the anonymous line.

Four first-name pages had merged a child with a later adult-job booking of the same name, only
because both got the same slug. `george` belongs to a real adult contact (Concrete, from the
meeting log): kept, with the child's entries removed. `pippa`, `isaac` and `gaia` were deleted
too. Each was a child at a kids agency with a chaperone, then 10–15 months later a model at an
adult agency. They were probably different people, but nothing on a callsheet proves the later
one was 18 or over, and a 16-year-old can move to an adult board. The pages held only a first
name, so their adult-job rows keep the name as plain text with no link. Identity was not
researched: that would mean trying to identify a possible child, which this ADR exists to avoid.
Farago's booking records are the only reliable source if it ever matters. The page names were also removed from `wiki/log.md` and `.page-metadata.json`.
`sources/`, `archive/` and both existing snapshots held no child data. Before any change, an
encrypted full backup of the workspace was taken outside this repo and the VPS (Nick holds it).
Replaying `minors.py` over every extract withholds exactly the same 75 rows on the same 8 jobs.

## Consequences

- Job pages for kids campaigns no longer say who was cast; the job folder still does, for
  anyone at Farago who needs it.
- Detection is heuristic. A child booked through an agency with an adult-sounding name on a
  non-kids job would get through; add the agency to `KIDS_AGENCIES`. Lint is the backstop.
- **Known limit:** callsheets carry no ages. A 16- or 17-year-old booked through an adult agency
  on an adult job (London Fashion Week allows models from 16) looks exactly like an adult, so
  "under 18" can only be enforced as far as the callsheet shows it.
- First-name-only talent pages are shared by slug, so different people with the same first name
  land on one page. That broke the "never link records by talent name" rule here and is how a
  child's history ended up on an adult's page. Worth revisiting for all talent (open).
- The callsheet extracts (`CALLSHEET_EXTRACTS_DIR`) still contain the children's rows, as the
  source callsheets in Farago's job folders do. They stay outside this repo.
- Open: whether Farago want the extracts' child rows redacted too, and whether Simon wants to
  confirm this policy against Farago's own safeguarding policy.
