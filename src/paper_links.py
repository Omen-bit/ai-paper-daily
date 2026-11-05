"""
paper_links.py
What surrounds each paper on its page, gathered once a day by the pipeline:
  - Hugging Face: models, datasets and demo apps (Spaces) that link the paper
  - GitHub: stars on the paper's code
  - Semantic Scholar: the papers it builds on, and later papers that cite it
  - the lab or company behind it: the Hugging Face organization that claimed it,
    else the authors' institutions on OpenAlex (see labs.py)

Everything is saved in data/links.json, keyed by arXiv ID, and the site builder
reads it. Plain HTTP calls, no AI. Each service is optional: when one is down or
rate limited, the paper keeps what it had and the page leaves that part out.

Run after main.py:  python src/paper_links.py
"""
import json
import os
import re
import sys
import time
from datetime import date, timedelta

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import labs  # noqa: E402

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SRC_DIR)
DATA_DIR = os.path.join(ROOT_DIR, "data")
LINKS_FILE = os.path.join(DATA_DIR, "links.json")

USER_AGENT = "ai-paper-daily/1.0 (+https://github.com/Omen-bit/ai-paper-daily)"
TIMEOUT = 15
# Semantic Scholar allows about one request a second without a key
S2_PAUSE = float(os.environ.get("S2_PAUSE", "1.1"))
S2_FIELDS = ("citationCount,influentialCitationCount,"
             "references.title,references.year,references.externalIds,references.citationCount,"
             "citations.title,citations.year,citations.externalIds,citations.citationCount")
# Requests per run, so a big backlog spreads over several days instead of one slow run
MAX_LOOKUPS = int(os.environ.get("LINKS_MAX_LOOKUPS", "120"))
# New papers change fastest: look again after a week while they are under two months old
RECHECK_DAYS = 7
RECHECK_UNTIL_AGE = 60
SHOW = 3  # items kept per list
# Lab lookups per run (two quick calls each), so the backlog of older papers fills in within days
ORG_MAX_LOOKUPS = int(os.environ.get("ORG_MAX_LOOKUPS", "300"))


def _abstract_code(abstract: str) -> str:
    m = re.search(r"https?://(?:www\.)?github\.com/[\w.\-]+/[\w.\-]+", abstract)
    return m.group(0).rstrip(".,;)") if m else ""


def _get(url: str, headers: dict | None = None):
    h = {"User-Agent": USER_AGENT}
    h.update(headers or {})
    resp = requests.get(url, timeout=TIMEOUT, headers=h)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def hf_repos(arxiv_id: str) -> dict:
    """Models, datasets and Spaces on Hugging Face that link this paper, most liked first."""
    data = _get(f"https://huggingface.co/api/arxiv/{arxiv_id}/repos") or {}
    out = {}
    for kind in ("models", "datasets", "spaces"):
        items = data.get(kind) or []
        items = sorted(items, key=lambda r: -(r.get("likes") or 0))
        out[kind] = {"n": len(items), "top": [{"id": r.get("id"), "likes": r.get("likes") or 0}
                                               for r in items[:SHOW] if r.get("id")]}
    return out


def github_stars(code_url: str) -> int | None:
    """Stars on a GitHub repository, or None if the link isn't a GitHub repo."""
    parts = (code_url or "").split("github.com/", 1)
    if len(parts) < 2:
        return None
    owner_repo = "/".join(parts[1].strip("/").split("/")[:2])
    if owner_repo.count("/") != 1:
        return None
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = _get(f"https://api.github.com/repos/{owner_repo}", headers)
    return int(data["stargazers_count"]) if data and "stargazers_count" in data else None


def _paper_ref(p: dict) -> dict | None:
    if not p or not p.get("title"):
        return None
    ids = p.get("externalIds") or {}
    return {"title": p["title"], "year": p.get("year"), "arxiv": ids.get("ArXiv"),
            "cites": p.get("citationCount") or 0}


def s2_lineage(arxiv_id: str) -> dict:
    """The most cited papers it builds on, and the papers citing it (most cited first)."""
    data = _get(f"https://api.semanticscholar.org/graph/v1/paper/arXiv:{arxiv_id}?fields={S2_FIELDS}")
    if not data:
        return {"found": False}
    refs = [r for r in (_paper_ref(x) for x in data.get("references") or []) if r]
    cites = [r for r in (_paper_ref(x) for x in data.get("citations") or []) if r]
    refs.sort(key=lambda r: -r["cites"])
    cites.sort(key=lambda r: (-r["cites"], -(r["year"] or 0)))
    return {"found": True, "cited_by": data.get("citationCount") or len(cites),
            "influential": data.get("influentialCitationCount") or 0,
            "refs_n": len(refs), "refs": refs[:SHOW], "cites": cites[:SHOW]}


def hf_paper_org(arxiv_id: str) -> str:
    """The organization that claimed the paper on Hugging Face Papers, or ''."""
    data = _get(f"https://huggingface.co/api/papers/{arxiv_id}") or {}
    return labs.from_hf_org(data.get("organization"))


