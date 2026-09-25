"""Rebuild company pages onto the real entity-type schema from free, verifiable sources.

Layer 1 (no network beyond the wiki): key_contacts repaired to real contacts/ links,
Contacts / Job History / Industry Connections rebuilt from live callsheets and contact
pages, farago_history / last_job_date / status derived from job dates.
Layer 2 (free public data): Wikidata (accepted only when its official website matches
the page's website domain and the entity is not a person), Wikipedia summary, and the
company's own site meta description as a last resort. Cached in enrichment-cache/.
Meeting History comes from the Outreach Log sheet, read-only, classified by rules
because outcomes are written as free text in whichever column was nearest.

Never overwrites a non-empty frontmatter field (except the derived ones above), never
touches `industry`, never invents a wiki link. Dry-run by default: renders every page
to --out with a diff against live. --live writes.

    python enrich_companies.py --only adidas zara --regen-overview
    python enrich_companies.py --all --out out/ --live
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

import yaml
from dotenv import load_dotenv

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
load_dotenv(HERE / ".env")
import wikiapi as ia  # noqa: E402

TODAY = dt.date.today()
ACTIVE_WINDOW = dt.timedelta(days=548)  # 18 months: leaves room for contact time between jobs
CACHE = HERE / "enrichment-cache"
# Wikimedia throttles clients without contact info; a repo URL satisfies their UA policy without a personal email
WD_UA = {"User-Agent": "FaragopediaEnrichment/1.0 (+https://github.com/accountantwise/Faragopedia-Sales-V2)"}
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"}

FIELD_ORDER = ["name", "parent_group", "brands", "website", "instagram", "linkedin", "industry",
               "company_size", "hq_location", "address", "campaigns_per_year",
               "production_companies_used", "psl_status", "key_contacts", "farago_history",
               "last_job_date", "last_job_value", "status", "notes"]
STATUS_VALUES = {"Prospect", "Active Client", "Lapsed", "Lost"}
SECTIONS = ["Company Overview", "Recent News & Social Activity", "Contacts", "Meeting History",
            "Job History", "Competitor Production Companies", "Industry Connections"]
SECTION_ALIASES = {"Overview": "Company Overview", "Key Contacts": "Contacts", "Talent": "Contacts"}
STUB_OVERVIEWS = {"", "Production company or agency."}
PLACEHOLDER = re.compile(r"^\*.*\*$")
# Lines this script writes itself; rebuilt from data every run, never carried over as manual text.
GENERATED_MEETING = re.compile(r"Log: “|\[\[(outreach|meetings)/|Listed as an outreach target|\*\*Converted:\*\*")
GENERATED_CONTACT = re.compile(r"^On Farago callsheets:$|^- …and \d+ more|\(no wiki page yet\)$")
RESEARCH: dict = {}  # slug -> {"website", "news": [...]}, from --research
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug",
                                      "sep", "oct", "nov", "dec"], start=1)}


# ---------------------------------------------------------------- http helpers

def http_json(url: str, headers: dict, data: bytes | None = None, tries: int = 5):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code not in (429, 500, 502, 503, 504) or attempt == tries - 1:
                raise
            wait = e.headers.get("Retry-After") if e.code == 429 else None
            time.sleep(int(wait) if wait and wait.isdigit() else 5 * 2 ** attempt)
            continue
        except (TimeoutError, urllib.error.URLError):
            if attempt == tries - 1:
                raise
        time.sleep(2 ** attempt)


SMALL_WORDS = {"and", "of", "for", "the", "a", "an", "to", "in", "on", "at", "&"}
ACRONYMS = {"pr", "ceo", "cmo", "cco", "coo", "vp", "svp", "evp", "dop", "hmu", "mua", "uk", "us", "eu", "ai", "hr", "it", "tv", "ecom", "ac", "dp", "dit", "bts", "3d", "vfx", "cgi"}


def tidy_role(role: str) -> str:
    """'EXECUTIVE PRODUCER AND HEAD OF CREATIVE SERVICES' / 'PRODUCER (for X)' -> readable title case,
    leaving already mixed-case text alone."""
    def fix(m):
        words = m.group(0).lower().split(" ")
        return " ".join(w.upper() if w in ACRONYMS else w if (i and w in SMALL_WORDS) else w[:1].upper() + w[1:]
                        for i, w in enumerate(words))
    return re.sub(r"\b[A-Z0-9][A-Z0-9&/\-]*(?: [A-Z0-9&/\-]+)*\b",
                  lambda m: fix(m) if re.search(r"[A-Z].*[A-Z]|[0-9][A-Z]", m.group(0)) else m.group(0), role.strip())


def article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def possessive(name: str) -> str:
    return f"{name}'" if name.endswith("s") else f"{name}'s"


def norm(name: str) -> str:
    """Matching key that survives case, accents, punctuation and '&' vs 'and':
    'Ace & Tate' == 'ace-and-tate', "Catherine O'Tool" == 'catherine-otool', 'M.A.P.' == 'map'."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]", "", s)


def domain(url: str | None) -> str:
    return re.sub(r"^https?://(www\.)?", "", (url or "").strip().lower()).split("/")[0]


