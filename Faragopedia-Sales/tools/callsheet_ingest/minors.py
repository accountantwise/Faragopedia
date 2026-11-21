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
- anyone whose role is a parent or guardian of someone on set (MOTHER, FATHER, GUARDIAN),
  and every CHAPERONE: chaperones are often parents, and the row usually names the child;
- talent a chaperone row says it is "for": a chaperone means a minor, even on an adult job
  booked through an adult agency;
- every talent row on a job with a chaperone in any wording ("TALENT CHAPERONE",
  "MODEL'S CHAPERONE (Sam)"), even when the row does not say who it is for;
- once any child is found on a job, every other talent row on that job too. Callsheets
  give no ages, and a child can appear with no signal at all (a first name in a call-time
  line, a "FRIEND" booked direct), so one confirmed child is treated as a children's cast.

A combined role (`talent + other`, for MODEL/CHAPERONE) counts as talent. After all of
that, any kept row whose role, company or contact route still names a withheld person is
withheld too, and an agency named in the anonymous note is cut back to the agency itself
("Example Kids Ltd (agent for <child>)" -> "Example Kids Ltd").

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
PARENT_ROLE = re.compile(r"\b(mother|father|mum|mom|dad|parent|guardian|chaperone)\b", re.I)
# Agencies whose whole name is a parent word. "Parent" is a London artist agency
# (directors, photographers): "LEAD PRODUCER: NAME @ PARENT" is an adult producer, not a
# child's parent (job 393, Nick 2026-11-21). Exact name only: "Parent of X", "c/o parent"
# and any parent word in the role are still withheld.
NOT_PARENT_AGENCIES = ("parent",)
# "CHAPERONE (for Sam, Model)" in the role, or "Chaperone for Sam (Model)" in the company.
CHAPERONE_FOR = re.compile(r"chaperone\b[^|]*?\bfor\s+([^,()|;]+)", re.I)
# Everything after the agency itself in an agent's company cell.
AGENT_FOR_TAIL = re.compile(r"\s*(?:[;,(]|\bagent for\b|\bfor\b).*$", re.I)
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


def is_talent(canonical: str) -> bool:
    """`talent`, or a combined role that includes it (`talent + other`)."""
    return any(c.strip() == "talent" for c in (canonical or "").split("+"))


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def chaperoned(days) -> set[str]:
    """Names (as keys) that a chaperone row says it is for. Read from the unfiltered sheet:
    chaperones map to `other` and are gone from `d.people` by the time this runs."""
    out = set()
    for d in days:
        for p in d.sheet.people + list(d.people):
            for text in (p.role_raw, p.company):
                for m in CHAPERONE_FOR.finditer(text or ""):
                    out.add(_key(m.group(1)))
    return out - {""}


def has_chaperone(days) -> bool:
    """True when any row on the job, filtered or not, is a chaperone in any wording:
    "TALENT CHAPERONE", "MODEL'S CHAPERONE (Sam)", "Chaperone" in the company cell.
    Nick, 2026-11-19: a chaperone means a child is on the job, named or not, so every
    talent row is withheld. A chaperone that says who it is for is also caught by
    chaperoned(); this catches the ones that don't."""
    for d in days:
        for p in d.sheet.people + list(d.people):
            if re.search(r"\bchaperones?\b", f"{p.role_raw or ''} {p.company or ''}", re.I):
                return True
    return False


def why_withheld(p, kids_job: bool, chaperoned_keys: set[str] = frozenset()) -> str | None:
    """Why this callsheet row must not reach the wiki, or None to keep it."""
    role = p.role_raw or ""
    company = p.company or ""
    if PARENT_ROLE.search(role) or (PARENT_ROLE.search(company)
                                     and _agency_key(company) not in NOT_PARENT_AGENCIES):
        return "parent"
    if not is_talent(p.canonical):
        return None
    if _key(p.name) in chaperoned_keys:
        return "child"
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
        return _agency_only(company.rsplit("@", 1)[1])
    if company and company.lower() not in ("unknown", "—", "-") and not company.lower().startswith("c/o"):
        return _agency_only(company)
    for via in p.contact_via:
        parts = [x.strip() for x in via.split(",") if x.strip() and not PHONE.match(x.strip()) and "@" not in x]
        if len(parts) >= 2:
            return _agency_only(parts[1])
    return None


def _agency_only(text: str) -> str | None:
    """'KIDS LONDON LTD (agent for <child>, MODEL)' -> 'KIDS LONDON LTD'. The note is the
    one place a withheld row leaves a trace, so it carries the agency and nothing else."""
    return AGENT_FOR_TAIL.sub("", (text or "").strip()).strip() or None


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
    chap = chaperoned(days)
    seen: set[str] = set()
    # One confirmed child makes every talent row on the job a possible child (see module doc).
    children_on_job = kids_job or has_chaperone(days) or any(
        why_withheld(p, kids_job, chap) == "child" for d in days for p in d.people)
    for d in days:
        kept = []
        for p in d.people:
            why = why_withheld(p, children_on_job, chap)
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
    # Last pass: nothing kept may still name a withheld person ("Chaperone for <child>",
    # "agent for <child>", a contact route through a parent).
    gone = [n for n in out.children | out.parents if len(_key(n)) >= 3]
    if gone:
        pat = re.compile(r"(?<![a-z])(" + "|".join(re.escape(n) for n in gone) + r")(?![a-z])", re.I)
        for d in days:
            linked = [p for p in d.people
                      if pat.search(" ".join([p.role_raw or "", p.company or "", *p.contact_via]))]
            for p in linked:
                out.parents.add(p.name.strip().lower())
            d.people[:] = [p for p in d.people if p not in linked]
    out.agencies = [a for a in out.agencies if not (gone and pat.search(a))]
    return out
