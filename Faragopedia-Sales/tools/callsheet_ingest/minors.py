"""Children on callsheets are withheld from the wiki (ADR 0011).

Kids campaigns list child models, and some other shoots cast child actors. Their rows
carry a first name, a parent's name ("c/o <parent>, agent <name> @ Example Kids Agency") and a
mobile number that is usually the parent's. None of that belongs in a sales wiki, so before
a job page is rendered or any page is created, those rows are taken out and the job page
gets one anonymous line instead: how many children, and through which agencies.

Who counts as a child is decided from the callsheet, because callsheets never give ages:

- talent on a kids job (campaign, title or folder says Kids / Baby / Junior / Children);
- talent whose role says so (YOUNG SCOTT, CHILD, KID, BABY, BOY, GIRL, TEEN);
- talent booked through a kids agency (name contains Kids / Kidz / Children / Junior, or a
  known children's agency below);
- anyone whose role is a parent or guardian of someone on set (MOTHER, FATHER, GUARDIAN).

This over-withholds on purpose: an adult model dropped from a Zara Kids page costs nothing,
a child's page in the wiki is the failure this exists to prevent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Agencies that represent children but don't say so in their name. Add to this, never
# remove: a false positive only hides an adult's row on one job page.
KIDS_AGENCIES = ("bruce and brown", "bruce & brown", "maya inc", "bizzy", "arwen and co", "grace and galor",
                 "grace & galor", "mini title", "brood management", "scallywags", "urban angels",
                 "agence frimousse", "ray and robin", "rebel nineteen")

KIDS_WORDS = re.compile(r"\b(kids?|kidz|kidso|kidsa|children|childrens|child|junior|juniors|baby|babies)\b", re.I)
CHILD_ROLE = re.compile(r"\b(young|child|kid|kids|baby|boy|girl|teen|toddler|infant|junior)\b", re.I)
PARENT_ROLE = re.compile(r"\b(mother|father|mum|mom|dad|parent|guardian)\b", re.I)
PHONE = re.compile(r"^\+?[\d ()-]{7,}$")


def is_kids_job(days) -> bool:
    """True when any campaign, title or folder of the job names a children's line."""
    for d in days:
        fm = d.sheet.frontmatter
        text = " ".join(str(fm.get(k) or "") for k in ("campaign", "production", "job_folder_key",
                                                        "job_folder", "source_filename"))
        if KIDS_WORDS.search(text.replace("-", " ").replace("_", " ")):
            return True
    return False


def is_kids_agency(text: str) -> bool:
    t = (text or "").lower()
    return bool(KIDS_WORDS.search(t)) or any(a in t for a in KIDS_AGENCIES)


def why_withheld(p, kids_job: bool) -> str | None:
    """Why this callsheet row must not reach the wiki, or None to keep it."""
    role = p.role_raw or ""
    if PARENT_ROLE.search(role):
        return "parent"
    if p.canonical != "talent":
        return None
    if kids_job:
        return "child"
    if CHILD_ROLE.search(role):
        return "child"
    if is_kids_agency(" ".join([p.company or "", *p.contact_via])):
        return "child"
    return None


def agency_of(p) -> str | None:
    """The agency a withheld row was booked through, for the anonymous note.
    'c/o <parent>, agent <name> @ Example Kids Agency' -> 'Example Kids Agency';
    contact_via '<agent>, Example Kids Ltd, +44 7…' -> 'Example Kids Ltd'."""
    company = (p.company or "").strip()
    if "@" in company:
        return company.rsplit("@", 1)[1].strip() or None
    if company and company.lower() not in ("unknown", "—", "-") and not company.lower().startswith("c/o"):
        return company
    for via in p.contact_via:
        parts = [x.strip() for x in via.split(",") if x.strip() and not PHONE.match(x.strip()) and "@" not in x]
        if len(parts) >= 2:
            return parts[1]
    return None


@dataclass
class Withheld:
    children: set[str] = field(default_factory=set)
    parents: set[str] = field(default_factory=set)
    agencies: list[str] = field(default_factory=list)
    actors: bool = False  # a cast role ("YOUNG SCOTT") rather than a model booking

    def __bool__(self) -> bool:
        return bool(self.children or self.parents)

    def note(self) -> str:
        kind = "actors" if self.actors else "models"
        n = len(self.children)
        line = f"> **{n} child {kind if n != 1 else kind[:-1]}**"
        if self.parents:
            line += f" and {len(self.parents)} parent{'s' if len(self.parents) != 1 else ''}"
        line += " on this job"
        line += f" (via {', '.join(self.agencies)})." if self.agencies else "."
        return line + " Faragopedia does not record minors' names or contact details; see the job folder."


def _agency_key(a: str) -> str:
    return re.sub(r"\b(ltd|limited|agency|management)\b|[^a-z0-9]", "", a.lower().replace("&", "and"))


def withhold_minors(days) -> Withheld:
    """Remove children and their parents from every day's people, in place.
    Run before build_roster / render_job_page / any page creation."""
    out = Withheld()
    kids_job = is_kids_job(days)
    seen: set[str] = set()
    for d in days:
        kept = []
        for p in d.people:
            why = why_withheld(p, kids_job)
            if not why:
                kept.append(p)
                continue
            (out.parents if why == "parent" else out.children).add(p.name.strip().lower())
            if why == "child" and CHILD_ROLE.search(p.role_raw or "") and p.canonical == "talent" \
                    and not re.search(r"\bmodels?\b", p.role_raw or "", re.I):
                out.actors = True
            a = agency_of(p)
            if a and _agency_key(a) not in seen:
                seen.add(_agency_key(a))
                out.agencies.append(a)
        d.people[:] = kept
    return out