# ---------------------------------------------------------------- page parsing

def split_page(content: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", content, re.S)
    if not m:
        return {}, content
    try:
        return yaml.safe_load(m.group(1)) or {}, m.group(2)
    except yaml.YAMLError:
        return lenient_frontmatter(m.group(1)), m.group(2)


def lenient_frontmatter(text: str) -> dict:
    """Some ingested pages have unquoted values YAML rejects (e.g. 'name: & Other Stories')."""
    fm: dict = {}
    key = None
    for line in text.split("\n"):
        kv = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
        if kv:
            key, raw = kv.group(1), kv.group(2).strip()
            if raw.startswith("["):
                try:
                    fm[key] = json.loads(raw)
                    continue
                except ValueError:
                    pass
            fm[key] = raw.strip("'\"")
        elif key and line.strip().startswith("- "):
            if not isinstance(fm.get(key), list):
                fm[key] = []
            fm[key].append(line.strip()[2:].strip("'\""))
    return fm


def parse_sections(body: str) -> dict[str, list[str]]:
    """'## Heading' -> body lines, with old headings folded into the schema names."""
    out: dict[str, list[str]] = {}
    current = None
    for line in body.split("\n"):
        h = re.match(r"^## (.+?)\s*$", line)
        if h:
            current = SECTION_ALIASES.get(h.group(1), h.group(1))
            out.setdefault(current, [])
        elif current:
            out[current].append(line)
    return out


def text_of(lines: list[str]) -> str:
    return "\n".join(lines).strip()


def manual_lines(lines: list[str]) -> list[str]:
    """Lines a human wrote that the rebuild must keep: not blank, not a placeholder,
    not a bare wikilink bullet we regenerate from data."""
    keep = []
    for ln in lines:
        s = ln.strip()
        if not s or PLACEHOLDER.match(s) or s.startswith(("_Source", "_Web research", "_From the Outreach Log")):
            continue
        if re.match(r"^- \[\[(contacts|callsheets|jobs|industries)/", s):
            continue
        keep.append(ln.rstrip())
    return keep


def wikilink_targets(value) -> list[str]:
    items = value if isinstance(value, list) else [value] if value else []
    return [t for v in items for t in re.findall(r"\[\[([^\]|]+)", str(v))]


def yaml_scalar(v) -> str:
    if v is None or v == "":
        return "''"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return json.dumps(v.isoformat()[:10])
    if isinstance(v, list):
        return "[" + ", ".join(json.dumps(str(x), ensure_ascii=False) for x in v) + "]"
    return json.dumps(str(v), ensure_ascii=False)


def render_frontmatter(fm: dict) -> str:
    keys = FIELD_ORDER + [k for k in fm if k not in FIELD_ORDER]
    lines = []
    for k in keys:
        v = fm.get(k, [] if k in ("brands", "production_companies_used", "key_contacts") else "")
        if k == "tags" and isinstance(v, list):
            lines.append("tags:" + "".join(f"\n- {json.dumps(str(t), ensure_ascii=False)}" for t in v))
        else:
            lines.append(f"{k}: {yaml_scalar(v)}")
    return "---\n" + "\n".join(lines) + "\n---\n"


# ---------------------------------------------------------------- wiki data (layer 1)

class Wiki:
    def __init__(self):
        self.index = ia.all_pages()
        self.contacts = set(self.index.get("contacts", []))
        self.companies = set(self.index.get("companies", []))
        self._page_cache: dict[str, str] = {}
        self._company_keys: dict[str, str] | None = None
        self._contact_keys = self._unique({norm(p.split("/")[-1][:-3]): p[:-3] for p in self.contacts})

    @staticmethod
    def _unique(pairs) -> dict[str, str]:
        out, clash = {}, set()
        for k, v in (pairs.items() if isinstance(pairs, dict) else pairs):
            if k in out and out[k] != v:
                clash.add(k)
            out[k] = v
        return {k: v for k, v in out.items() if k not in clash and k}

    def company_keys(self) -> dict[str, str]:
        """norm(slug | name | each alias) -> slug. Ambiguous keys are dropped, never guessed."""
        if self._company_keys is None:
            pairs = []
            for path in self.companies:
                slug = path.split("/")[-1][:-3]
                fm, _ = split_page(self.get(path))
                pairs.append((norm(slug), slug))
                pairs.append((norm(fm.get("name") or ""), slug))
                for a in fm.get("aliases") or []:
                    pairs.append((norm(a), slug))
            self._company_keys = self._unique(pairs)
        return self._company_keys

    def resolve_company(self, value) -> str | None:
        targets = wikilink_targets(value)
        raw = targets[0] if targets else str(value or "").strip()
        if not raw or raw.lower() in ("unknown", "-", "n/a"):
            return None
        if raw.startswith("companies/") and f"{raw}.md" in self.companies:
            return raw.split("/")[-1]
        return self.company_keys().get(norm(raw.removeprefix("companies/")))

    def resolve_clients(self, value) -> list[str]:
        """A callsheet client field -> company slugs. Whole value first, then without a
        bracketed parent ('Johnnie Walker (Diageo)'), then each part of a joint client
        ('Y-3 / Mercedes-AMG ...', 'Rimowa / Another Man China')."""
        whole = self.resolve_company(value)
        if whole:
            return [whole]
        text = str(value or "")
        bare = re.sub(r"\s*\([^)]*\)", "", text).strip()
        if bare != text and self.resolve_company(bare):
            return [self.resolve_company(bare)]
        parts = [p for p in re.split(r"\s+(?:/|x|X|×)\s+", bare) if p.strip()]
        found = [s for s in (self.resolve_company(p) for p in parts) if s] if len(parts) > 1 else []
        return list(dict.fromkeys(found))

    def resolve_contact(self, value) -> str | None:
        """'contacts/x' | '[[Name]]' | 'Name' -> 'contacts/slug' when exactly one page matches."""
        targets = wikilink_targets(value)
        raw = targets[0] if targets else str(value or "").strip()
        if raw.startswith("contacts/") and f"{raw}.md" in self.contacts:
            return raw
        return self._contact_keys.get(norm(raw.removeprefix("contacts/")))

    def get(self, path: str) -> str:
        if path not in self._page_cache:
            self._page_cache[path] = ia.get_page(path)
        return self._page_cache[path]

    def contact_title(self, path: str) -> str:
        fm, _ = split_page(self.get(path))
        t = str(fm.get("job_title") or "").strip()
        return tidy_role(t)

    def scan_callsheets(self) -> dict[str, list[dict]]:
        """company slug -> [{job, name, category, start, end, as_client, people:[(role, link)]}]"""
        by_company: dict[str, dict[str, dict]] = {}
        for path in self.index.get("callsheets", []):
            fm, body = split_page(self.get(path))
            job = str(fm.get("job_reference_number", "")).strip()
            base = {"job": job, "name": fm.get("name", ""), "category": fm.get("category", ""),
                    "start": str(fm.get("shoot_start") or ""), "end": str(fm.get("shoot_end") or fm.get("shoot_start") or ""),
                    "path": path.removesuffix(".md"), "client_slug": ""}
            clients = self.resolve_clients(fm.get("client"))
            base["client_slug"] = clients[0] if clients else ""
            for client_slug in clients:
                entry = by_company.setdefault(client_slug, {}).setdefault(job, dict(base, as_client=True, people=[]))
                entry["as_client"] = True
            for row in re.findall(r"^\|(.+)\|\s*$", body, re.M):
                cells = [c.strip() for c in row.split("|")]
                if len(cells) < 3 or cells[0] in ("Role",) or cells[0].startswith("---"):
                    continue
                for comp in re.findall(r"\[\[companies/([^\]|]+)", cells[2]):
                    person = re.search(r"\[\[(contacts/[^\]|]+)", cells[1])
                    entry = by_company.setdefault(comp, {}).setdefault(job, dict(base, as_client=False, people=[]))
                    entry["people"].append((cells[0], person.group(1) if person else cells[1]))
        return {slug: sorted(jobs.values(), key=lambda j: j["start"] or "9999") for slug, jobs in by_company.items()}

    def linked_outreach_pages(self) -> dict[str, list[tuple[str, str, str]]]:
        """company slug -> [(date, page path, status)] from hand-made outreach/ and meetings/ pages."""
        out: dict[str, list] = {}
        for folder in ("outreach", "meetings"):
            for path in self.index.get(folder, []):
                fm, _ = split_page(self.get(path))
                for t in wikilink_targets(fm.get("companies_targeted") or fm.get("companies")):
                    out.setdefault(t.split("/")[-1], []).append(
                        (str(fm.get("date", "")), path.removesuffix(".md"), str(fm.get("status", ""))))
        return out


# ---------------------------------------------------------------- outreach log

def read_outreach_log() -> list[list[str]]:
    env = os.environ  # GOOGLE_* from .env: the CRM spreadsheet's OAuth client + refresh token
    tok = http_json("https://oauth2.googleapis.com/token", {"Content-Type": "application/x-www-form-urlencoded"},
                    urllib.parse.urlencode({"client_id": env["GOOGLE_CLIENT_ID"], "client_secret": env["GOOGLE_CLIENT_SECRET"],
                                            "refresh_token": env["GOOGLE_REFRESH_TOKEN"], "grant_type": "refresh_token"}).encode())
    rng = urllib.parse.quote("'Outreach Log'!A:N")
    data = http_json(f"https://sheets.googleapis.com/v4/spreadsheets/{env['GOOGLE_SHEETS_SPREADSHEET_ID']}/values/{rng}",
                     {"Authorization": f"Bearer {tok['access_token']}"})
    return data.get("values", [])


def parse_dates(text: str) -> list[dt.date]:
    out = []
    for d, mon, yr in re.findall(r"(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?(?:\s+(\d{4}))?",
                                 text, re.I):
        try:
            # the log was started in April 2026; rows without a year are 2026
            out.append(dt.date(int(yr or 2026), MONTHS[mon.lower()[:3]], int(d)))
        except ValueError:
            pass
    return out


def classify(text: str) -> tuple[int, str]:
    """Strongest signal in a row's free text -> (rank, label). Higher rank = further along."""
    t = text.lower()
    rules = [
        (5, "Meeting logged", r"\bmeeting\b|had (a )?call"),
        (4, "Call / meeting agreed", r"call scheduled|catch up|meeting booked"),
        (3, "Replied", r"\brepl(ied|y received)\b|\bresponded\b"),
        (1, "Dead end (bounced / left the company)", r"bounced|not working|not at the company|no longer"),
        (2, "Contacted, no reply recorded", r"did not respond|no reply"),
        (2, "Contacted", r"e-?mailed|reached out|messaged|chased|followed up|phone|email"),
    ]
    for rank, label, pat in rules:
        if re.search(pat, t):
            return rank, label
    return 0, ""


def outreach_by_company(rows: list[list[str]], wiki: "Wiki") -> tuple[dict, list]:
    """Match log rows to companies by name/alias, else a unique 'slug-*' prefix
    (e.g. 'Acne' -> acne-studios). Anything looser is reported, not guessed."""
    company_slugs = {p.split("/")[-1][:-3] for p in wiki.companies}
    matched: dict[str, list[dict]] = {}
    unmatched = []
    for i, r in enumerate(rows[1:], start=2):
        r = (r + [""] * 14)[:14]
        company = r[0].strip()
        if not company or company == "Company":
            continue
        slug = ia.slugify(company)
        target = wiki.resolve_company(company)
        if not target:
            prefixed = [s for s in company_slugs if s.startswith(slug + "-")]
            target = prefixed[0] if len(prefixed) == 1 else None
        if not target:
            unmatched.append(company)
            continue
        free = " | ".join(x.strip() for x in r[7:12] if x.strip())
        rank, label = classify(free)
        dates = parse_dates(free)
        matched.setdefault(target, []).append({
            "row": i, "contact": r[2].strip(), "title": r[4].strip(), "text": free,
            "rank": rank, "label": label, "first": min(dates) if dates else None,
            "last": max(dates) if dates else None})
    return matched, unmatched


# ---------------------------------------------------------------- public data (layer 2)

def load_cache(name: str) -> dict:
    p = CACHE / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_cache(name: str, data: dict):
    CACHE.mkdir(exist_ok=True)
    (CACHE / f"{name}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


WD = "https://www.wikidata.org/w/api.php?"


def wd(params: dict):
    time.sleep(0.2)
    return http_json(WD + urllib.parse.urlencode(dict(params, format="json")), WD_UA)


def claim_values(entity: dict, prop: str) -> list:
    vals = []
    for c in entity.get("claims", {}).get(prop, []):
        if c.get("rank") == "deprecated":
            continue
        v = c["mainsnak"].get("datavalue", {}).get("value")
        if isinstance(v, dict):
            v = v.get("id") or v.get("time") or v.get("amount")
        if v is not None:
            when = c.get("qualifiers", {}).get("P585", [{}])[0].get("datavalue", {}).get("value", {}).get("time", "")
            vals.append((v, when, c.get("rank") == "preferred"))
    return vals


def latest(entity: dict, prop: str):
    vals = claim_values(entity, prop)
    if not vals:
        return None
    return sorted(vals, key=lambda x: (x[2], x[1]))[-1][0]


def wikidata_lookup(name: str, site_domain: str, industry_hint: str) -> dict | None:
    """Candidates from label search, then full-text search with name variants; accept
    the first whose official website (P856) matches site_domain and isn't a human."""
    if not site_domain:
        return None
    queries = [("wbsearchentities", name)]
    for q in [name.replace(" ", ""), f"{name} {industry_hint}".strip(), f"{name} company"]:
        queries.append(("search", q))
    seen: list[str] = []
    for kind, q in queries:
        if kind == "wbsearchentities":
            r = wd({"action": "wbsearchentities", "search": q, "language": "en", "type": "item", "limit": 7})
            ids = [h["id"] for h in (r or {}).get("search", [])]
        else:
            r = wd({"action": "query", "list": "search", "srsearch": q, "srlimit": 5})
            ids = [h["title"] for h in (r or {}).get("query", {}).get("search", [])]
        ids = [i for i in ids if i not in seen]
        seen += ids
        if not ids:
            continue
        ents = (wd({"action": "wbgetentities", "ids": "|".join(ids), "props": "claims|descriptions|sitelinks",
                    "languages": "en", "sitefilter": "enwiki"}) or {}).get("entities", {})
        for i in ids:
            e = ents.get(i, {})
            sites = [domain(v[0]) for v in claim_values(e, "P856")]
            is_human = any(v[0] == "Q5" for v in claim_values(e, "P31"))
            if not is_human and any(s == site_domain or s.endswith("." + site_domain) or site_domain.endswith("." + s)
                                    for s in sites):
                return summarise_entity(i, e)
    return None


def summarise_entity(qid: str, e: dict) -> dict:
    refs = {k: latest(e, p) for k, p in [("hq", "P159"), ("parent", "P749")]}

    def fetch(ids):
        ids = [i for i in ids if i]
        return (wd({"action": "wbgetentities", "ids": "|".join(ids), "props": "labels|claims", "languages": "en"}) or {}
                ).get("entities", {}) if ids else {}
    ents = fetch(refs.values())
    # the company's own P17 lists every market it trades in; the HQ city's P17 is the real country
    hq_country = latest(ents.get(refs["hq"], {}), "P17") if refs["hq"] else None
    ents.update(fetch([hq_country]))
    label = lambda i: ents.get(i, {}).get("labels", {}).get("en", {}).get("value") if i else None  # noqa: E731
    inception = latest(e, "P571")
    emp = latest(e, "P1128")
    return {
        "qid": qid,
        "description": e.get("descriptions", {}).get("en", {}).get("value"),
        "founded": inception[1:5] if inception else None,
        "hq": label(refs["hq"]), "country": label(hq_country),
        "parent": label(refs["parent"]),
        "employees": int(float(emp)) if emp else None,
        "linkedin": latest(e, "P4264"), "instagram": latest(e, "P2003"),
        "enwiki": e.get("sitelinks", {}).get("enwiki", {}).get("title"),
    }


def wikipedia_summary(title: str) -> str | None:
    s = http_json("https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_")), WD_UA)
    if not s or s.get("type") == "disambiguation":
        return None
    sentences = re.split(r"(?<=[.!?])\s+", (s.get("extract") or "").strip())
    return " ".join(sentences[:2]) or None


