"""
signals.py
Measured evidence for each candidate paper, gathered with plain HTTP calls (no AI)
before the papers are scored. Every number here is shown on the paper's page,
so a reader can check why it ranked where it did.

  github    stars on the paper's code, how many it gained since we last looked,
            and whether the repo has a licence (GitHub REST API)
  hf        models, datasets and demo apps (Spaces) on Hugging Face that link the paper
  hn        Hacker News stories that link the paper: points and comments (Algolia API)
  authors   the median h-index of the paper's authors (Semantic Scholar batch API)

Each day's numbers are saved to data/signals/<date>.json. That file is both a
cache (a paper is looked up at most once a day) and a public, growing record of
how attention to each paper changes over its first days.

A lookup that fails leaves the value as None ("not known"), never 0, and the
scorer treats the two differently. No failure here can stop the edition.

Free limits: GitHub allows 1,000 calls an hour with the Actions token, Algolia
has no key, Semantic Scholar takes up to 500 papers per batch call (S2_API_KEY
is optional and raises the rate limit), Hugging Face needs no key.
"""
import json
import os
import statistics
import time
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional

import requests

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SRC_DIR)
DATA_DIR = os.path.join(ROOT_DIR, "data")

USER_AGENT = "ai-paper-daily/1.0 (+https://github.com/Omen-bit/ai-paper-daily)"
TIMEOUT = 15
# Papers that get the per-paper lookups (GitHub, HF, HN). The rest of the day's
# 1,000+ arXiv papers are ranked on what the feeds already say about them.
LOOKUP_LIMIT = int(os.environ.get("SIGNALS_LIMIT") or 60)
S2_BATCH = 500
# A repo this young had all its stars recently, so they count as gained
NEW_REPO_DAYS = 14
# How far back to look for the previous snapshot when working out growth
MAX_GAP_DAYS = 4

FIELDS = ("stars", "stars_gain", "license", "hf_models", "hf_datasets", "hf_spaces",
          "hn_points", "hn_comments", "hn_url", "h_index", "authors_found", "repo")


# ---------------------------------------------------------------- HTTP helpers

def _headers(extra: Optional[dict] = None) -> dict:
    h = {"User-Agent": USER_AGENT}
    h.update(extra or {})
    return h


def _get_json(url: str, headers: Optional[dict] = None, params: Optional[dict] = None):
    resp = requests.get(url, headers=_headers(headers), params=params, timeout=TIMEOUT)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def _post_json(url: str, body: dict, headers: Optional[dict] = None, params: Optional[dict] = None):
    resp = requests.post(url, json=body, headers=_headers(headers), params=params, timeout=TIMEOUT * 2)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------- sources

def repo_of(paper: dict) -> str:
    """'owner/name' of the paper's GitHub code, or ''."""
    import scorer
    for key in ("github_repo", "code_url"):
        url = str(paper.get(key) or "")
        if "github.com/" in url:
            return _owner_repo(url)
    m = scorer._CODE_LINK.search(paper.get("abstract") or "")
    return _owner_repo(m.group(0)) if m and "github.com/" in m.group(0) else ""


def _owner_repo(url: str) -> str:
    tail = url.split("github.com/", 1)[1].strip("/").rstrip(".,;)")
    parts = [p for p in tail.split("/") if p][:2]
    if len(parts) != 2:
        return ""
    name = parts[1][:-4] if parts[1].endswith(".git") else parts[1]
    return f"{parts[0]}/{name}"


def github_repo(owner_repo: str) -> Optional[dict]:
    """Stars, creation date and licence of a GitHub repo, or None if it can't be read."""
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = _get_json(f"https://api.github.com/repos/{owner_repo}", headers)
    if not data or "stargazers_count" not in data:
        return None
    return {"stars": int(data["stargazers_count"]), "created": (data.get("created_at") or "")[:10],
            "license": bool((data.get("license") or {}).get("spdx_id") not in (None, "NOASSERTION"))}


def hf_artifacts(arxiv_id: str) -> Optional[dict]:
    """How many models, datasets and Spaces on Hugging Face link the paper."""
    data = _get_json(f"https://huggingface.co/api/arxiv/{arxiv_id}/repos")
    if data is None:
        return {"hf_models": 0, "hf_datasets": 0, "hf_spaces": 0}
    return {f"hf_{kind}": len(data.get(kind) or []) for kind in ("models", "datasets", "spaces")}


def hn_mentions(arxiv_id: str) -> Optional[dict]:
    """Hacker News stories whose link contains the arXiv ID: total points and comments."""
    data = _get_json("https://hn.algolia.com/api/v1/search",
                     params={"query": arxiv_id, "restrictSearchableAttributes": "url", "tags": "story"})
    hits = [h for h in (data or {}).get("hits") or [] if arxiv_id in (h.get("url") or "")]
    best = max(hits, key=lambda h: h.get("points") or 0, default=None)
    return {"hn_points": sum(int(h.get("points") or 0) for h in hits),
            "hn_comments": sum(int(h.get("num_comments") or 0) for h in hits),
            "hn_url": f"https://news.ycombinator.com/item?id={best['objectID']}" if best else ""}


