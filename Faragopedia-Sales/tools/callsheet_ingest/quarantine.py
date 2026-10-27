"""Pre-write sanity checks for pages an ingest is about to CREATE (safeguard B3).

Every check here is a shape the 2026-10-26 incident actually produced. A candidate that
fails is quarantined: it is listed for a person to review and never written, and its
name stays plain text on the callsheet page. Nothing is "fixed" automatically — a
wrong-looking name is usually a parsing problem upstream, and that is what needs fixing.

    contacts created then:  ADIDAS, SPOMA, SALES, PRODUCER, PR (ADIDAS), NEW BALANCE), YY
    companies created then: jordan-example, remy-sample, alex-placeholder (people's names)
"""
from __future__ import annotations

import difflib
import re
import unicodedata

from wiki_filter import PLACEHOLDER_NAMES, RoleVocabulary


def norm(name: str) -> str:
    """Matching key that ignores case, accents, punctuation and spacing."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s.replace("&", "and"))


def role_words(vocab: RoleVocabulary) -> set[str]:
    """Every role label roles.yml knows (aliases and canonical names), plus the section
    headings callsheets group people under. A contact named one of these is a heading or a
    role that leaked into the name column."""
    words = {norm(a) for a in vocab.aliases}
    words |= {norm(c.replace("_", " ")) for c in vocab.roles}
    words |= {norm(w) for w in ("client", "production", "comms", "sales", "spoma", "pr", "band",
                                "management", "label", "socials and digital", "culture marketing",
                                "sports marketing", "creative direction", "talent", "crew")}
    words.discard("")
    return words


def is_farago(company: str) -> bool:
    return norm(company).startswith("faragoprojects")


def near_duplicate(key: str, existing: dict[str, str], cutoff: float = 0.88) -> str | None:
    """The existing contact slug this name is probably a spelling variant of
    ('Lena Brüning' / lena-bruening, 'Kenta Morikaw' / kenta-morikawa), or None."""
    if key in existing:
        return existing[key]  # same letters, different spacing/punctuation: 'Maria Da Costa' / maria-dacosta
    for k in difflib.get_close_matches(key, existing, n=1, cutoff=cutoff):
        return existing[k]
    return None


def contact_problems(name: str, *, company_keys: set[str], roles: set[str],
                     existing_contacts: dict[str, str] | None = None, company: str = "") -> list[str]:
    """Why `name` must not become a new contact page ([] = fine).
    company_keys: norm() of every known company slug/name, including this job's own company column.
    existing_contacts: norm(slug) -> slug for every contact page, for near-duplicate checks."""
    problems = []
    raw = name.strip()
    key = norm(raw)
    letters = re.sub(r"[^A-Za-z]", "", raw)
    if "\\" in raw or "|" in raw:
        problems.append("contains \\ or | (a split table cell)")
    if raw.lower() in PLACEHOLDER_NAMES or not key:
        problems.append("placeholder / empty")
    if key in roles:
        problems.append("is a role or section label, not a person")
    if key and key in company_keys:
        problems.append("matches a company name")
    if len(letters) > 3 and letters.isupper() and " " in raw:
        problems.append("all-caps multi-word (looks like a company or heading)")
    if "(" in raw or ")" in raw:
        problems.append("bracketed note in the name (e.g. '(at showroom)') or a truncated cell")
    if 0 < len(letters) <= 3 and letters.isupper():
        problems.append("initials only — open question for Simon whether these get pages")
    if company and is_farago(company):
        problems.append("Farago's own people get pages by hand (staff-page policy), not automatically")
    if key and existing_contacts and (dup := near_duplicate(key, existing_contacts)):
        problems.append(f"probably the same person as contacts/{dup} — if so, add to --aliases")
    return problems


def company_problems(name: str, *, person_keys: set[str], row_person: str, roles: set[str]) -> list[str]:
    """Why `name` must not become a new company page ([] = fine).
    person_keys: norm() of every known contact slug and every person on this job's roster."""
    problems = []
    raw = name.strip()
    key = norm(raw)
    if "\\" in raw or "|" in raw:
        problems.append("contains \\ or | (a split table cell)")
    if not key or raw.lower() in PLACEHOLDER_NAMES:
        problems.append("placeholder / empty")
    if key and key == norm(row_person):
        problems.append("same as the person's own name on this row (shifted columns)")
    elif key in person_keys:
        problems.append("matches a person's name")
    if key in roles:
        problems.append("is a role or section label, not a company")
    if is_farago(raw):
        problems.append("a Farago office: map it to the existing farago-projects* page with --aliases")
    return problems