def site_meta(url: str) -> dict | None:
    try:
        req = urllib.request.Request(url if url.startswith("http") else "https://" + url, headers=BROWSER_UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read(500_000).decode("utf-8", "ignore")
    except Exception:
        return None

    def meta(n):
        m = (re.search(r'<meta[^>]+(?:name|property)=["\']%s["\'][^>]+content=["\']([^"\']+)' % n, body, re.I)
             or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\']%s["\']' % n, body, re.I))
        return html.unescape(m.group(1)).strip() if m else None
    ig = sorted(set(h for h in re.findall(r"instagram\.com/([A-Za-z0-9_.]+)", body) if h not in ("p", "explore", "reel")))
    li = sorted(set(re.findall(r"linkedin\.com/company/([A-Za-z0-9_\-&%.]+)", body)))
    return {"description": meta("description") or meta("og:description"),
            "instagram": ig[0] if len(ig) == 1 else None, "linkedin": li[0] if len(li) == 1 else None}


def public_profile(slug: str, fm: dict, caches: dict, refresh: bool) -> dict:
    if slug in caches["public"] and not refresh:
        return caches["public"][slug]
    site = domain(fm.get("website"))
    hint = (wikilink_targets(fm.get("industry")) or [""])[0].split("/")[-1].split("-")[0]
    prof: dict = {"fetched": TODAY.isoformat(), "wikidata": None, "wikipedia": None, "site": None}
    prof["wikidata"] = wikidata_lookup(str(fm.get("name") or slug), site, hint)
    if prof["wikidata"] and prof["wikidata"].get("enwiki"):
        prof["wikipedia"] = wikipedia_summary(prof["wikidata"]["enwiki"])
    w = prof["wikidata"] or {}
    if site and (not prof["wikipedia"] or not (w.get("linkedin") and w.get("instagram"))):
        prof["site"] = site_meta(fm["website"])
    caches["public"][slug] = prof
    save_cache("public", caches["public"])
    return prof


