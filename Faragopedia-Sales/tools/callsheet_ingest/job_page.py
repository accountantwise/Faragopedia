"""Assemble filtered callsheets into one wiki page per job.

One page per job, keyed on the job reference number, with shoot types as sections within
it — decided 2026-08-31. A job keeps ONE page even when it spans several campaigns (job
534 holds two COS campaigns with different photographers), so days are grouped by
campaign inside the page: a job-wide roster otherwise shows two photographers on
disjoint days with nothing explaining why.

The people roster is deduplicated across days, and is deliberately NEVER joined on a
talent name. Farago put placeholder names on callsheets so campaigns cannot leak before
release, so a talent name is a low-confidence field and two days sharing one are not
evidence of the same person.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from wiki_filter import Callsheet, Person

# Order the roster reads in. Seniority first, per Simon's rule ("anything that's a
# director or important"), not alphabetical — a reader is looking for the photographer.
ROLE_ORDER = [
    "photographer", "director", "client_contact", "production_lead", "art_director",
    "stylist_lead", "hair_lead", "makeup_lead", "casting_director", "crew_lead",
    "talent", "other",
]

SHOOT_TYPE_ORDER = ["recce", "fitting", "pre-light", "company move", "shoot", "event", "unknown"]


@dataclass
class Day:
    sheet: Callsheet
    people: list[Person]

    @property
    def campaign(self) -> str:
        return str(self.sheet.frontmatter.get("campaign") or "unknown")

    @property
    def shoot_type(self) -> str:
        return str(self.sheet.frontmatter.get("shoot_type") or "unknown")


def _role_rank(canonical: str) -> int:
    """Position in ROLE_ORDER, lowest (most senior) wins for a compound canonical.

    EXTRACTION.md's compound-role rule records one person wearing two hats as
    "photographer + director" — a string ROLE_ORDER was never meant to contain
    verbatim. Ranking the whole compound string falls through to len(ROLE_ORDER),
    burying a photographer at the bottom of the roster purely because they also
    direct, which is the opposite of Simon's rule that a reader is looking for the
    photographer first.
    """
    parts = [p.strip() for p in canonical.split("+")]
    return min(
        (ROLE_ORDER.index(p) if p in ROLE_ORDER else len(ROLE_ORDER) for p in parts),
        default=len(ROLE_ORDER),
    )


def _type_rank(t: str) -> int:
    return SHOOT_TYPE_ORDER.index(t) if t in SHOOT_TYPE_ORDER else len(SHOOT_TYPE_ORDER)


def _fm(days: list[Day], key: str) -> list[str]:
    seen = OrderedDict()
    for d in days:
        v = d.sheet.frontmatter.get(key)
        if v and str(v) != "unknown":
            seen[str(v)] = None
    return list(seen)


def slug_for(job: str, days: list[Day]) -> str:
    campaigns = _fm(days, "campaign") or _fm(days, "production") or ["job"]
    base = campaigns[0].lower()
    keep = [c if (c.isalnum() or c == " ") else " " for c in base]
    words = "".join(keep).split()
    return f"job-{job}-" + "-".join(words) if words else f"job-{job}"


def build_roster(days: list[Day]) -> list[tuple[Person, list[str]]]:
    """One row per person across the whole job, with the days they appear on.

    Identity is (canonical role, name) — never name alone, since the same name in two
    roles is two rows, and never for talent, whose names are unreliable by design.
    """
    rows: OrderedDict[tuple[str, str], tuple[Person, list[str]]] = OrderedDict()
    for d in days:
        for p in d.people:
            if p.canonical == "talent":
                # Deliberately not merged: a placeholder name repeated across days is
                # not evidence of one person, so each appearance stands on its own.
                # role_raw is part of the key too — an artist credited for two separate
                # works on one event day (job 531: Shaan Bevan, "Cerebral Cortex" and
                # "Specular Orefield") is two appearances on the same date, and without
                # role_raw the second credit's gallery contact is silently dropped.
                key = (p.canonical, p.name, d.sheet.shoot_date, p.role_raw)
            else:
                key = (p.canonical, p.name.strip().lower())
            if key in rows:
                person, dates = rows[key]
                if d.sheet.shoot_date not in dates:
                    dates.append(d.sheet.shoot_date)
                for via in p.contact_via:
                    if via not in person.contact_via:
                        person.contact_via.append(via)
                # Keep the first non-unknown contact detail we see for them.
                for attr in ("phone", "email", "company"):
                    if getattr(person, attr) in ("", "unknown") and getattr(p, attr) not in ("", "unknown"):
                        setattr(person, attr, getattr(p, attr))
            else:
                rows[key] = (p, [d.sheet.shoot_date])
    return sorted(rows.values(), key=lambda r: (_role_rank(r[0].canonical), r[0].name))


def _resolver_url(job_key: str) -> str:
    """Link target for a job's source folder: the wiki's own resolver, not a storage URL.

    Mounted under /api because the wiki frontend proxies /api same-origin, so a person
    browsing the wiki follows these links without needing the API's own service-token
    auth. As of 2026-09-13 the whole FARAGOPEDIA_WIKI_URL host sits behind Cloudflare
    Access — a signed-in person still gets through, but "no extra access policy" no
    longer describes it precisely; re-check this comment if Access config changes again.

    FARAGOPEDIA_WIKI_URL is the wiki's browser-facing host, which is NOT
    FARAGOPEDIA_API_URL — that one is the machine-auth hostname and would 403 a person.
    faragopedia.accountantwise.uk (the domain this used to point at) has no DNS record
    as of 2026-09-13 — don't reuse it as an example or a fallback.
    """
    import os
    base = os.environ.get("FARAGOPEDIA_WIKI_URL", "").rstrip("/")
    if not base:
        raise RuntimeError(
            "FARAGOPEDIA_WIKI_URL is not set. It is the wiki's browser-facing host "
            "(e.g. https://faragopedia-vps.ai-wise.uk) and must not be the "
            "service-token API hostname, which would 403 a human."
        )
    return f"{base}/api/job/{job_key}"


def _services(days: list[Day]) -> list[tuple[str, str, str]]:
    """Every distinct service across the job, in first-seen order.

    Deduplicated on (service, provider): the medic, hospital, caterer and equipment
    supplier are almost always identical on every day of a job, so listing them per day
    just repeats itself. Keyed without the phone number so a day that omitted it does
    not produce a second row for the same provider.
    """
    seen: OrderedDict[tuple[str, str], tuple[str, str, str]] = OrderedDict()
    for d in days:
        for svc, who, tel in d.sheet.services:
            key = (svc.strip().lower(), who.strip().lower())
            if key not in seen or (tel and tel != "unknown" and seen[key][2] in ("", "unknown")):
                seen[key] = (_cell(svc), _cell(who), _cell(tel))
    return list(seen.values())


def _cell(value: str) -> str:
    """Escape a value for a markdown table cell. Farago's filenames genuinely contain
    pipes — "MCQ CALL SHEET | SHOOT 23 JAN.xlsx" — and an unescaped one silently splits
    the row into extra columns."""
    return str(value).replace("|", "\\|")


def _fmt_contact(p: Person) -> str:
    bits = [b for b in (p.phone, p.email) if b and b != "unknown"]
    if p.contact_via:
        bits.append("contact via " + "; ".join(p.contact_via))
    return _cell(" · ".join(bits)) if bits else "—"


def render_job_page(job: str, days: list[Day], dropbox_job_folder: str | None) -> str:
    days = sorted(days, key=lambda d: (d.campaign, d.sheet.shoot_date, _type_rank(d.shoot_type)))
    campaigns = _fm(days, "campaign")
    clients = _fm(days, "client")
    dates = sorted(d.sheet.shoot_date for d in days if d.sheet.shoot_date)
    first = days[0].sheet.frontmatter

    title = campaigns[0] if campaigns else f"Job {job}"
    lines = [
        "---",
        "type: callsheet",
        f"name: {title}",
        f"job_reference_number: {job}",
        f"client: {clients[0] if clients else 'unknown'}",
        f"category: {first.get('category', 'unknown')}",
        f"city: {first.get('city', 'unknown')}",
        f"campaigns: [{', '.join(_yaml_str(c) for c in campaigns)}]",
        f"shoot_start: {dates[0] if dates else 'unknown'}",
        f"shoot_end: {dates[-1] if dates else 'unknown'}",
        f"job_folder_key: {first.get('job_folder_key', 'unknown')}",
        "---",
        "",
        f"# {title}",
        "",
        "## Overview",
        "",
        f"Job **{job}** · {first.get('category', 'unknown')} · "
        f"{len(days)} callsheet{'s' if len(days) != 1 else ''}"
        + (f" ({dates[0]} – {dates[-1]})" if dates else ""),
        "",
        f"Client: {clients[0] if clients else 'unknown'}. "
        f"Production company: {first.get('production_company', 'unknown')}.",
        "",
    ]
    if len(campaigns) > 1:
        lines += [
            f"This job covers {len(campaigns)} campaigns — "
            + ", ".join(f"**{c}**" for c in campaigns)
            + ". Shoot days are grouped by campaign below; crew differs between them.",
            "",
        ]
    # city is the Farago office that ran the job, not where it shot. Say so on the page,
    # because the shoot locations listed under each day frequently contradict it.
    lines += [
        f"Run out of the {first.get('city', 'unknown')} office. Shoot locations are listed per day.",
        "",
    ]

    services = _services(days)
    if services:
        lines += ["**Services** — " + "; ".join(
            f"{svc} — {who}" + (f" ({tel})" if tel and tel != "unknown" else "")
            for svc, who, tel in services) + ".", ""]

    lines += ["## Shoot Days", ""]

    current_campaign = None
    for d in days:
        if len(campaigns) > 1 and d.campaign != current_campaign:
            current_campaign = d.campaign
            lines += [f"### {d.campaign}", ""]
        heading = "####" if len(campaigns) > 1 else "###"
        day_no = d.sheet.frontmatter.get("shoot_day")
        suffix = f" — day {day_no}" if day_no and str(day_no) != "unknown" else ""
        lines += [f"{heading} {d.sheet.shoot_date} · {d.shoot_type}{suffix}", ""]
        if d.sheet.locations:
            for loc in d.sheet.locations:
                # Nested notes arrive prefixed with two spaces by the parser; keep the
                # nesting so access notes stay attached to their venue.
                lines.append(f"  - {loc.strip()}" if loc.startswith("  ") else f"- {loc}")
            lines.append("")
        # Call times are deliberately NOT rendered. They are day-of-shoot operational
        # detail — who is on set at 06:15 — and worthless to somebody looking a job up
        # months later, while being the longest thing on the page. Still parsed and still
        # in callsheets-md/, so this is a presentation choice that can be reversed
        # without re-extracting anything.
        #
        # Services are rendered once at job level instead of under each day: they are
        # bought per job, not per day, and repeating an identical medic, hospital and
        # caterer under every shoot day is noise.

    lines += ["## People", ""]
    roster = build_roster(days)
    multi_day = len(days) > 1
    header = "| Role | Name | Company / agency | Contact |" + (" Days |" if multi_day else "")
    rule = "|------|------|------------------|---------|" + ("------|" if multi_day else "")
    lines += [header, rule]
    for p, dates_on in roster:
        name = p.name
        if p.caveat:
            name += " ⚠"
        role = p.role_raw or p.canonical
        company = p.company if p.company and p.company != "unknown" else "—"
        if p.employment:
            company += f" `{p.employment}`" if company != "—" else f"`{p.employment}`"
        row = f"| {_cell(role)} | {_cell(name)} | {_cell(company)} | {_fmt_contact(p)} |"
        if multi_day:
            row += f" {', '.join(d[5:] for d in dates_on)} |"
        lines.append(row)
    lines.append("")
    if any(p.caveat for p, _ in roster):
        lines += [
            "> ⚠ Name as printed on the callsheet. Talent names may be placeholders — "
            "Farago use them so a campaign cannot leak before release — so this is not a "
            "reliable identity and must never be used to link records.",
            "",
        ]

    lines += ["## Source", ""]
    job_key = first.get("job_folder_key")
    if job_key and job_key != "unknown":
        # A KEY, never a live URL — decisions doc §4. GET /api/job/{key} resolves it
        # through a closed lookup table, so when folders are reorganised in Dropbox, or
        # the archive moves to Drive, `build_job_links.py` refreshes the table and every
        # link across the wiki re-points at once. No page is rewritten.
        lines += [f"[Open job folder]({_resolver_url(job_key)})", ""]
    if dropbox_job_folder:
        # The path as harvested, for reference and for anybody reconciling by hand. It is
        # explicitly NOT the link: it is a snapshot that goes stale the moment somebody
        # moves the folder, which is the failure the resolver exists to absorb.
        lines += [f"Path at harvest: `{dropbox_job_folder}`", ""]
    lines += ["| Shoot date | Type | Source file |", "|------------|------|-------------|"]
    for d in days:
        lines.append(f"| {d.sheet.shoot_date} | {d.shoot_type} | "
                     f"`{_cell(d.sheet.frontmatter.get('source_filename', 'unknown'))}` |")
    lines.append("")
    return "\n".join(lines) + "\n"


def _yaml_str(s: str) -> str:
    return '"' + s.replace('"', '\\"') + '"' if any(c in s for c in ':#,[]{}"') else s
