"""Decide which people and fields from a raw callsheet extract reach the wiki.

This is the filtering half of stage 4 (ingestion). `callsheets-md/` is the archival
extract and keeps everyone on the sheet; the wiki page keeps a subset. Per the decisions
doc, filtering happens HERE and never at extraction — a field dropped during extraction
is gone for good, and re-extraction costs a Claude session per PDF.

Three things happen, in order:

1. Canonical roles are re-validated against roles.yml, asymmetrically (see
   `resolve_canonical`). Extraction predates parts of the vocabulary, so recorded
   canonicals drift.
2. Staff-vs-freelance is resolved as at the shoot date via staff_list, which is read
   from outside the repo and never written into the extract.
3. Agents are merged onto the person they represent, or dropped with them.

Nothing here writes to `callsheets-md/`. Input is read-only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from mdtable import MalformedRow, check_width, is_separator, split_cells  # noqa: F401  (MalformedRow re-exported)

HERE = Path(__file__).parent
ROLES_YML = HERE / "roles.yml"

# "AGENT (for Tim Walker, Photographer)" -> "Tim Walker". EXTRACTION.md requires the
# principal be named; an agent without one cannot be placed and is reported, not silently
# dropped, because across the corpus 45% of agent rows carry a phone against 3% of
# principal rows — losing the link loses the only usable contact for that person.
PRINCIPAL_RE = re.compile(r"\bfor\s+([^,)]+)", re.IGNORECASE)


@dataclass
class Person:
    canonical: str
    role_raw: str
    name: str
    company: str
    on_set: str
    phone: str
    email: str
    # Filled in during filtering.
    employment: str | None = None
    caveat: str | None = None
    contact_via: list[str] = field(default_factory=list)


@dataclass
class Callsheet:
    path: Path
    frontmatter: dict
    people: list[Person]
    services: list[tuple[str, str, str]]
    schedule: list[tuple[str, str]]
    locations: list[str]
    notes: str

    @property
    def shoot_date(self) -> str:
        return str(self.frontmatter.get("shoot_date", "") or "")

    @property
    def job(self) -> str:
        return str(self.frontmatter.get("job_reference_number", "unknown"))


# Rows where the sheet names a role but nobody was cast or booked yet. "SEAMSTRESS | TBC"
# on the job 526 shoot sheet is a vacancy, not a person, and a wiki page listing "TBC"
# under People is worse than one that omits the line.
PLACEHOLDER_NAMES = {"tbc", "tba", "unknown", "n/a", "na", "-", "?", ""}


@dataclass
class FilterReport:
    """Everything a human needs to see. Silence is the failure mode being guarded
    against, so each of these is printed rather than accumulated and forgotten."""
    schema_skipped: list[tuple[str, str]] = field(default_factory=list)
    role_overrides: list[tuple[str, str, str, str]] = field(default_factory=list)
    role_trusted: list[tuple[str, str, str, str]] = field(default_factory=list)
    other_roles: list[tuple[str, str]] = field(default_factory=list)
    orphan_agents: list[tuple[str, str, str]] = field(default_factory=list)
    unfilled_roles: list[tuple[str, str]] = field(default_factory=list)
    moved_to_services: list[tuple[str, str]] = field(default_factory=list)
    dropped: list[tuple[str, str, str]] = field(default_factory=list)
    # (callsheet file, rows read, {outcome: count}) — one per sheet, written by filter_people
    reconciled: list[tuple[str, int, dict]] = field(default_factory=list)

    def render(self) -> str:
        out = []

        def block(title, rows, fmt):
            # Deduped: a job spanning several callsheets reports the same person once per
            # sheet, and a report that repeats itself stops being read.
            seen = list(dict.fromkeys(rows))
            if seen:
                out.append(f"\n{title} ({len(seen)})")
                for r in seen:
                    out.append("  " + fmt(r))

        block("SKIPPED — pre-rework schema, cannot be filtered", self.schema_skipped,
              lambda r: f"{r[0]}: {r[1]}")
        block("ROLE OVERRIDDEN — extract said drop, roles.yml says keep", self.role_overrides,
              lambda r: f"{r[0]:28} {r[1]:34} {r[2]} -> {r[3]}")
        block("ROLE LABEL KEPT FROM EXTRACT — differs from roles.yml, person kept either way",
              self.role_trusted,
              lambda r: f"{r[0]:28} {r[1]:34} {r[2]} (roles.yml: {r[3]})")
        block("ROLE 'other' — EXCLUDED from the wiki. Extend roles.yml to include anyone "
              "here who should appear", self.other_roles,
              lambda r: f"{r[0]:28} {r[1]}")
        block("AGENT WITH NO NAMED PRINCIPAL — dropped, contact route lost", self.orphan_agents,
              lambda r: f"{r[0]:28} {r[1]:24} {r[2]}")
        block("ROLE ON THE SHEET BUT UNFILLED — omitted", self.unfilled_roles,
              lambda r: f"{r[0]:34} named as '{r[1]}'")
        block("MOVED TO PRODUCTION SERVICES — supplier, not a crew member",
              self.moved_to_services, lambda r: f"{r[0]:34} {r[1]}")

        # A count, not a list: excluded people are the majority of a callsheet and
        # printing them all would bury the reports above. But the total has to be
        # visible — every one of these is somebody the extract holds and the wiki does
        # not, and the whole point of filtering at ingestion is that the decision stays
        # inspectable.
        if self.dropped:
            by_role: dict[str, int] = {}
            for _, _, canonical in self.dropped:
                by_role[canonical] = by_role.get(canonical, 0) + 1
            summary = ", ".join(f"{n}× {c}" for c, n in sorted(by_role.items(), key=lambda kv: -kv[1]))
            out.append(f"\nEXCLUDED BY THE KEEP-LIST ({len(self.dropped)}): {summary}")

        return "\n".join(out) if out else "\n(nothing to report)"


class RoleVocabulary:
    """roles.yml, resolved. Exact alias first, then pattern shapes, then `other` —
    the order roles.yml specifies. Fuzzy matching was considered and rejected: its
    failure modes invert the decision that matters, since "Photo Assistant" scores
    high against "Photographer" and is the opposite call."""

    def __init__(self, data: dict):
        self.roles = data["roles"]
        self.aliases = {
            a.strip().lower(): canon
            for canon, spec in self.roles.items()
            for a in (spec.get("aliases") or [])
        }
        self.patterns = [
            (re.compile(p["shape"]), p["canonical"]) for p in data.get("patterns", [])
        ]
        self.not_people = {n.strip().lower() for n in data.get("not_people", [])}

    @classmethod
    def load(cls, path: Path | None = None) -> "RoleVocabulary":
        with open(path or ROLES_YML, encoding="utf-8") as f:
            return cls(yaml.safe_load(f))

    def resolve(self, role_raw: str) -> str:
        raw = role_raw.strip()
        if raw.lower() in self.aliases:
            return self.aliases[raw.lower()]
        for rx, canon in self.patterns:
            if rx.search(raw):
                return canon
        return "other"

    def keep(self, canonical: str) -> object:
        """True / False / "represents", read straight from roles.yml.

        `other` used to be special-cased True here. It is now an ordinary entry in
        roles.yml (wiki_keep: false, reversed 2026-09-07), so every keep/drop decision
        lives in one file and none of them are hidden in code.

        A canonical absent from roles.yml entirely still defaults to True: that means the
        vocabulary and the extract have diverged, which is a bug to see rather than a
        person to hide.
        """
        return self.roles.get(canonical, {}).get("wiki_keep", True)

    def caveat(self, canonical: str) -> str | None:
        return self.roles.get(canonical, {}).get("display_caveat")


def resolve_canonical(vocab: RoleVocabulary, recorded: str, role_raw: str,
                      report: FilterReport, who: str) -> str:
    """Reconcile the extract's canonical against roles.yml. Deliberately asymmetric.

    roles.yml itself states that section headings are the primary disambiguator, and the
    heading is gone by the time we get here: on the job 526 sheet "PRODUCER" under CLIENT
    is a brand producer and under "PRODUCTION | FARAGO PROJECTS" is a Farago production
    lead, from the same string. So string resolution cannot be authoritative.

    But extraction drifts the other way: it blanket-mapped the technical bench to `crew`
    (wiki_keep: false) when roles.yml has a `crew_lead` tier for DOP, gaffer, 1st AD,
    lighting director, set designer, studio manager and DIT.

    Rule: only override in the direction that would otherwise LOSE somebody.
    """
    expected = vocab.resolve(role_raw)

    # A label roles.yml cannot classify is a vocabulary gap, and now that `other` is
    # excluded it is also a person leaving the page. Report it on the roles.yml verdict
    # rather than on the final canonical: the job 526 extract labelled its McQueen studio
    # staff `crew`, so reporting only final-canonical `other` missed four people who were
    # dropped for want of an alias.
    if expected == "other":
        report.other_roles.append((who, role_raw))

    if expected == recorded:
        return recorded

    recorded_keep = vocab.keep(recorded)
    expected_keep = vocab.keep(expected)

    # The ONLY direction we override: the extract would drop somebody roles.yml keeps.
    if recorded_keep is False and expected_keep is not False:
        report.role_overrides.append((who, role_raw, recorded, expected))
        return expected

    # Everything else keeps the extract's label, because the extract had the section
    # heading and string resolution does not. Overriding here actively corrupts meaning:
    # "PRODUCER" under CLIENT is a brand producer, and roles.yml's alias table resolves
    # it to production_lead, relabelling McQueen's producer as Farago's. Likewise
    # "CREATIVE DIRECTOR" under CLIENT is the client's creative director, not the shoot's.
    # Both keep the person either way, so there is nothing to gain and meaning to lose.
    #
    # Reported by the caller, and only for people who survive filtering: a crew-vs-
    # assistant relabel on somebody the wiki excludes either way is noise, and a report
    # nobody reads is the same as no report.
    if recorded_keep is not False:
        report.role_trusted.append((who, role_raw, recorded, expected))
    return recorded


# Table splitting lives in mdtable.py, shared by every script that reads a markdown table
# (2026-10-26: five private copies of a naive split("|") shifted escaped-pipe rows).
_split_row = split_cells
_is_separator = is_separator


def parse_callsheet(path: Path) -> Callsheet | None:
    """Read one extract. Returns None if it predates the schema rework, which is the
    loud-failure case: without a `Canonical role` column there is no wiki_keep decision
    to make, and a partially filtered page would silently omit most of the crew."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    fm = yaml.safe_load(text[4:end]) or {}
    body = text[end + 4:]

    people: list[Person] = []
    services: list[tuple[str, str, str]] = []
    schedule: list[tuple[str, str]] = []
    locations: list[str] = []
    notes_lines: list[str] = []

    section = None
    header_seen = False
    header_width = 0
    for lineno, line in enumerate(body.splitlines(), start=1):
        s = line.strip()
        if s.startswith("## "):
            section, header_seen = s[3:].strip().lower(), False
            continue
        if section == "contacts" and s.startswith("|"):
            cells = _split_row(s)
            if cells and cells[0].lower() == "canonical role":
                header_seen, header_width = True, len(cells)
                continue
            if _is_separator(cells) or not header_seen:
                continue
            if len(cells) != header_width:
                raise MalformedRow(
                    f"{path.name}: contacts row has {len(cells)} cells, header has "
                    f"{header_width} (body line {lineno}): {s[:160]}")
            people.append(Person(*[c.replace("**", "") for c in cells[:7]]))
        elif section in ("production services", "schedule") and s.startswith("|"):
            cells = _split_row(s)
            if cells and cells[0].lower() in ("service", "time"):
                header_seen, header_width = True, len(cells)
                continue
            if _is_separator(cells) or not header_seen:
                continue
            check_width(cells, header_width, f"{path.name} {section} (body line {lineno})", s)
            if section == "production services" and len(cells) >= 3:
                services.append((cells[0], cells[1], cells[2]))
            elif section == "schedule" and len(cells) >= 2:
                schedule.append((cells[0], cells[1]))
        elif section == "locations" and s.startswith("-"):
            # Indentation carries meaning: the top-level bullet is the venue, nested
            # bullets are access/parking/transport notes about it. Flattening them makes
            # "Parking available onsite" read as a separate location.
            indent = len(line) - len(line.lstrip())
            locations.append(("  " if indent else "") + s.lstrip("- ").strip())
        elif section == "notes" and s:
            notes_lines.append(s)

    if not people:
        return None
    return Callsheet(path, fm, people, services, schedule, locations, "\n".join(notes_lines))