# ---------------------------------------------------------------- rendering

def fmt_date(d: str) -> str:
    return d[:10] if d else ""


def date_range(j: dict) -> str:
    s, e = fmt_date(j["start"]), fmt_date(j["end"])
    return s if not e or e == s else f"{s} to {e}"


def month_year(d: str) -> str:
    return dt.date.fromisoformat(d[:10]).strftime("%b %Y") if d else "?"


def people_phrase(people: list[tuple[str, str]], limit: int = 3) -> str:
    names = []
    for role, who in people[:limit]:
        who_txt = f"[[{who}]]" if who.startswith("contacts/") else re.sub(r"\[\[|\]\]", "", who)
        names.append(f"{who_txt} ({tidy_role(role)})")
    more = f" and {len(people) - limit} more" if len(people) > limit else ""
    return ", ".join(names) + more


def build(slug: str, content: str, wiki: Wiki, jobs: list[dict], outreach: list[dict],
          outreach_pages: list, profile: dict, regen_overview: bool, overrides: dict) -> tuple[str, list[str]]:
    fm, body = split_page(content)
    fm.update(overrides)
    sections = parse_sections(body)
    flags: list[str] = []
    name = str(fm.get("name") or slug)

    # key_contacts -> real contacts/ links; unmatched names kept as plain text in the body
    kc_links, kc_unmatched = [], []
    for t in wikilink_targets(fm.get("key_contacts")):
        path = wiki.resolve_contact(t)
        (kc_links if path else kc_unmatched).append(path or t)
    kc_links = list(dict.fromkeys(kc_links))
    fm["key_contacts"] = [f"[[{p}]]" for p in kc_links]
    if kc_unmatched:
        flags.append(f"key_contacts with no contact page: {kc_unmatched}")

    client_jobs = [j for j in jobs if j["as_client"]]
    vendor_jobs = [j for j in jobs if not j["as_client"]]
    last_end = max((j["end"] for j in jobs if j["end"]), default="")
    if last_end:
        fm["last_job_date"] = fmt_date(last_end)
    if client_jobs:
        last_client = max(j["end"] for j in client_jobs)
        fm["status"] = "Active Client" if dt.date.fromisoformat(last_client[:10]) >= TODAY - ACTIVE_WINDOW else "Lapsed"
        fm["farago_history"] = (f"{len(client_jobs)} job{'s' if len(client_jobs) > 1 else ''} as client, "
                                f"{month_year(client_jobs[0]['start'])} to {month_year(last_client)}.")
    elif vendor_jobs:
        fm["farago_history"] = (f"On {len(vendor_jobs)} Farago job{'s' if len(vendor_jobs) > 1 else ''} without being the client, "
                                f"{month_year(vendor_jobs[0]['start'])} to {month_year(last_end)}.")
    elif outreach or outreach_pages:
        if fm.get("status") not in STATUS_VALUES:
            fm["status"] = "Prospect"
    if fm.get("status") and fm["status"] not in STATUS_VALUES:
        # e.g. 'Vendor' on agencies: no client/prospect criterion applies, so blank (Nick, 2026-09-25)
        flags.append(f"status {fm['status']!r} is not a schema value, cleared")
        fm["status"] = ""

    # public facts: fill empty fields only
    w = profile.get("wikidata") or {}
    site = profile.get("site") or {}
    li = w.get("linkedin") or site.get("linkedin")
    ig = w.get("instagram") or site.get("instagram")
    hq, country = w.get("hq"), w.get("country")
    fill = {
        "linkedin": f"https://www.linkedin.com/company/{li}" if li else None,
        "instagram": f"https://www.instagram.com/{ig}" if ig else None,
        "hq_location": (hq if not country or country in hq else f"{hq}, {country}") if hq else None,
        "company_size": w.get("employees"),
        "parent_group": w.get("parent"),
    }
    for k, v in fill.items():
        if v and not fm.get(k):
            fm[k] = v

    # ---- Company Overview
    old_overview = text_of(sections.get("Company Overview", []))
    generated = "_Sources:" in old_overview  # our own earlier output, safe to rebuild
    if regen_overview or generated or old_overview in STUB_OVERVIEWS:
        p1 = profile.get("wikipedia")
        if not p1 and w.get("description"):
            bits = [f"{name} is {article(w['description'])} {w['description']}"]
            if w.get("founded"):
                bits.append(f"founded in {w['founded']}")
            if fm.get("hq_location"):
                bits.append(f"headquartered in {fm['hq_location']}")
            p1 = ", ".join(bits) + "."
        if not p1 and site.get("description"):
            p1 = f"{possessive(name)} website describes it as: “{site['description']}”"
        extra = []
        if w.get("founded") and p1 and w["founded"] not in p1:
            extra.append(f"Founded {w['founded']}.")
        if w.get("parent") and p1 and w["parent"] not in p1:
            extra.append(f"Part of {w['parent']}.")
        p1 = " ".join([p1] + extra) if p1 else None
        if client_jobs:
            last = client_jobs[-1]
            p2 = (f"Farago has worked with {name} as a client on {len(client_jobs)} job{'s' if len(client_jobs) > 1 else ''} "
                  f"between {month_year(client_jobs[0]['start'])} and {month_year(last['end'])}, most recently "
                  f"{last['name']} (job {last['job']}).")
        elif vendor_jobs:
            p2 = (f"{name} has not been the commissioning client on a Farago job, but its people appear on "
                  f"{len(vendor_jobs)} Farago callsheet{'s' if len(vendor_jobs) > 1 else ''} (as an agency, supplier "
                  f"or brand partner — see Job History).")
        elif outreach or outreach_pages:
            firsts = [o["first"] for o in outreach if o["first"]] + [dt.date.fromisoformat(d[:10]) for d, _, _ in outreach_pages if d]
            when = f" since {min(firsts).strftime('%B %Y')}" if firsts else ""
            p2 = f"No Farago jobs on record. {name} has been a new-business target{when} (see Meeting History)."
        else:
            p2 = "No Farago jobs or outreach on record yet."
        sources = [s for s, ok in [("Wikipedia", profile.get("wikipedia")), ("Wikidata", w),
                                   ("company website", site.get("description") and not profile.get("wikipedia") and not w.get("description")),
                                   ("Farago callsheets", jobs), ("Outreach Log", outreach)] if ok]
        overview = "\n\n".join(x for x in [p1 or "*No public profile found yet.*", p2,
                                            f"_Sources: {', '.join(sources) or 'none'} (as of {TODAY.isoformat()})._"] if x)
        if not p1:
            flags.append("no verified public profile (Wikidata/Wikipedia/site)")
    else:
        overview = old_overview

    # ---- Contacts
    contact_lines = [f"- [[{p}]]" + (f" — {t}" if (t := wiki.contact_title(f'{p}.md')) else "") for p in kc_links]
    contact_lines += [f"- {n} (no wiki page yet)" for n in kc_unmatched]
    seen_people = set(kc_links)
    on_sheets: dict[str, dict] = {}
    for j in jobs:
        for role, who in j["people"]:
            if who.startswith("contacts/") and who not in seen_people:
                on_sheets.setdefault(who, {"role": role, "jobs": []})["jobs"].append(j["job"])
    if on_sheets:
        contact_lines.append("")
        contact_lines.append("On Farago callsheets:")
        for who, d in sorted(on_sheets.items(), key=lambda kv: -len(kv[1]["jobs"]))[:15]:
            role = tidy_role(d["role"])
            contact_lines.append(f"- [[{who}]] — {role} (job{'s' if len(d['jobs']) > 1 else ''} {', '.join(d['jobs'])})")
        if len(on_sheets) > 15:
            contact_lines.append(f"- …and {len(on_sheets) - 15} more across the callsheets below.")
    contact_lines += [ln for ln in manual_lines(sections.get("Contacts", [])) if not GENERATED_CONTACT.search(ln)]
    contacts_txt = "\n".join(dict.fromkeys(contact_lines)).strip() or \
        "*No contacts recorded yet.*"

    # ---- Meeting History
    mh = []
    for date, path, status in sorted(outreach_pages):
        mh.append(f"- {date}: [[{path}]] — {status}")
    for o in sorted(outreach, key=lambda o: (o["first"] or dt.date.max)):
        who_path = wiki.resolve_contact(o["contact"]) if o["contact"] else None
        who = f"[[{who_path}]]" if who_path else (o["contact"] or "unnamed contact")
        title = f" ({o['title']})" if o["title"] else ""
        when = o["first"].isoformat() if o["first"] else "undated"
        chased = f"; last activity {o['last'].isoformat()}" if o["last"] and o["last"] != o["first"] else ""
        if o["text"]:
            mh.append(f"- {when}: {o['label'] or 'Logged'} — {who}{title}{chased}. Log: “{o['text']}”")
        else:
            mh.append(f"- Listed as an outreach target: {who}{title}. No activity recorded in the log.")
    booked_after = [j for j in client_jobs if outreach and any(o["first"] and j["start"] and dt.date.fromisoformat(j["start"][:10]) > o["first"] for o in outreach)]
    if booked_after:
        mh.append(f"- **Converted:** job {booked_after[0]['job']} ({booked_after[0]['name']}) was booked after this outreach.")
    mh += [ln for ln in manual_lines(sections.get("Meeting History", [])) if not GENERATED_MEETING.search(ln)]
    mh = list(dict.fromkeys(mh))
    if outreach:
        mh.append("")
        mh.append("_From the Outreach Log. Outcomes are often not recorded there, so a missing reply or meeting here does not mean none happened._")
    meeting_txt = "\n".join(mh).strip() or "*No meetings logged yet.*"

    # ---- Job History
    jh = []
    for j in jobs:
        link = f"[[{j['path']}]]"
        if j["as_client"]:
            jh.append(f"- {date_range(j)}: {j['name']}, {j['category'] or 'job'} ({link}, job {j['job']}).")
        else:
            jh.append(f"- {date_range(j)}: {j['name']} — {people_phrase(j['people'])} ({link}, job {j['job']}).")
            other = j["client_slug"]
            if other and other != slug and (slug in other or other in slug):
                flags.append(f"possible duplicate: job {j['job']} credits client companies/{other}, "
                             f"but its {name} people are linked to this page")
    dropped = [ln for ln in sections.get("Job History", [])
               if ln.strip() and not PLACEHOLDER.match(ln.strip()) and ln.strip() not in jh]
    if dropped:
        flags.append(f"old Job History lines replaced by callsheet data: {dropped}")
    jobs_txt = "\n".join(jh) or "*No jobs logged yet.*"

    # ---- Industry Connections
    ic = [f"- [[{t}]]" for t in wikilink_targets(fm.get("industry")) if t.startswith("industries/")]
    ic += [ln for ln in manual_lines(sections.get("Industry Connections", [])) if ln not in ic]
    ind_txt = "\n".join(dict.fromkeys(ic)) or "*None recorded yet.*"

    out_sections = {
        "Company Overview": overview,
        "Recent News & Social Activity": news_section(slug, sections.get("Recent News & Social Activity", [])),
        "Contacts": contacts_txt,
        "Meeting History": meeting_txt,
        "Job History": jobs_txt,
        "Competitor Production Companies": text_of(sections.get("Competitor Production Companies", [])) or "*Unknown.*",
        "Industry Connections": ind_txt,
    }
    for extra in sections:
        if extra not in out_sections and text_of(sections[extra]):
            out_sections[extra] = text_of(sections[extra])
            flags.append(f"kept non-schema section: {extra}")

    page = render_frontmatter(fm) + "\n" + "\n\n".join(f"## {h}\n\n{t}" for h, t in out_sections.items()) + "\n"
    return page, flags