def s2_authors(arxiv_ids: list[str]) -> dict[str, dict]:
    """
    Median author h-index per paper from Semantic Scholar, in batches of 500.
    Papers Semantic Scholar hasn't indexed yet are left out (not known, not zero).
    """
    headers = {}
    key = os.environ.get("S2_API_KEY")
    if key:
        headers["x-api-key"] = key
    out = {}
    for start in range(0, len(arxiv_ids), S2_BATCH):
        chunk = arxiv_ids[start:start + S2_BATCH]
        rows = _post_json("https://api.semanticscholar.org/graph/v1/paper/batch",
                          {"ids": [f"ARXIV:{pid}" for pid in chunk]}, headers,
                          params={"fields": "authors.hIndex"})
        for pid, row in zip(chunk, rows or []):
            h = [a["hIndex"] for a in (row or {}).get("authors") or [] if isinstance(a.get("hIndex"), int)]
            if h:
                out[pid] = {"h_index": round(statistics.median(h), 1), "authors_found": len(h)}
    return out


# ---------------------------------------------------------------- snapshots

def snapshot_path(date_str: str, data_dir: str = DATA_DIR) -> str:
    return os.path.join(data_dir, "signals", f"{date_str}.json")


def load_snapshot(date_str: str, data_dir: str = DATA_DIR) -> dict:
    try:
        with open(snapshot_path(date_str, data_dir), encoding="utf-8") as f:
            data = json.load(f)
        return data.get("papers") or {} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def previous_snapshot(date_str: str, data_dir: str = DATA_DIR) -> tuple[dict, str]:
    """The newest snapshot before date_str (at most MAX_GAP_DAYS back) and its date."""
    day = date.fromisoformat(date_str)
    for back in range(1, MAX_GAP_DAYS + 1):
        d = (day - timedelta(days=back)).isoformat()
        snap = load_snapshot(d, data_dir)
        if snap:
            return snap, d
    return {}, ""


def save_snapshot(date_str: str, papers: dict, data_dir: str = DATA_DIR) -> str:
    path = snapshot_path(date_str, data_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"date": date_str, "generated_at": datetime.now(timezone.utc).isoformat(),
                   "papers": papers}, f, ensure_ascii=False, indent=1, sort_keys=True)
    return path


def stars_gain(stars: Optional[int], previous: dict, created: str, today: str) -> Optional[int]:
    """
    Stars gained since the previous snapshot. A repo under two weeks old counts
    all its stars as gained. None when we can't tell (first sighting of an old repo).
    """
    if stars is None:
        return None
    if previous.get("stars") is not None:
        return max(0, stars - int(previous["stars"]))
    try:
        age = (date.fromisoformat(today) - date.fromisoformat(created)).days
    except ValueError:
        return None
    return stars if age <= NEW_REPO_DAYS else None


# ---------------------------------------------------------------- collect

def default_sources() -> dict:
    return {"github": github_repo, "hf": hf_artifacts, "hn": hn_mentions, "s2": s2_authors}


def _safe(fn: Callable, *args, label: str = ""):
    try:
        return fn(*args)
    except Exception as exc:  # a missing signal is shown as unknown, never stops the run
        print(f"  [signals] {label} failed: {str(exc)[:120]}")
        return None


def collect(papers: list[dict], date_str: str, data_dir: str = DATA_DIR,
            limit: int = LOOKUP_LIMIT, sources: Optional[dict] = None, pause: float = 0.0,
            save: bool = True) -> dict[str, dict]:
    """
    Look up signals for the first `limit` papers (pass them best first), attach
    them to each paper as paper["signals"], and save the day's snapshot.
    Papers already in today's snapshot are not looked up again.
    Returns {arxiv_id: signals}.
    """
    src = {**default_sources(), **(sources or {})}
    today = load_snapshot(date_str, data_dir)
    before, before_date = previous_snapshot(date_str, data_dir)
    todo = [p for p in papers[:limit] if p.get("id") and p["id"] not in today]

    s2 = _safe(src["s2"], [p["id"] for p in todo], label="Semantic Scholar") if todo else {}
    s2_ok = s2 is not None
    looked = 0
    for p in todo:
        pid = p["id"]
        sig = {k: None for k in FIELDS}
        sig["fetched"] = True
        repo = repo_of(p)
        sig["repo"] = repo or None
        if repo:
            gh = _safe(src["github"], repo, label=f"GitHub {repo}")
            if gh:
                sig["stars"] = gh["stars"]
                sig["license"] = gh["license"]
                sig["stars_gain"] = stars_gain(gh["stars"], before.get(pid) or {}, gh.get("created", ""), date_str)
        hf = _safe(src["hf"], pid, label=f"Hugging Face {pid}")
        if hf:
            sig.update(hf)
        hn = _safe(src["hn"], pid, label=f"Hacker News {pid}")
        if hn:
            sig.update(hn)
        if s2_ok and pid in s2:
            sig.update(s2[pid])
        sig["upvotes"] = int(p.get("hf_upvotes") or 0)
        today[pid] = sig
        looked += 1
        if pause:
            time.sleep(pause)

    for p in papers:
        if p.get("id") in today:
            p["signals"] = today[p["id"]]
    if save and (looked or not os.path.exists(snapshot_path(date_str, data_dir))):
        save_snapshot(date_str, today, data_dir)
    since = f", growth since {before_date}" if before_date else ""
    print(f"  [signals] Looked up {looked} papers ({len(today)} in today's snapshot{since}).")
    return today
