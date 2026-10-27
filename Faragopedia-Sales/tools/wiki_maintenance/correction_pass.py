"""Correction pass over companies and contacts, driven by a plan file. Dry-run by default.

    python correction_pass.py --plan plans/<date>.json [--company-research r.json] [--research c.json] [--live]

The plan (see example_plan.json) lists human-verified merges, client-field fixes, and
companies/contacts to create. It carries contact details, so it lives in plans/ (ignored).

0. Create missing company pages (plan "new_companies"), and contact pages for CRM
   Contacts-tab people whose company now has a page (first-name-only rows are skipped).
1. Merge verified duplicate company pages into a survivor. The loser's name becomes an
   `aliases:` entry on the survivor so future callsheets/CRM rows naming it still resolve.
2. Repoint every [[companies/<loser>]] link in every folder, and callsheet `client:` fields
   that name a loser, to the survivor. Archive the loser (soft delete) and record the pair
   in merge_history.json, so links to it are repointed on every future run.
3. Repair contacts' `company:` field to a real [[companies/...]] link (name/alias match,
   never a guess; unresolved values are reported and left alone).
4. Expand company key_contacts from the CRM Contacts tab, and flag contact-name spellings
   that disagree with the CRM email address (HUMAN: note).
5. Create contact pages for agency people named only in callsheet Contact cells / the
   Outreach Log, and link their names where they appear.

Run `enrich_companies.py --all --live` afterwards to re-render company pages.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import enrich_companies as ec  # noqa: E402  (loads .env)
import wikiapi as ia  # noqa: E402

MERGE_HISTORY = HERE / "merge_history.json"  # loser slug -> survivor slug, every company merge ever done
CARRY_SECTIONS = ["Recent News & Social Activity", "Competitor Production Companies",
                  "Industry Connections", "Contacts", "Meeting History"]

EMPTY_BODY = "\n\n".join(f"## {h}\n\n" for h in ec.SECTIONS)


def read_sheet(tab: str) -> list[list[str]]:
    env = os.environ
    tok = ec.http_json("https://oauth2.googleapis.com/token", {"Content-Type": "application/x-www-form-urlencoded"},
                       urllib.parse.urlencode({"client_id": env["GOOGLE_CLIENT_ID"], "client_secret": env["GOOGLE_CLIENT_SECRET"],
                                               "refresh_token": env["GOOGLE_REFRESH_TOKEN"], "grant_type": "refresh_token"}).encode())
    rng = urllib.parse.quote(f"'{tab}'!A:Z")
    return ec.http_json(f"https://sheets.googleapis.com/v4/spreadsheets/{env['GOOGLE_SHEETS_SPREADSHEET_ID']}/values/{rng}",
                        {"Authorization": f"Bearer {tok['access_token']}"}).get("values", [])


def set_line(content: str, key: str, value: str) -> str:
    """Replace one frontmatter line (and any orphaned indented continuation lines under it)."""
    return re.sub(rf"^{key}:.*(?:\n[ \t]+\S.*)*$", lambda m: f"{key}: {value}", content, count=1, flags=re.M)


class Pass:
    def __init__(self, live: bool, plan: dict):
        self.live = live
        self.plan = plan
        self.wiki = ec.Wiki()
        # every earlier merge too: old links may still point at a page merged away months ago
        self.redirect = {**json.loads(MERGE_HISTORY.read_text(encoding="utf-8")),
                         **{l: s for s, ls in plan.get("merges", {}).items() for l in ls}}
        self.pending: dict[str, str] = {}   # path -> new content
        self.new_paths: set[str] = set()
        self.report: dict[str, list] = {k: [] for k in
                                         ["merged", "repointed", "client_fixed", "contact_company_fixed",
                                          "contact_company_unresolved", "key_contacts_added", "spelling_flags",
                                          "created", "crm_unmatched"]}

    def content(self, path: str) -> str:
        return self.pending.get(path) or self.wiki.get(path)

    def exists(self, path: str) -> bool:
        folder = path.split("/")[0]
        return path in self.wiki.index.get(folder, [])

    def company(self, value) -> str | None:
        slug = self.wiki.resolve_company(value)
        return self.redirect.get(slug, slug) if slug else None

    def add_page(self, path: str, content: str):
        """Stage a brand-new page and make it visible to the resolvers for later steps."""
        folder = path.split("/")[0]
        self.pending[path] = content
        self.new_paths.add(path)
        self.wiki.index.setdefault(folder, []).append(path)
        self.wiki._page_cache[path] = ""
        if folder == "companies":
            self.wiki.companies.add(path)
            self.wiki._company_keys = None
        elif folder == "contacts":
            self.wiki.contacts.add(path)
            self.wiki._contact_keys[ec.norm(path.split("/")[-1][:-3])] = path[:-3]
        self.report["created"].append(path)

    # ---- 0
    def new_companies(self, research: dict):
        for c in self.plan.get("new_companies", []):
            name, industry, parent = c["name"], c.get("industry", ""), c.get("parent_group", "")
            slug = ia.slugify(name)
            path = f"companies/{slug}.md"
            if self.exists(path) or self.wiki.resolve_company(name):
                continue
            r = next((v for k, v in research.items() if ec.norm(k) == ec.norm(name)), {})
            fm = {"name": name, "parent_group": parent, "website": r.get("website") or "",
                  "industry": f"[[industries/{industry}]]" if industry else "", "hq_location": r.get("hq") or "",
                  "notes": r.get("notes") if str(r.get("notes") or "").startswith("HUMAN:") else ""}
            page = ec.render_frontmatter(fm) + "\n" + EMPTY_BODY
            self.add_page(path, page)
            self.wiki._page_cache[path] = page

    def crm_contacts(self):
        """CRM Contacts-tab people whose company has a page but who don't have one yet."""
        for r in read_sheet("Contacts")[1:]:
            r = (r + [""] * 14)[:14]
            company, name = r[0].strip(), f"{r[1].strip()} {r[2].strip()}".strip()
            slug = self.company(company) if company else None
            if not slug or len(name.split()) < 2 or self.wiki.resolve_contact(name):
                continue  # first-name-only rows can't be told apart (M.A.P. 'Kirsty' is kirsty-wilson)
            title = ec.tidy_role(r[3].strip())
            cname = ec.split_page(self.content(f"companies/{slug}.md"))[0].get("name", company)
            overview = f"{name} is {ec.article(title)} {title} at {cname}." if title else f"{name} works at {cname}."
            fm = {"name": name, "company": f"[[companies/{slug}]]", "job_title": title, "department": "",
                  "seniority": r[6].strip(), "email": r[7].strip(), "phone": r[13].strip(), "linkedin": "",
                  "source": "CRM Contacts tab", "relationship": "", "farago_contact": "", "industries": [],
                  "role_tags": [r[4].strip()] if r[4].strip() else [], "internal_or_freelance": r[5].strip(),
                  "first_contacted": "", "last_contacted": "", "last_meeting": "", "next_follow_up": "",
                  "status": "", "notes": ""}
            lines = ["---"] + [f"{k}: {ec.yaml_scalar(v)}" for k, v in fm.items()] + ["---", ""]
            path = f"contacts/{ia.slugify(name)}.md"
            self.add_page(path, "\n".join(lines) + f"## Overview\n\n{overview}\n\n## Interaction History\n\n\n\n## Related Contacts\n\n")

    # ---- 1 + 2
    def merges(self):
        for survivor, losers in self.plan.get("merges", {}).items():
            sp = f"companies/{survivor}.md"
            s_fm, s_body = ec.split_page(self.content(sp))
            s_sec = ec.parse_sections(s_body)
            for loser in losers:
                lp = f"companies/{loser}.md"
                if not self.exists(lp):
                    continue
                l_fm, l_body = ec.split_page(self.wiki.get(lp))
                l_sec = ec.parse_sections(l_body)
                for k, v in l_fm.items():
                    if k in ("name", "notes", "aliases"):
                        continue
                    if isinstance(v, list):
                        merged = list(dict.fromkeys((s_fm.get(k) or []) + v))
                        if merged:
                            s_fm[k] = merged
                    elif v not in ("", None) and s_fm.get(k) in ("", None):
                        s_fm[k] = v
                aliases = list(s_fm.get("aliases") or [])
                for a in [l_fm.get("name")] + list(l_fm.get("aliases") or []):
                    if a and ec.norm(a) != ec.norm(s_fm.get("name", "")) and a not in aliases:
                        aliases.append(a)
                s_fm["aliases"] = aliases
                s_over = ec.text_of(s_sec.get("Company Overview", []))
                l_over = ec.text_of(l_sec.get("Company Overview", []))
                if "_Sources:" in s_over and l_over and "_Sources:" not in l_over:
                    s_sec["Company Overview"] = l_sec["Company Overview"]
                for h in CARRY_SECTIONS:
                    have = {ln.strip() for ln in s_sec.get(h, [])}
                    extra = [ln for ln in ec.manual_lines(l_sec.get(h, [])) if ln.strip() not in have]
                    if extra:
                        s_sec[h] = [ln for ln in s_sec.get(h, []) if not ec.PLACEHOLDER.match(ln.strip())] + extra
                self.report["merged"].append(f"{loser} -> {survivor}")
            body = "\n\n".join(f"## {h}\n\n{ec.text_of(lines)}" for h, lines in s_sec.items())
            self.pending[sp] = ec.render_frontmatter(s_fm) + "\n" + body + "\n"

        for folder, paths in self.wiki.index.items():
            for path in paths:
                if path.startswith("companies/") and path.split("/")[-1][:-3] in self.redirect:
                    continue
                text = self.content(path)
                new = text
                for loser, survivor in self.redirect.items():
                    new = re.sub(rf"\[\[companies/{re.escape(loser)}(?=[\]|])", f"[[companies/{survivor}", new)
                if new != text:
                    self.report["repointed"].append(path)
                if folder == "callsheets":
                    m = re.search(r"^client:\s*(.*)$", new, re.M)
                    raw = m.group(1).strip().strip("'\"") if m else ""
                    fixed = self.plan.get("client_fixes", {}).get(path)
                    if not fixed and raw and not raw.startswith("[["):
                        slug = self.wiki.resolve_company(raw)
                        fixed = self.redirect.get(slug) if slug in self.redirect else None
                    if fixed and raw != f"[[companies/{fixed}]]":
                        new = set_line(new, "client", json.dumps(f"[[companies/{fixed}]]"))
                        self.report["client_fixed"].append(f"{path}: {raw!r} -> {fixed}")
                if new != text:
                    self.pending[path] = new

    # ---- 3
    def contact_companies(self):
        for path in self.wiki.index.get("contacts", []):
            text = self.content(path)
            m = re.search(r"^company:\s*(.*)$", text, re.M)
            if not m:
                continue
            raw = m.group(1).strip().strip("'\"")
            if not raw:
                continue
            targets = ec.wikilink_targets(raw)
            if targets and targets[0].startswith("companies/") and f"{targets[0]}.md" in self.wiki.companies \
                    and targets[0].split("/")[-1] not in self.redirect:
                continue
            slug = self.company(raw)
            if not slug:
                self.report["contact_company_unresolved"].append(f"{path}: {raw}")
                continue
            self.pending[path] = set_line(text, "company", json.dumps(f"[[companies/{slug}]]"))
            self.report["contact_company_fixed"].append(f"{path}: {raw} -> {slug}")

    # ---- 4
    def crm_key_contacts(self):
        rows = read_sheet("Contacts")
        add: dict[str, list[str]] = {}
        for r in rows[1:]:
            r = (r + [""] * 14)[:14]
            company, name, email = r[0].strip(), f"{r[1].strip()} {r[2].strip()}".strip(), r[7].strip()
            if not company or not name:
                continue
            slug, person = self.company(company), self.wiki.resolve_contact(name)
            if not slug or not person:
                self.report["crm_unmatched"].append(f"{company} / {name}" + ("" if slug else " (no company page)"))
                continue
            add.setdefault(slug, []).append(f"[[{person}]]")
            self.flag_spelling(person, name, email)
        for slug, links in add.items():
            path = f"companies/{slug}.md"
            fm, body = ec.split_page(self.content(path))
            current = [f"[[{p}]]" for p in (self.wiki.resolve_contact(t) for t in ec.wikilink_targets(fm.get("key_contacts"))) if p]
            merged = list(dict.fromkeys(current + links))
            new_links = [x for x in merged if x not in current]
            if new_links:
                fm["key_contacts"] = merged
                self.pending[path] = ec.render_frontmatter(fm) + "\n" + body.lstrip("\n")
                self.report["key_contacts_added"].append(f"{slug}: +{len(new_links)}")

    def flag_spelling(self, person: str, name: str, email: str):
        local = email.split("@")[0].lower() if "@" in email else ""
        last = ec.norm(" ".join(name.split()[1:]))
        email_last = re.sub(r"[^a-z]", "", local.split(".", 1)[1]) if "." in local else ""
        if not last or not email_last or last == email_last:
            return
        if (email_last in last or last in email_last) and abs(len(last) - len(email_last)) >= 3:
            return  # the address drops a whole name part (Abd-Rabbo -> rabbo), not a typo
        if difflib.SequenceMatcher(None, last, email_last).ratio() < 0.7:
            return  # a different format (initials etc.), not a likely typo
        path = f"{person}.md"
        text = self.content(path)
        fm, _ = ec.split_page(text)
        if str(fm.get("notes") or "").strip():
            return
        note = f"HUMAN: check surname spelling - page says '{name.split()[-1]}', CRM email is {email}."
        self.pending[path] = set_line(text, "notes", json.dumps(note))
        self.report["spelling_flags"].append(f"{person}: {name} vs {email}")

    # ---- 5
    def new_contacts(self, research: dict):
        for c in self.plan.get("new_contacts", []):
            r = research.get(ia.slugify(c["name"])) or {}
            ok = r.get("confidence") in ("high", "medium")
            short, full = c["name"], r.get("full_name") or ""
            if ok and full.startswith(short + " "):
                c = dict(c, name=full, human=f"HUMAN: surname '{full[len(short) + 1:]}' comes from web research "
                                              f"({', '.join(r.get('sources', [])[:2])}); the CRM and callsheet only say "
                                              f"'{short}' - confirm.")
            slug = ia.slugify(c["name"])
            path = f"contacts/{slug}.md"
            if self.exists(path):
                continue
            title = (r.get("job_title") if ok and r.get("job_title") else None) or c.get("title", "")
            history = []
            if c.get("callsheet"):
                cs_fm, _ = ec.split_page(self.wiki.get(c["callsheet"]))
                who, role = c["represents"]
                start, end = str(cs_fm.get("shoot_start") or ""), str(cs_fm.get("shoot_end") or "")
                when = start if not end or end == start else f"{start} to {end}"
                history.append(f"{when}: agent for [[{who}]] ({role}) on {cs_fm.get('name')} "
                               f"(job {cs_fm.get('job_reference_number')}, [[{c['callsheet'][:-3]}]]).")
            if c.get("outreach"):
                history.append(f"{c['outreach_note']} ([[{c['outreach']}]]).")
            company_name = ec.split_page(self.wiki.get(f"companies/{c['company']}.md"))[0].get("name", c["company"])
            bio = r.get("bio") if ok and r.get("bio") else None
            overview = bio or (f"{c['name']} is {ec.article(title)} {title.lower()} at {company_name}"
                               + (f", {c['city']}" if c.get("city") else "") + ".")
            if c.get("represents"):
                overview += f" Farago's contact for booking [[{c['represents'][0]}]]."
            human = c.get("human") or (f"HUMAN: {r['caveat']}" if r.get("caveat") else "")
            fm = {
                "name": c["name"], "company": f"[[companies/{c['company']}]]", "job_title": title,
                "department": c.get("department", ""), "seniority": "", "email": c.get("email", ""),
                "phone": c.get("phone", ""), "linkedin": (r.get("linkedin") if ok else "") or "",
                "source": "Farago callsheets / Outreach Log" + (" + web research" if ok else ""),
                "relationship": "", "farago_contact": "", "industries": [], "role_tags": [],
                "internal_or_freelance": "", "first_contacted": "", "last_contacted": "", "last_meeting": "",
                "next_follow_up": "", "status": "", "notes": human,
            }
            lines = ["---"] + [f"{k}: {ec.yaml_scalar(v)}" for k, v in fm.items()] + ["---", ""]
            page = "\n".join(lines) + (f"## Overview\n\n{overview}\n\n## Interaction History\n\n" + "\n\n".join(history)
                                       + "\n\n## Related Contacts\n\n" + (f"- [[{c['represents'][0]}]]\n" if c.get("represents") else ""))
            self.pending[path] = page
            self.report["created"].append(path)
            if c.get("callsheet"):
                cs = self.content(c["callsheet"])
                pat = rf"(contact via ){re.escape(short)}\b"
                if re.search(pat, cs):
                    self.pending[c["callsheet"]] = re.sub(pat, rf"\1[[contacts/{slug}]]", cs)
            cp = f"companies/{c['company']}.md"
            cfm, cbody = ec.split_page(self.content(cp))
            kc = list(cfm.get("key_contacts") or [])
            kc = [x for x in kc if ec.norm((ec.wikilink_targets(x) or [x])[0].split("/")[-1])
                  not in (ec.norm(short), ec.norm(c["name"]), ec.norm(slug))] + [f"[[contacts/{slug}]]"]
            cfm["key_contacts"] = list(dict.fromkeys(kc))
            self.pending[cp] = ec.render_frontmatter(cfm) + "\n" + cbody.lstrip("\n")

    def write(self):
        for path, content in self.pending.items():
            if path not in self.new_paths and content == self.wiki.get(path):
                continue
            if self.live:
                ia.write_page(path, content)
        losers = [f"companies/{l}.md" for l in self.redirect if self.exists(f"companies/{l}.md")]
        if self.live and losers:
            ia.archive_pages(losers)
        if self.live and self.plan.get("merges"):
            history = json.loads(MERGE_HISTORY.read_text(encoding="utf-8"))
            history.update({l: s for s, ls in self.plan["merges"].items() for l in ls})
            MERGE_HISTORY.write_text(json.dumps(history, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", type=Path, required=True,
                    help="JSON {merges, client_fixes, new_companies, new_contacts}; holds contact details, keep it out of git")
    ap.add_argument("--research", type=Path, help="JSON web research for new_contacts, keyed by slug")
    ap.add_argument("--company-research", type=Path, help="JSON {slug: {website, hq, notes}} for new_companies")
    ap.add_argument("--out", type=Path, default=HERE / "out" / "correction_pass")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()

    p = Pass(args.live, json.loads(args.plan.read_text(encoding="utf-8")))
    research = json.loads(args.research.read_text(encoding="utf-8")) if args.research else {}
    company_research = json.loads(args.company_research.read_text(encoding="utf-8")) if args.company_research else {}
    print("creating missing company pages..."); p.new_companies(company_research)
    print("merging duplicates / repointing links..."); p.merges()
    print("repairing contact company links..."); p.contact_companies()
    print("creating CRM contacts..."); p.crm_contacts()
    print("expanding key_contacts from CRM..."); p.crm_key_contacts()
    print("creating new contacts..."); p.new_contacts(research)

    args.out.mkdir(parents=True, exist_ok=True)
    changed = [pth for pth, c in p.pending.items() if pth in p.new_paths or c != p.wiki.get(pth)]
    for pth in changed:
        old = "" if pth in p.new_paths else p.wiki.get(pth)
        diff = "".join(difflib.unified_diff(old.splitlines(True), p.pending[pth].splitlines(True), pth, pth))
        (args.out / (re.sub(r"[^A-Za-z0-9._-]", "_", pth) + ".diff")).write_text(diff, encoding="utf-8")
    p.write()
    if args.live:  # standing rule: notes cleanup after any AI processing (HUMAN: notes survive)
        from clear_notes import clean
        live_paths = [x for x in changed if not any(x == f"companies/{l}.md" for l in p.redirect)]
        cleared = clean(live_paths, live=True)
        print(f"notes cleanup: {len(cleared.get('cleared', []))} cleared, {len(cleared.get('kept (human flag)', []))} human flags kept")
    (args.out / "report.json").write_text(json.dumps(p.report, indent=1, ensure_ascii=False), encoding="utf-8")
    for k, v in p.report.items():
        print(f"{k:28} {len(v)}")
    print(f"pages changed: {len(changed)} | {'LIVE - written' if args.live else 'DRY RUN - nothing written'} | {args.out}")


if __name__ == "__main__":
    main()
