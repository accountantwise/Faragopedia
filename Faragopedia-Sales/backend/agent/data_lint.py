"""Deterministic data-quality rules run at the start of every lint (no LLM involved).

Each rule is a shape the 2026-10-26 callsheet-import incident produced (an escaped `\\|`
in a role shifted table columns: people filed as companies, companies and role labels
filed as contacts). They run on whatever folders exist and do nothing for wikis without
contacts/companies/callsheets folders.

Findings are tagged "Data rule:" and are never sent to the LLM fixer (see
WikiManager.fix_lint_findings): the fix for a junk page is upstream — re-parse, merge or
archive by hand — and an LLM rewrite would only hide it.
"""
from __future__ import annotations

import os
import re
import unicodedata

import yaml

PREFIX = "Data rule:"
CELL_BOUNDARY = re.compile(r"(?<!\\)\|")
LINK = re.compile(r"\[\[(contacts|companies)/([^\]|#]+)")
# role and section labels that turned up as contact names in the incident
ROLE_WORDS = {"sales", "producer", "comms", "photographer", "production", "client", "pr", "spoma",
              "culturemarketing", "socialsanddigital", "management", "label", "band", "talent", "crew",
              "artdirector", "stylist", "director", "casting", "agent"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s.replace("&", "and"))


def _frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def _read_folder(wiki_dir: str, folder: str) -> dict[str, str]:
    d = os.path.join(wiki_dir, folder)
    if not os.path.isdir(d):
        return {}
    out = {}
    for f in sorted(os.listdir(d)):
        if f.endswith(".md") and not f.startswith("_"):
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                out[f[:-3]] = fh.read()
    return out


def run_rules(wiki_dir: str) -> list[dict]:
    """Returns finding dicts (severity, page, description, fix_confidence, fix_description)."""
    contacts = _read_folder(wiki_dir, "contacts")
    companies = _read_folder(wiki_dir, "companies")
    callsheets = _read_folder(wiki_dir, "callsheets")
    findings: list[dict] = []

    def add(severity, page, what, fix):
        findings.append({"severity": severity, "page": page, "description": f"{PREFIX} {what}",
                         "fix_confidence": "needs_source", "fix_description": f"By hand: {fix}"})

    company_fm = {s: _frontmatter(t) for s, t in companies.items()}
    company_keys = {_norm(s) for s in companies} | {_norm(f.get("name", "")) for f in company_fm.values()}
    company_keys.discard("")

    # who is a client on any callsheet (frontmatter `client:` as a link or plain name)
    clients = set()
    for t in callsheets.values():
        c = str(_frontmatter(t).get("client", "") or "")
        m = re.search(r"\[\[companies/([^\]|#]+)", c)
        clients.add(m.group(1) if m else re.sub(r"[^a-z0-9]+", "-", c.lower()).strip("-"))

    for slug, text in contacts.items():
        fm = _frontmatter(text)
        name = str(fm.get("name", "") or "").strip()
        page = f"contacts/{slug}.md"
        letters = re.sub(r"[^A-Za-z]", "", name)
        multiword = " " in name
        if "\\" in name or "|" in name or "\\" in str(fm.get("job_title", "") or ""):
            add("error", page, f"contact '{name}' has a \\ or | in its name/title — a split table cell.",
                "re-import the callsheet with the fixed parser, then archive this page.")
        if _norm(name) in ROLE_WORDS:
            add("error", page, f"contact '{name}' is a role or section label, not a person.",
                "archive it and re-import the callsheet it came from.")
        if (multiword or letters.isupper()) and _norm(name) in company_keys:
            add("warning", page, f"contact '{name}' has the same name as a company page.",
                "if it is the company, archive the contact and repoint links to the company page.")
        if len(letters) > 3 and letters.isupper() and multiword:
            add("warning", page, f"contact '{name}' is all-caps and multi-word — usually a company or heading.",
                "check the source callsheet; archive if it is not a person.")
        rel = str(fm.get("relationship", "") or "").strip()
        staff = "farago-projects" in str(fm.get("company", "") or "") or \
            str(fm.get("internal_or_freelance", "") or "").lower().startswith("staff")
        if rel and staff:
            add("error", page, f"Farago staff/freelancer '{name}' has pipeline relationship '{rel}'.",
                "clear the relationship field (it is a sales stage; staff have none).")

    for slug in companies:
        # multi-word only: a one-word talent name ('Chloe') can share a brand's slug (Chloé)
        if slug in contacts and slug not in clients and "-" in slug:
            add("warning", f"companies/{slug}.md",
                f"company page '{slug}' has the same slug as a contact and is never a client — "
                "likely a person filed as a company.",
                "if it is a person, archive the company page and fix the callsheet row that created it.")

    for slug, text in callsheets.items():
        page = f"callsheets/{slug}.md"
        people = text.split("## People", 1)[1].split("\n## ", 1)[0] if "## People" in text else ""
        width = None
        for line in people.splitlines():
            if line.startswith("| Role | Name |"):
                width = len(CELL_BOUNDARY.split(line))
                continue
            if width is None or not line.startswith("|") or line.startswith("|---"):
                continue
            if len(CELL_BOUNDARY.split(line)) != width:
                add("error", page, f"People row has the wrong number of cells: {line[:90]}",
                    "re-render the row; a stray | shifts every later column.")
            elif re.match(r"^\|[^|]*\\\s*\|", line):
                add("error", page, f"People row role ends in a backslash (shifted columns): {line[:90]}",
                    "re-import with the fixed parser; name and company in this row are swapped.")

    pools = {"contacts": contacts, "companies": companies}
    for folder, pages in [("callsheets", callsheets), ("contacts", contacts), ("companies", companies)]:
        for slug, text in pages.items():
            missing = sorted({f"{k}/{s}" for k, s in LINK.findall(text) if s not in pools[k]})
            if missing:
                add("warning", f"{folder}/{slug}.md", f"links to missing page(s): {', '.join(missing[:5])}"
                    + (f" (+{len(missing) - 5} more)" if len(missing) > 5 else ""),
                    "create the page, or repoint the link (archived pages are not restored by links).")
    return findings