def is_supplier(p: Person, vocab: RoleVocabulary) -> bool:
    """Is this row a bought-in service rather than a member of the crew?

    Two signals, both taken from how callsheets are actually written:

    1. roles.yml's `not_people` list — Hospital, Medic, Catering, Lighting EQ, Art
       Handler. These were always meant to sit under Production services; the filter
       simply was not consulting the list.
    2. The role label IS the company name. Under the "SUPPLIERS, CATERING & HOSPITAL"
       heading Farago label the row with the supplier's trading name rather than a job
       title — "AQUATIC IMPACT | David Turner" for the water-tank specialists. A crew
       member's role never equals their employer's name, so the collision is a reliable
       tell and it generalises to vendors we have not seen instead of needing each one
       added to a list by hand.
    """
    role = p.role_raw.strip().lower()
    if role in vocab.not_people:
        return True
    company = (p.company or "").strip().lower()
    return bool(company) and company not in ("unknown", "—") and company == role


class ReconciliationError(RuntimeError):
    """Rows read from a callsheet != people kept + people dropped for a named reason."""


def filter_people(sheet: Callsheet, vocab: RoleVocabulary, staff, report: FilterReport) -> list[Person]:
    """Apply the keep-list, resolve employment as at the shoot date, merge agents.

    Reconciled (safeguard B2): every row read leaves by exactly one named door, and the
    counts must add up to the rows read, or the run stops. The 2026-10-26 incident lost
    ~80 people between the extract and the wiki with nothing recording where they went."""
    tally = {"kept": 0, "unfilled": 0, "supplier": 0, "excluded_by_keep_list": 0,
             "agent_merged": 0, "agent_no_principal": 0, "agent_principal_dropped": 0}
    kept = _filter_people(sheet, vocab, staff, report, tally)
    accounted = sum(tally.values())
    if accounted != len(sheet.people) or tally["kept"] != len(kept):
        raise ReconciliationError(
            f"{sheet.path.name}: {len(sheet.people)} rows read but {accounted} accounted for "
            f"({tally}); kept list has {len(kept)}")
    report.reconciled.append((sheet.path.name, len(sheet.people), dict(tally)))
    return kept