def openalex_org(arxiv_id: str) -> str:
    """The authors' most common institution on OpenAlex (arXiv DOIs are 10.48550/arXiv.<id>)."""
    url = f"https://api.openalex.org/works/doi:10.48550/arXiv.{arxiv_id}?select=authorships"
    key = os.environ.get("OPENALEX_API_KEY")
    if key:
        url += f"&api_key={key}"
    return labs.from_institutions(labs.openalex_institutions(_get(url) or {}))


def org_due(rec: dict, entry: dict, today: date) -> bool:
    """Look for the lab once, and again weekly while a young paper still has none."""
    if rec.get("org") or entry.get("org"):
        return False
    return due({"checked": entry.get("org_checked")}, rec.get("submitted") or rec.get("first_seen") or "", today)


def refresh_orgs(papers: dict, links: dict, today: date | None = None,
                 max_lookups: int = ORG_MAX_LOOKUPS) -> int:
    """Fill links[id]["org"] for papers whose record has no lab. Returns how many were looked up."""
    today = today or date.today()
    done = 0
    for rec in paper_order(papers):
        if done >= max_lookups:
            break
        pid = rec["id"]
        entry = links.get(pid) or {}
        if not org_due(rec, entry, today):
            continue
        entry = dict(entry)
        org, ok = "", False
        code = rec.get("code_url") or _abstract_code(rec.get("abstract") or "")
        for name, find in (("Hugging Face", hf_paper_org), ("code", lambda _: labs.from_code_url(code)),
                           ("OpenAlex", openalex_org)):
            try:
                org = find(pid)
                ok = True
            except Exception as exc:
                print(f"  [links] {name} lab lookup failed for {pid}: {str(exc)[:100]}")
            if org:
                break
        if org:
            entry["org"] = org
        if ok:
            entry["org_checked"] = today.isoformat()
        links[pid] = entry
        done += 1
    return done


def load(path: str = LINKS_FILE) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(links: dict, path: str = LINKS_FILE) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(links, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    os.replace(tmp, path)


def due(entry: dict | None, published: str, today: date) -> bool:
    """Look a paper up if we never have, or weekly while it is young."""
    if not entry or not entry.get("checked"):
        return True
    try:
        checked = date.fromisoformat(entry["checked"])
        born = date.fromisoformat((published or entry["checked"])[:10])
    except ValueError:
        return True
    return (today - born).days <= RECHECK_UNTIL_AGE and (today - checked).days >= RECHECK_DAYS


def paper_order(papers: dict) -> list[dict]:
    """Picks first, then the newest papers, so the most read pages fill in first."""
    newest_first = sorted(papers.values(), key=lambda r: r.get("first_seen") or "", reverse=True)
    return sorted(newest_first, key=lambda r: 0 if r.get("featured") else 1)  # stable: keeps the date order


def refresh(papers: dict, links: dict, today: date | None = None, max_lookups: int = MAX_LOOKUPS,
            pause: float = S2_PAUSE) -> int:
    """Update links in place for papers that are due. Returns how many papers were looked up."""
    today = today or date.today()
    done = 0
    for rec in paper_order(papers):
        if done >= max_lookups:
            break
        pid = rec["id"]
        old = links.get(pid) or {}
        if not due(old, rec.get("submitted") or rec.get("first_seen") or "", today):
            continue
        entry = dict(old)
        try:
            entry["hf"] = hf_repos(pid)
        except Exception as exc:
            print(f"  [links] Hugging Face lookup failed for {pid}: {str(exc)[:100]}")
        code = rec.get("code_url") or _abstract_code(rec.get("abstract") or "")
        if code:
            try:
                stars = github_stars(code)
                if stars is not None:
                    entry["stars"] = stars
            except Exception as exc:
                print(f"  [links] GitHub lookup failed for {pid}: {str(exc)[:100]}")
        try:
            entry["s2"] = s2_lineage(pid)
        except Exception as exc:
            print(f"  [links] Semantic Scholar lookup failed for {pid}: {str(exc)[:100]}")
        if pause:
            time.sleep(pause)
        if entry.get("hf") or entry.get("s2"):
            entry["checked"] = today.isoformat()
        links[pid] = entry
        done += 1
    return done


def run() -> None:
    sys.path.insert(0, SRC_DIR)
    import site_builder
    papers = site_builder.merge_papers(site_builder.load_days(DATA_DIR))
    links = load()
    # Drop papers that no longer have a page
    links = {k: v for k, v in links.items() if k in papers}
    n = refresh(papers, links)
    save(links)
    k = refresh_orgs(papers, links)
    save(links)
    found = sum(1 for v in links.values() if v.get("org"))
    print(f"[links] Looked up {n} papers and {k} labs; {len(links)} have links saved, {found} with a lab.")


if __name__ == "__main__":
    run()
