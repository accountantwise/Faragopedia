# Tailoring the Wiki for the Sales Manager — Analysis & Recommendations

**Source compared:** `New Business _ Farago London - Copy.xlsx` (MEETING LOG + GLOBAL DATABASE sheets)
**Against:** current scaffold in `/Wiki-Concept/` (SCHEMA.md, clients/, prospects/, contacts/, photographers/, productions/, sources/)
**Date:** 2026-04-20

---

## 1. What her spreadsheet actually is

The workbook is doing three very different jobs that have been flattened into two sheets. Naming them properly is the first design decision — the current wiki doesn't have a home for two of the three.

**Job A — Activity log (MEETING LOG, rows 2–28).** A running record of meetings held in 2026 with the outcome scrawled next to each: "Won jobs!", "Bidding on La Vie Est Belle", "Meeting on 14th April", "Won showroom & show!". This is a sales pipeline/CRM log, not a contact list. There is no column structure — outcomes sit in the notes cell.

**Job B — Outreach queue (MEETING LOG, rows 32–49).** An email list of people she's been trying to reach, separate from people already met. Mixed in are raw email addresses embedded inside the company-name cell (e.g. `Akris - Annachiara Esposito -`, `Palm Angels - Chantal Kimberly <ck@palmangels.com>`). Cold pipeline, essentially.

**Job C — Master contact book (GLOBAL DATABASE + MEETING LOG rows 72+).** Her address book, organised by **industry vertical first, region second**. Columns: `Company | Region | Name | Title | Email | Number | Notes | Meetings`. Segments used: Enquiries, Agencies, Art Directors, High Fashion / Fashion, Contemporary / New, Streetwear / Sportswear / Outdoor, Footwear, Lingerie / Swimwear, Alcohol, Product / Home, Eyewear, Jewellery, Makeup.

The single biggest structural signal: **industry segment is her primary mental index, not client-vs-prospect.** The wiki schema currently inverts that — it uses stage (client/prospect) as top-level and has no concept of segment at all.

---

## 2. Quantitative patterns worth designing around

Pulled from the database sheet:

- **Geography is Paris-heavy, not London-heavy.** 66 Paris contacts, 21 Italy, only 5 tagged London, plus Amsterdam as an implicit sub-section. Despite the sheet being titled "Farago London New Business," her pipeline is continental. The schema needs `region` as a first-class field, and Paris needs to be treated as a segment not a footnote.
- **"Hub accounts" have deep contact trees.** Puig (8 contacts, spanning JP Gaultier and L'Artisan Parfumeur subsidiaries), Yves Rocher (6), Shiseido group (10+ across BPI, Narciso Rodriguez, Issey Miyake, NARS, Serge Lutens, Skincare), Nike (8+ across EMEA Amsterdam and global), Rimowa (4 across Paris and Shanghai). She is not really selling to brands — she's selling into parent groups. **The wiki needs a `parent_group` concept or a `groups/` folder.**
- **The roles she sells into cluster tightly.** Title keywords by frequency: Director (21), Content (15), Manager (15), Marketing (13), Head (12), Image (12), Producer (10), Creative (10), Brand (7), Production (7). She is pitching to Heads of Image, Heads of Production, Creative Directors, and Marketing/Content Directors. A controlled `role_category` enum would let her query "all Heads of Image at LVMH brands" in one step.
- **She tracks people, and people move.** Adam Nait (Lancôme) appears in both the meeting log and the makeup database. Careers in fashion beauty move annually. The current `contacts/` schema has `org` + `linked_orgs` but no career history section and no "previous roles" — so when a producer moves, she either loses them or overwrites the past.

---

## 3. Gaps between her Excel and the current wiki schema

| Her spreadsheet has | Current wiki has | Gap |
|---|---|---|
| Industry segments (13 of them) as primary grouping | No segment field | **Critical** — add `industry_segment` enum |
| Agencies as a first-class category (M+A, Webber, Magnet, Streeters, Bryant, Art Partner, LGA, Artistry, M.A.P., New School, Canvas Rep, Trouble, Walter Schupfer, Art + Commerce) | Only `photographers/`; agencies bundled into prospects | **Critical** — add `agencies/` folder; an agency is a gatekeeper to multiple photographers, not a prospect |
| Art Directors as a first-class category (SJ Todd, Ed Quarmby, Jaime Perlman, Ben Reardon, Holly Hay, David Lane, Maxine Leonard, Jamie Reid) | No home — would fall into `contacts/` and lose structure | **Add** `art-directors/` folder (they are freelancers who pull in brand work, not employees of any one client) |
| Parent groups (LVMH, Kering, Puig, Shiseido, L'Oréal, Richemont) implied by the data | No parent-group concept | **Add** `brand_groups/` folder or `parent_group:` field on clients/prospects |
| Region tagged per contact | No region on any entity | **Add** `region` field to clients, prospects, contacts, agencies |
| Deal stage (meeting booked / meeting held / bidding / won / lost) | Only `status: active/inactive` on clients and `status: prospect/target` on prospects | **Replace** with a proper stage enum |
| "Ideal Hit List" = top-priority targets, distinct from the wider watchlist | `tier: A/B/C` — same letter-grade for everything | **Add** `hit_list: true/false` boolean or split priority from tier |
| "Enquiries" = inbound leads | No distinction between inbound and outbound | **Add** `source: inbound/outbound/referral` field on prospects |
| Activity log — meetings, emails, bids, outcomes over time | No concept of activity | **Add** `activity/` folder or append-only log section per company page |
| Career history of individual contacts | `contacts/` has `org` + `linked_orgs` but no timeline | **Add** `## Career History` section with dated entries |
| Multiple contacts per company with distinct roles | Supported, but not cross-indexed by role | **Add** `role_category` enum to contacts so she can query "all Heads of Image" |
| Phone number field | Not in `contacts/_type.yaml` | **Add** `phone` field |

---

## 4. Proposed directory structure

```
Wiki/
├── SCHEMA.md
├── SCHEMA_TEMPLATE.md
├── index.md
├── log.md
├── company_profile.md
│
├── brand-groups/          # NEW — LVMH, Kering, Puig, Shiseido, L'Oréal, Richemont, Inditex, etc.
│   └── lvmh.md
│
├── clients/               # KEEP — brands we've actively produced for
├── prospects/              # KEEP — brands in active pursuit
├── watchlist/              # NEW — brands on the radar but not being actively worked
├── enquiries/              # NEW — inbound leads (separate pipeline from cold outbound)
│
├── agencies/               # NEW — photographer/talent agencies (M+A, Webber, Magnet, Bryant, etc.)
├── art-directors/          # NEW — freelance ADs who bring in work (SJ Todd, Ed Quarmby, etc.)
├── photographers/          # KEEP
│
├── contacts/               # KEEP but enrich
├── productions/            # KEEP
├── activity/               # NEW — dated interaction log (one file per month or one per engagement)
│
└── sources/
```

Rationale for each addition:

- **`brand-groups/`** — lets her ask "what's happening across LVMH beauty?" in one query. Roll-up pages don't need frontmatter-heavy schemas, just a list of child brands and cross-brand contacts.
- **`watchlist/`** vs **`prospects/`** — today everything not-a-client is a prospect. Her spreadsheet has a huge tail of names under sections like Footwear > Tod's, Church's, Ecco, Geox where the intent is "know they exist, not pursuing." Watchlist removes noise from the active prospect view.
- **`enquiries/`** — she already separates inbound in her sheet under a distinct ENQUIRIES heading (Jean Paul Gaultier, Vertus). An inbound lead is a different beast commercially — it needs a response-time KPI, not an outreach plan.
- **`agencies/`** — an agency is an entity that represents many photographers and sometimes art directors. Meeting with M+A is meeting with a roster, not a photographer. Currently they'd be misfiled as prospects.
- **`art-directors/`** — a freelance AD (SJ Todd was credited on the McQueen Holiday Edit) is the person who picks the production company. She sells to them separately from selling to the brand. They belong in their own roster.
- **`activity/`** — the one thing the current schema has no home for: "on Tuesday I met Britt Andress from Magnet and she said they're pitching Range Rover x Wimbledon." Put those as dated files so the wiki agent can produce "activity this week" and "contacts gone cold" queries.

---

## 5. Proposed schema changes (frontmatter)

### clients/prospects/watchlist — unified core fields

```yaml
---
type: client | prospect | watchlist
name:
parent_group:           # e.g. lvmh, kering, puig, shiseido, l-oreal
industry_segment:       # enum (see below)
region:                 # London | Paris | Milan | Amsterdam | New York | LA | Shanghai | Global
hq:
tier: A | B | C
hit_list: true | false  # NEW — is this on the 2026 Ideal Hit List?
deal_stage:             # NEW — aware | contacted | meeting-booked | meeting-held | pitching | bidding | won | lost | dormant
source: outbound | inbound | referral | existing
relationship_since:
last_contact:
next_action:            # NEW — one-liner: "email Tom Shickle re Celine spring pitch"
next_action_date:       # NEW
source_count:
---
```

### industry_segment enum — lifted from her sheet

`high-fashion` · `contemporary` · `streetwear` · `footwear` · `lingerie-swimwear` · `alcohol` · `product-home` · `eyewear` · `jewellery` · `makeup` · `skincare` · `fragrance` · `beauty-group` · `pharma` (Novartis, Sanofi, AbbVie, Merck, AstraZeneca, Roche, Pfizer are all in her meeting log — worth its own segment).

### contacts — enriched

```yaml
---
type: contact
name:
role:
role_category:          # NEW — enum below
org:                    # current employer
parent_group:           # NEW
region:                 # NEW
email:
phone:                  # NEW
linked_orgs: []
last_contact:
---
```

Sections: `## Bio` · `## Role & Responsibilities` · `## Career History` · `## Relationship History` · `## Productions Involved` · `## Notes`

**`role_category` enum** (derived from title-keyword analysis of her book):
`head-of-production` · `head-of-image` · `creative-director` · `art-director` · `marketing-director` · `marketing-manager` · `brand-director` · `content-director` · `content-producer` · `producer` · `agent` · `art-buyer` · `communications` · `other`

The point isn't perfect categorisation — it's so she can run "all Heads of Image in Paris" as a Dataview query and get 20 names back immediately.

### agencies — new type

```yaml
---
type: agency
name:
region:
represents: []          # list of wikilinks to photographers/ADs
hit_list: true | false
tier: A | B | C
last_contact:
---
```
Sections: `## Overview` · `## Key Agents` · `## Represented Talent` · `## Relationship History` · `## Productions Via This Agency`

### art-directors — new type

```yaml
---
type: art-director
name:
based:
represented_by:         # wikilink to agency if any, else "freelance"
typical_clients: []
hit_list: true | false
---
```
Sections: `## Bio` · `## Style Notes` · `## Recent Work` · `## Relationship History` · `## Sources`

### activity — new type

One file per interaction, named `YYYY-MM-DD-short-slug.md`. Lightweight:

```yaml
---
type: activity
date:
kind: meeting | call | email | bid | pitch | won | lost
with_contact: []        # wikilinks
with_company: []        # wikilinks
outcome:                # one of: positive | neutral | negative | open-loop
follow_up_date:
---
```
Sections: `## Summary` · `## Notes`

This replaces the free-text "Meetings" column in her Excel and makes it queryable.

### brand-groups — new type

```yaml
---
type: brand-group
name:
hq:
brands_owned: []        # wikilinks to clients/prospects
key_contacts: []        # wikilinks to cross-group contacts (e.g. group heads of production)
---
```

---

## 6. Insights the wiki agent should be able to produce

This is where the wiki earns its keep vs the spreadsheet. Each of these should work out of a single-file Dataview query once the schema above is in place.

**Sales-operational**
- "Which Ideal Hit List targets have I not contacted in 60 days?" (stale priorities)
- "Open bids and their age" (from activity where kind=bid and no closing activity yet)
- "Meetings this month with outcomes" (weekly report)
- "Wins year-to-date, grouped by industry segment and region"
- "Prospects with `deal_stage: meeting-booked` and no `next_action` set" (data-hygiene gap)
- "Everyone I've emailed with no reply logged" (outreach follow-up queue)

**Relationship-strategic**
- "All contacts across the Shiseido group" / "All contacts across LVMH beauty"
- "Who at Puig do I know, what do they do, when did I last speak" (account mapping)
- "Paris-based Heads of Image I have not met"
- "Photographers represented by M+A whom I've worked with" (agency-to-talent roll-up)
- "Art Directors who have worked with more than one of my current clients" (warm-introduction candidates)

**Intelligence**
- "Contacts whose role has changed in the last 6 months" (career-move detector — from the Career History section)
- "Brands that have appeared in 3+ news sources but aren't yet a prospect" (opportunity radar)
- "Agencies I've never had a meeting with" (coverage gap)
- "Segments where my pipeline is thin" (e.g. Alcohol has 3 names — should I develop it?)

**Composition**
- "Draft an outreach email to Hannah Kitchen at Jo Malone referencing my Gentlewoman Surfacing credit" (the wiki already knows the credit, the relationship stage, and the company tier — it can write the email)
- "Brief me before my Tuesday with Britt Andress" (read the Magnet agency page + all activity with Britt + current pitch status — render as a one-pager)

---

## 7. Ingestion workflow for migrating the spreadsheet

The cleanup is non-trivial; it's worth doing once, properly.

1. **Extract each GLOBAL DATABASE segment as its own pass.** Trailing whitespace is on almost every cell ("Magnet ", "L'Oreal ", "Paris "). Strip on ingest.
2. **Fill down the Company column.** Many rows omit company because the company is implied from the row above (e.g. rows 86–88 for Nike; rows 71–72 for Loewe's additional contacts). The agent should forward-fill before creating contact records.
3. **Deduplicate companies.** `L'Oreal`, `L'Oréal`, `L'Oreal Luxe` need a canonical form. `SHISEIDO` vs `SISHEIDO` (row 338) is a typo to fix on import. `Converse / Nike` should resolve to two links, not one.
4. **Parse embedded emails.** Rows like `Akris - Annachiara Esposito -`, `Palm Angels - Chantal Kimberly <ck@palmangels.com>`, `Andrea Zini - <andrea@thesolo.house>` need splitting into company / name / email.
5. **Parse "Name I Title" patterns in the makeup section.** `Yaël Tuil I VP`, `Christophe Venot I Global Brand Director...` — split on `I` (which is a typo for the pipe `|`).
6. **Map MEETING LOG rows 2–28 to activity entries.** Each row becomes either an `activity/` entry (if it describes a meeting) or a status update on the corresponding prospect page.
7. **Map MEETING LOG rows 32–49 to outreach activity** with `kind: email` and `outcome: open-loop`.
8. **Assign `hit_list: true`** to anything that was meant to go under `IDEAL HIT LIST 2026` — that header has been empty in the sheet for months but she clearly thinks about it. Ask her to nominate ~20 targets.
9. **Assign `deal_stage`** from the notes: "Won jobs!" → `won`, "Bidding" → `bidding`, "Meeting on 14th April" → `meeting-booked`, otherwise → `contacted` or `aware`.
10. **Build the brand-groups pages last**, once all clients/prospects exist, so the `brands_owned` wikilinks resolve.

Rough count: this migration produces roughly 230–260 company pages, 400+ contact pages, 40–50 activity entries, 15 agency pages, 8 art-director pages, and 5–6 brand-group pages on first pass.

---

## 8. Data-quality issues she'll want flagged (lint targets)

Once the schema is set, the `lint` operation should flag:

- Companies with no region set
- Prospects with `hit_list: true` and no activity in the last 90 days
- Contacts with `last_contact` more than 180 days ago
- Clients with `deal_stage: won` but no production entry logged
- Duplicate contact names across organisations (same person, or coincidence?)
- Contacts with a title but no `role_category`
- Brand groups whose `brands_owned` list is shorter than their actual children in `clients/` + `prospects/`
- Activity entries without a `follow_up_date` where `kind: meeting` and `outcome: positive`

These are concrete, not philosophical — each can fire automatically on `lint`.

---

## 9. What to trim from the current scaffold

- **`SCHEMA_TEMPLATE.md`** can stay but the template itself is thin and will need re-generating once the new entity types are added. Add placeholder sections for the new types.
- The example `productions/` and `prospects/` files in the folder are useful as format references; keep them until the first real ingest runs, then archive them to `sources/assets/examples/`.
- `company_profile.md` is fine and immutable as stated. Consider adding one line: "primary sales axis = industry segment × region, not client/prospect" so any future agent picks up the design intent.

---

## 10. Order of operations I'd recommend

1. Confirm the proposed segment list, region list, deal-stage enum, and role-category enum with her — these are the only schema choices where her opinion is load-bearing. Everything else follows.
2. Update `SCHEMA.md` and the `_type.yaml` files. Create empty `agencies/`, `art-directors/`, `brand-groups/`, `enquiries/`, `watchlist/`, `activity/` folders.
3. Run the migration from the spreadsheet as described in Section 7 — ideally in a single ingest session so cross-links resolve in one pass.
4. Build 3–4 canned Dataview queries in `index.md` ("This week's meetings", "Hit list status", "Stale priorities", "Open bids") so she sees value on day one.
5. Retire the spreadsheet. Or keep it read-only for 90 days as a safety net, then kill it.

The faster step 5 happens, the sooner she stops double-entering data.