def _filter_people(sheet: Callsheet, vocab: RoleVocabulary, staff, report: FilterReport,
                   tally: dict[str, int]) -> list[Person]:
    resolved: list[Person] = []
    for p in sheet.people:
        canon = resolve_canonical(vocab, p.canonical, p.role_raw, report, p.name)
        resolved.append(Person(canon, p.role_raw, p.name, p.company, p.on_set, p.phone, p.email))

    # Principals first: an agent is kept only if the person they represent is kept, so
    # the keep set has to exist before agents can be placed.
    principals = [p for p in resolved if p.canonical != "agent"]
    agents = [p for p in resolved if p.canonical == "agent"]

    kept: list[Person] = []
    for p in principals:
        if p.name.strip().lower() in PLACEHOLDER_NAMES:
            report.unfilled_roles.append((p.role_raw, p.name))
            tally["unfilled"] += 1
            continue
        if is_supplier(p, vocab):
            # Suppliers belong under Production services, alongside the medic and the
            # caterer, not in the people roster — they are a service the job bought, not
            # crew on it. Their contact detail is preserved, just in the other section.
            report.moved_to_services.append((p.role_raw, p.name))
            sheet.services.append((p.role_raw.title(), p.name, p.phone))
            tally["supplier"] += 1
            continue
        # Reported BEFORE the keep decision, not after. `other` is now excluded, and it
        # is the bucket for roles the vocabulary has never seen — so this report is the
        # only signal that somebody was omitted for want of an alias. Reporting it inside
        # the keep branch, as an earlier version did, silenced it exactly when it started
        # to matter.
        if p.canonical == "other":
            report.other_roles.append((p.name, p.role_raw))
        decision = vocab.keep(p.canonical)
        if decision is False:
            report.dropped.append((p.name, p.role_raw, p.canonical))
            tally["excluded_by_keep_list"] += 1
            continue
        if staff is not None and (p.company or "").lower().startswith("farago"):
            # Employment status only ever comes from the staff list. The
            # "PRODUCTION | FARAGO PROJECTS" heading gives the role grouping, not the
            # employment status: on this sheet only 1 of 7 under it is actually staff.
            p.employment = staff.classify(p.name, sheet.shoot_date)
        p.caveat = vocab.caveat(p.canonical)
        kept.append(p)
        tally["kept"] += 1

    by_name = {p.name.strip().lower(): p for p in kept}
    for a in agents:
        m = PRINCIPAL_RE.search(a.role_raw)
        if not m:
            report.orphan_agents.append((a.name, a.company, a.role_raw))
            tally["agent_no_principal"] += 1
            continue
        principal = by_name.get(m.group(1).strip().lower())
        if principal is None:
            # Their principal was dropped, so they go too — the intended behaviour of
            # wiki_keep: represents, not an oversight.
            report.dropped.append((a.name, a.role_raw, "agent"))
            tally["agent_principal_dropped"] += 1
            continue
        contact = ", ".join(x for x in (a.name, a.company, a.phone) if x and x != "unknown")
        principal.contact_via.append(contact)
        tally["agent_merged"] += 1

    return kept