def news_section(slug: str, old_lines: list[str]) -> str:
    """Existing news is kept; researched items are added unless their URL is already there."""
    footers = [ln.strip() for ln in old_lines if ln.strip().startswith("_Web research")]
    old = [ln.rstrip() for ln in old_lines if ln.strip() and not PLACEHOLDER.match(ln.strip())
           and not ln.strip().startswith("_Web research")]
    new = []
    for n in (RESEARCH.get(slug) or {}).get("news", []):
        if n.get("url") and any(n["url"] in ln for ln in old):
            continue
        src = f" ([{n.get('source') or domain(n['url'])}]({n['url']}))" if n.get("url") else ""
        new.append(f"- **{n.get('date', '')} — {n['headline'].rstrip('.')}.** {n.get('summary', '').strip()}{src}")
    lines = new + old
    if new:
        lines += ["", f"_Web research, {TODAY.strftime('%B %Y')}._"]
    elif footers and old:
        lines += ["", footers[0]]
    return "\n".join(lines).strip() or "*None recorded yet.*"


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--only", nargs="+", metavar="SLUG")
    g.add_argument("--all", action="store_true")
    ap.add_argument("--regen-overview", action="store_true", help="Rebuild Company Overview even when it has prose.")
    ap.add_argument("--refresh-public", action="store_true", help="Ignore the cached Wikidata/Wikipedia results.")
    ap.add_argument("--overrides", type=Path, help="JSON {slug: {field: value}} applied before rebuilding.")
    ap.add_argument("--out", type=Path, default=HERE / "out")
    ap.add_argument("--research", type=Path, help="JSON from the web-research step: {slug: {website, news}}.")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()

    wiki = Wiki()
    slugs = sorted(p.split("/")[-1][:-3] for p in wiki.companies) if args.all else args.only
    overrides = json.loads(args.overrides.read_text(encoding="utf-8")) if args.overrides else {}
    if args.research:
        RESEARCH.update(json.loads(args.research.read_text(encoding="utf-8")))

    print("scanning callsheets...")
    jobs_by_company = wiki.scan_callsheets()
    outreach_pages = wiki.linked_outreach_pages()
    print("reading Outreach Log...")
    log_rows = read_outreach_log()
    outreach, unmatched = outreach_by_company(log_rows, wiki)
    caches = {"public": load_cache("public")}

    args.out.mkdir(parents=True, exist_ok=True)
    report = []
    for slug in slugs:
        try:
            report.append(process(slug, wiki, jobs_by_company, outreach, outreach_pages, caches, overrides, args))
        except Exception as e:  # one bad page must not sink a 291-page run
            report.append({"slug": slug, "error": f"{type(e).__name__}: {e}"})
            print(f"{slug:28} ERROR {e}")

    (args.out / "report.json").write_text(json.dumps({"companies": report, "outreach_unmatched": sorted(set(unmatched))},
                                                     indent=1, ensure_ascii=False), encoding="utf-8")
    if args.live:  # standing rule: notes cleanup after any AI processing (HUMAN: notes survive)
        from clear_notes import clean
        cleared = clean([f"companies/{r['slug']}.md" for r in report if r.get("changed")], live=True)
        print(f"notes cleanup: {len(cleared.get('cleared', []))} cleared, {len(cleared.get('kept (human flag)', []))} human flags kept")
    print(f"\n{'LIVE - written' if args.live else 'DRY RUN - nothing written'}. Output in {args.out}")


