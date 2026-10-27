"""Push one Farago job's callsheets to the wiki — the only supported push path.

    python push_job.py --job 510                        # dry run -> out/job-510/ (writes nothing)
    python push_job.py --job 510 --aliases aliases.json # human-approved spelling variants
    python push_job.py --job 510 --live                 # snapshot, then write

Every step that a live page needed by hand or by a one-off script before 2026-10-26 is
here, and every safeguard from that incident is on the path:

1. collect(): escape-aware, width-checked table parsing (mdtable) and per-callsheet
   reconciliation (wiki_filter) — a malformed row or an unaccounted person stops the run.
2. render_job_page() + the NNNN-<words>.md filename (postprocess.page_path).
3. An existing page for the job is never overwritten (that loses hand fixes — the A5
   repair had to merge row by row); pass --replace only for a page you have checked.
4. People and companies resolve to existing pages by exact slug, or by --aliases
   ({"people": {"Lena Brüning": "lena-bruening"}, "companies": {"YY": "yohji-yamamoto-yy"}}).
   Never by a near miss.
5. Pages to create pass quarantine.py; a failure is listed in quarantine.md and never
   written, and the name stays plain text on the page.
6. Names and companies on the page are linked; the page is checked structurally
   (H1, People table, Source) — PUT accepts anything with a 200.
7. --live takes a full snapshot first (wiki.require_snapshot) and refuses without one,
   writes companies -> contacts -> callsheet, and reads every page back.

Afterwards (printed at the end): build_job_links.py, rebuild_interaction_history.py
--only <new + linked contacts>, wiki_maintenance enrich_companies.py --only <companies>,
then clear_notes.py.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE.parent / "wiki_maintenance"))  # after HERE: this folder's modules win

import enrich_companies as ec  # noqa: E402  (company-page schema helpers only)
import quarantine as q  # noqa: E402
from job_page import build_roster, render_job_page  # noqa: E402
from postprocess import page_path, people_links, wikilink_companies, wikilink_people  # noqa: E402
from push_to_faragopedia import collect  # noqa: E402
from wiki import all_pages, get_page, require_snapshot, slugify, write_page  # noqa: E402
from wiki_filter import RoleVocabulary  # noqa: E402

OUT = HERE / "out"
NOT_A_COMPANY = {"", "unknown", "—", "-", "n/a"}
CONTACT_FIELDS = ["name", "company", "job_title", "department", "seniority", "email", "phone", "linkedin",
                  "source", "relationship", "farago_contact", "industries", "role_tags",
                  "internal_or_freelance", "first_contacted", "last_contacted", "last_meeting",
                  "next_follow_up", "status", "notes"]


def job_title(role_raw: str, company: str) -> str:
    """'Y3 / SALES' at Y-3 -> 'Sales'. Drops the parts of a grouped role that only name the
    group or company, keeps the job; falls back to the whole label."""
    parts = [p.strip() for p in role_raw.split(" / ") if p.strip()]
    group = {q.norm(company), "client", "y3", "farago", "faragoprojects"}
    keep = [p for p in parts if q.norm(p) not in group] or parts or ["Crew"]
    return ec.tidy_role(keep[-1])


def render_contact(name: str, company_slug: str | None, company_name: str | None, title: str,
                   canonical: str, employment: str | None, phone: str, email: str, job: str) -> str:
    fm = {k: ("" if k not in ("industries", "role_tags") else []) for k in CONTACT_FIELDS}
    fm.update(name=name, company=f"[[companies/{company_slug}]]" if company_slug else "", job_title=title,
              department=canonical, internal_or_freelance=employment or "",
              phone="" if phone in ("", "unknown") else phone, email="" if email in ("", "unknown") else email,
              source=f"Farago callsheet job {job}")
    # Staff never carry a sales-pipeline relationship; nobody created here does (2026-10-26).
    assert fm["relationship"] == ""
    where = f" at {company_name}" if company_name else ""
    overview = f"{name} appeared as talent on Farago job {job}." if canonical == "talent" else \
        f"{name}: {title}{where} (Farago job {job})."
    lines = ["---"] + [f"{k}: {ec.yaml_scalar(fm[k])}" for k in CONTACT_FIELDS] + ["---", ""]
    return "\n".join(lines) + f"## Overview\n\n{overview}\n\n## Interaction History\n\n\n\n## Related Contacts\n\n"


def render_company(name: str) -> str:
    return ec.render_frontmatter({"name": name, "notes": ""}) + "\n" + \
        "\n\n".join(f"## {h}\n\n" for h in ec.SECTIONS)


def check_structure(page: str) -> list[str]:
    need = [("H1 title", lambda t: any(l.startswith("# ") for l in t.splitlines())),
            ("People table", lambda t: "| Role | Name |" in t),
            ("Source section", lambda t: "\n## Source" in t)]
    return [label for label, ok in need if not ok(page)]


def plan_job(job: str, aliases: dict, replace: bool) -> dict:
    by_job, report, _staff = collect(job)
    days = by_job.get(job)
    if not days:
        raise SystemExit(f"job {job}: no extracts on the current schema\n{report.render()}")
    pages = all_pages()
    contacts = {p[len("contacts/"):-3] for p in pages.get("contacts", [])}
    companies = {p[len("companies/"):-3] for p in pages.get("companies", [])}
    people_alias = aliases.get("people", {})
    company_alias = {k.lower(): v for k, v in aliases.get("companies", {}).items()}

    path = page_path(job, days)
    existing = [p for p in pages.get("callsheets", []) if Path(p).name.startswith(f"{job.zfill(4)}-")]
    if existing and not replace:
        raise SystemExit(f"job {job} already has {existing} — refusing to overwrite (hand fixes would be "
                         f"lost). Merge changes row by row, or pass --replace after checking the page.")

    roster = build_roster(days)
    vocab = RoleVocabulary.load()
    roles = q.role_words(vocab)
    person_keys = {q.norm(s) for s in contacts} | {q.norm(p.name) for p, _ in roster}
    job_companies = {(p.company or "").strip() for p, _ in roster} - NOT_A_COMPANY
    company_keys = {q.norm(s) for s in companies} | {q.norm(c) for c in job_companies}
    existing_contacts = {q.norm(s): s for s in contacts}

    def resolve_company(name: str) -> str | None:
        n = (name or "").strip()
        if n.lower() in NOT_A_COMPANY:
            return None
        if n.lower() in company_alias:
            return company_alias[n.lower()]
        s = slugify(n)
        return s if s in companies or s in new_companies else None

    new_companies: dict[str, str] = {}
    new_contacts: dict[str, str] = {}
    held: list[dict] = []
    for p, _dates in roster:
        comp = (p.company or "").strip()
        if comp.lower() not in NOT_A_COMPANY and not resolve_company(comp):
            why = q.company_problems(comp, person_keys=person_keys, row_person=p.name, roles=roles)
            if why:
                held.append({"kind": "company", "name": comp, "row": f"{p.role_raw} | {p.name}", "why": why})
            else:
                new_companies[slugify(comp)] = comp
    for p, _dates in roster:
        if p.name in people_alias or slugify(p.name) in contacts:
            continue
        why = q.contact_problems(p.name, company_keys=company_keys, roles=roles,
                                 existing_contacts=existing_contacts, company=p.company or "")
        slug = slugify(p.name)
        if why:
            held.append({"kind": "contact", "name": p.name, "row": f"{p.role_raw} | {p.company}", "why": why})
            continue
        if slug in new_contacts:
            continue  # same person on two roster rows (two roles)
        cslug = resolve_company(p.company)
        cname = new_companies.get(cslug) or (p.company if cslug else None)
        new_contacts[slug] = render_contact(p.name, cslug, cname, job_title(p.role_raw, p.company or ""),
                                            p.canonical, p.employment, p.phone, p.email, job)

    page = render_job_page(job, days, days[0].sheet.frontmatter.get("job_folder"))
    linkable = contacts | set(new_contacts)
    page = wikilink_people(page, lambda n: f"contacts/{slugify(n)}.md" if slugify(n) in linkable else None,
                           people_alias)
    page = wikilink_companies(page, resolve_company)
    missing = check_structure(page)
    if missing:
        raise SystemExit(f"job {job}: rendered page is missing {missing} — not writing")

    return {"job": job, "callsheet": path, "replacing": existing, "page": page,
            "new_companies": {f"companies/{s}.md": render_company(n) for s, n in new_companies.items()},
            "new_contacts": {f"contacts/{s}.md": c for s, c in new_contacts.items()},
            "quarantine": held, "report": report.render(),
            "reconciled": report.reconciled}


def write_dry_run(plan: dict) -> Path:
    d = OUT / f"job-{plan['job']}"
    for sub in ("companies", "contacts", "callsheets"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    (d / plan["callsheet"]).write_text(plan["page"], encoding="utf-8")
    for p, c in {**plan["new_companies"], **plan["new_contacts"]}.items():
        (d / p).write_text(c, encoding="utf-8")
    lines = [f"# Quarantine — job {plan['job']}", "",
             "Not written. Each name stays plain text on the page until a person decides.", ""]
    grouped: dict[tuple[str, str], dict] = {}
    for h in plan["quarantine"]:
        g = grouped.setdefault((h["kind"], h["name"]), {"why": h["why"], "rows": []})
        g["rows"].append(h["row"])
    lines += [f"- **{kind}** `{name}` — {'; '.join(g['why'])}  \n  rows: {' · '.join(dict.fromkeys(g['rows']))}"
              for (kind, name), g in grouped.items()] or ["(nothing quarantined)"]
    (d / "quarantine.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    recon = "\n".join(f"{f}: {n} rows -> {t}" for f, n, t in plan["reconciled"])
    (d / "report.txt").write_text(plan["report"] + "\n\nRECONCILED\n" + recon + "\n", encoding="utf-8")
    return d


def write_live(plan: dict) -> None:
    print("snapshot:", require_snapshot(f"pre-push-job-{plan['job']}"))
    order = list(plan["new_companies"].items()) + list(plan["new_contacts"].items()) + \
        [(plan["callsheet"], plan["page"])]
    for path, content in order:
        write_page(path, content)
    bad = [p for p, c in order if get_page(p) != c]
    if bad:
        raise SystemExit(f"READ-BACK MISMATCH on {bad}")
    print(f"written and verified: {len(order)} pages")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--aliases", type=Path, help="JSON {people: {name: slug}, companies: {name: slug}}")
    ap.add_argument("--replace", action="store_true", help="allow replacing this job's existing page")
    ap.add_argument("--live", action="store_true")
    a = ap.parse_args()
    aliases = json.loads(a.aliases.read_text(encoding="utf-8")) if a.aliases else {}
    plan = plan_job(a.job, aliases, a.replace)
    d = write_dry_run(plan)
    print(f"job {a.job} -> {plan['callsheet']}{' (REPLACING ' + str(plan['replacing']) + ')' if plan['replacing'] else ''}")
    print(f"  new companies: {len(plan['new_companies'])}   new contacts: {len(plan['new_contacts'])}   "
          f"quarantined: {len(plan['quarantine'])}   callsheets reconciled: {len(plan['reconciled'])}")
    print(f"  review: {d}")
    if not a.live:
        print("DRY RUN — nothing written.")
        return 0
    write_live(plan)
    people = " ".join(sorted({s for s, _role in people_links(plan["page"])}))
    firms = " ".join(sorted(set(re.findall(r"\[\[companies/([^\]|]+)\]\]", plan["page"]))))
    print("\nNext, in order:\n"
          "  python build_job_links.py\n"
          f"  python rebuild_interaction_history.py --live --only {people}\n"
          f"  (wiki_maintenance) python enrich_companies.py --live --only {firms}\n"
          "  (wiki_maintenance) python clear_notes.py --live")
    return 0


if __name__ == "__main__":
    sys.exit(main())
