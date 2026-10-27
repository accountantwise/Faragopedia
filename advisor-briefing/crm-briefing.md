# Why not just buy a CRM?

**Internal briefing · For advisors · Farago BD system · July 2026**

A CRM is a **system of record** — a filing cabinet someone has to fill in by hand. What we built is a **system of intelligence**: it finds the leads, verifies the contacts, writes the record, and turns every meeting into knowledge that compounds. The real choice isn't "CRM vs. this." It's **a database someone must feed** vs. **a loop that feeds itself.**

---

## The engine — one closed loop across two purpose-built systems

The RocketReach lead engine and the Faragopedia knowledge graph aren't two tools bolted together — they form a cycle. Research flows into outreach; outreach flows into institutional memory; and that memory calibrates the next round of research. A CRM sits at one point on this loop (storage) and leaves every other step to a human.

```
  LEAD ENGINE (RocketReach · Sheets)
  ┌─────────────────────────────────────────────────────────────────────┐
  │  01 Prospect  ──▶  02 Enrich  ──▶  03 Outreach                        │
  │  AI drafts fresh   RocketReach     Pre-filled rows land in the        │
  │  target companies  verifies email, sheet Siobahn already uses;        │
  │  weekly.           title, location. she picks who to pursue.          │
  └──────────────────────────────────────────────────────┬──────────────┘
                                                          ▼
  KNOWLEDGE GRAPH (Faragopedia)
  ┌───────────────────────────────────────────────────────────────────────┐
  │  04 Meeting booked  ──▶  05 Knowledge graph                            │
  │  Marking a win auto-     A linked wiki page is written &               │
  │  syncs the record into   cross-referenced automatically.               │
  │  the knowledge base.                                                   │
  └────────────────────────────────────────┬──────────────────────────────┘
                                            ▼
                    ↩ COMPOUNDS BACK into next week's targeting
```

**The step a CRM can't do:** accumulated intelligence about who we know, why they mattered, and what worked feeds straight back into next week's targeting. The system gets sharper every cycle — on its own.

---

## Three things a subscription CRM structurally will not do

**1. It finds who to approach — not just their email.**
Modern CRMs can enrich a contact from a name and company — but only as a paid add-on, and only once you've decided who that contact is. Ours does the deciding: it proposes fit-calibrated targets each week, verifies them, and writes them in.
→ *Per contact: ~30 min of hunting → 3–5 sec.*

**2. Knowledge compounds instead of sitting in fields.**
A CRM stores flat records. Faragopedia builds a self-maintaining knowledge graph — every meeting enriches an interlinked web of people, companies and context, with the AI keeping links and summaries current.
→ *Output = institutional memory, not a contact list.*

**3. It lives where the work already happens.**
No new tool to adopt, no migration, no seats to train. Prospects surface in the Google Sheet Siobahn already uses; intelligence surfaces in a wiki anyone on the team can read.
→ *Adoption cost: zero new software.*

---

## Same job, two very different machines

| | Off-the-shelf CRM | Farago BD system |
|---|---|---|
| **Finding leads** | You research and type them in | AI proposes calibrated targets weekly |
| **Contact data** | Add a paid enrichment add-on, then map fields | RocketReach-verified, written in automatically |
| **Keeping it current** | Manual data entry & hygiene | AI maintains pages, links & contradictions |
| **Knowledge model** | Flat records in fixed fields | Interlinked knowledge graph that compounds |
| **Where you work** | A separate app the team must adopt | The spreadsheet & wiki already in use |
| **Ownership** | Rented; intelligence leaves when you cancel | Portable markdown files we own outright |

---

## The cost a CRM hides — time

A CRM — even with a paid enrichment add-on — still runs on human time: someone decides who to chase, hunts down the email and title, keys it in, and later digs back through records to recover the context. Automating that research is where the hours come back.

**Research & enrichment, per contact:**

| | Time per contact |
|---|---|
| **By hand** — CRM + manual research | ~20–30 min |
| **Automated** — Farago lead engine | 3–5 sec |

**≈ 10–30× more throughput.** Freed from the research grind, one person works through 10–30× the prospects — a week of hunting collapses into an afternoon. And it **scales**: a single run handles 5 contacts or 500 at essentially the same time cost, so more volume no longer means another hire. Retrieval is the same story — context that takes minutes to dig out of a CRM's notes is **one search** here.

---

## The honest accounting

### What the off-the-shelf route actually costs
- **+** CRM **seats** — **$12–$175+** per user / month, billed annually
- **+** A **data-enrichment** add-on to auto-fill contacts — **~$49–$99/mo**, or **~$0.20+** per contact beyond plan credits
- **+** **Integration middleware** (Zapier / Make) to wire it together
- **+** **Onboarding & setup** — **$1,500–$3,500** one-time, plus certified consultants at **$100–$300/hr**
- **+** … and you'd **still do the prospecting by hand**

> *Typical 2026 market pricing.* The sticker price is only the first line: seats, enrichment, middleware and setup stack into the real total — and none of it decides who to approach for you.

### Where a CRM genuinely wins
- ✓ Mature **deal-pipeline** mechanics & forecasting
- ✓ Native **email & calendar** logging
- ✓ **Multi-user** permissions and large-team workflows
- ✓ Out-of-the-box **dashboards**, mobile apps, vendor support

> We deliberately don't compete on sales-funnel mechanics for a big team. This is built for a focused BD workflow — and if we ever need pipeline mechanics, **this loop can feed a CRM rather than be replaced by one.**

---

## Bottom line

A CRM would give us a differently-organised place to store contacts we'd still have to find ourselves. This gives us the contacts, the context, and a knowledge base that compounds — inside the tools the team already uses. **It isn't a cheaper CRM. It's a different, and for our purpose better, machine.**

---

*Farago Projects · BD intelligence system · Live in production since July 2026 · 159 automated tests*