def process(slug, wiki, jobs_by_company, outreach, outreach_pages, caches, overrides, args) -> dict:
    path = f"companies/{slug}.md"
    live = wiki.get(path)
    fm, _ = split_page(live)
    if norm(fm.get("name") or slug).startswith("faragoprojects"):
        # Farago's own pages are hand-maintained: its staff are on every callsheet, which the
        # client/supplier logic would misread (Nick, 2026-09-25)
        print(f"{slug:28} skipped (Farago's own page)")
        return {"slug": slug, "changed": False, "skipped": "Farago's own page", "flags": []}
    ov = dict(overrides.get(slug, {}))
    found_site = (RESEARCH.get(slug) or {}).get("website")
    new_site = bool(found_site and not fm.get("website"))
    if new_site:
        fm["website"] = ov["website"] = found_site
    profile = public_profile(slug, fm, caches, args.refresh_public or new_site)
    page, flags = build(slug, live, wiki, jobs_by_company.get(slug, []), outreach.get(slug, []),
                        outreach_pages.get(slug, []), profile, args.regen_overview, ov)
    fname = re.sub(r'[<>:"/\|?*]', "_", slug)
    (args.out / f"{fname}.md").write_text(page, encoding="utf-8")
    diff = "".join(difflib.unified_diff(live.splitlines(True), page.splitlines(True), f"live/{slug}", f"new/{slug}"))
    (args.out / f"{fname}.diff").write_text(diff, encoding="utf-8")
    w = profile.get("wikidata") or {}
    if args.live and page != live:
        ia.write_page(path, page)
    print(f"{slug:28} {'changed' if page != live else 'same   '} wd={w.get('qid') or '-':10} "
          f"jobs={len(jobs_by_company.get(slug, [])):2} outreach={len(outreach.get(slug, [])):2} flags={len(flags)}")
    return {"slug": slug, "changed": page != live, "wikidata": w.get("qid"),
            "wikipedia": bool(profile.get("wikipedia")), "site": bool(profile.get("site")),
            "jobs": len(jobs_by_company.get(slug, [])), "outreach": len(outreach.get(slug, [])), "flags": flags}


if __name__ == "__main__":
    main()
