"""
novelty.py
How different each candidate paper is from everything we saw in the last 90 days,
measured on the words of its title and abstract (TF-IDF and cosine similarity,
the same idea arxiv-sanity uses). No AI and no downloads: the history is the
papers already saved in data/daily/.

  novelty = 1 - (similarity to the closest earlier paper)

0 means a near copy of a paper we already saw; values near 1 mean nothing
recent used the same words. The scorer turns it into points by where a paper
stands among the day's candidates, so the scale never needs tuning.
"""
import glob
import json
import math
import os
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Iterable, Optional

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SRC_DIR), "data")
HISTORY_DAYS = 90
# Words in more than this share of documents say nothing about a paper ("model", "results")
MAX_DF_SHARE = 0.1

_WORD = re.compile(r"[a-z][a-z0-9\-]{2,}")
_STOP = set("""
the and for with that this from are was were has have had our their its into than then them they these those
which while where when what who whom how can could would should may might will shall also such using used use
based via over under between both each more most other some any all not only very well new show shows shown
paper papers propose proposed approach approaches method methods results result work study present presents
""".split())


def words(text: str) -> list[str]:
    return [w for w in _WORD.findall((text or "").lower()) if w not in _STOP]


def doc_text(p: dict) -> str:
    return f"{p.get('title') or ''} {p.get('title') or ''} {p.get('abstract') or ''}"


def history(before: str, data_dir: str = DATA_DIR, days: int = HISTORY_DAYS) -> list[dict]:
    """Papers saved in the `days` days before `before` (YYYY-MM-DD), one record per ID."""
    start = (date.fromisoformat(before) - timedelta(days=days)).isoformat()
    seen = {}
    for path in sorted(glob.glob(os.path.join(data_dir, "daily", "*.json"))):
        d = os.path.basename(path)[:-5]
        if not (start <= d < before):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                for r in json.load(f).get("papers") or []:
                    if isinstance(r, dict) and r.get("id") and r.get("abstract"):
                        seen.setdefault(r["id"], r)
        except (OSError, ValueError, AttributeError):
            continue
    return list(seen.values())


class Index:
    """A small TF-IDF index over past papers with an inverted list for fast lookups."""

    def __init__(self, docs: Iterable[dict]):
        self.ids, counts = [], []
        df = Counter()
        for p in docs:
            c = Counter(words(doc_text(p)))
            if c:
                self.ids.append(p["id"])
                counts.append(c)
                df.update(c.keys())
        n = len(counts)
        self.n = n
        max_df = max(2, int(MAX_DF_SHARE * n))
        self.idf = {w: math.log((1 + n) / (1 + k)) + 1 for w, k in df.items() if k <= max_df}
        self.postings = defaultdict(list)
        for i, c in enumerate(counts):
            vec = self.vector(c)
            for w, x in vec.items():
                self.postings[w].append((i, x))

    def vector(self, counts: Counter) -> dict:
        vec = {w: (1 + math.log(k)) * self.idf[w] for w, k in counts.items() if w in self.idf}
        norm = math.sqrt(sum(x * x for x in vec.values())) or 1.0
        return {w: x / norm for w, x in vec.items()}

    def closest(self, p: dict, skip: Optional[str] = None) -> tuple[float, Optional[str]]:
        """Cosine similarity to the most similar past paper, and that paper's ID."""
        vec = self.vector(Counter(words(doc_text(p))))
        dots = defaultdict(float)
        for w, x in vec.items():
            for i, y in self.postings.get(w, ()):
                dots[i] += x * y
        best, best_id = 0.0, None
        for i, s in dots.items():
            if s > best and self.ids[i] != skip:
                best, best_id = s, self.ids[i]
        return min(1.0, best), best_id


def score(papers: list[dict], before: str, data_dir: str = DATA_DIR,
          past: Optional[list[dict]] = None) -> int:
    """
    Set paper["novelty"] (0..1) and paper["closest"] (the most similar past paper's ID)
    on each candidate. Returns how many papers were scored. Needs at least 50 past papers.
    """
    past = past if past is not None else history(before, data_dir)
    ids = {p.get("id") for p in papers}
    past = [r for r in past if r["id"] not in ids]
    if len(past) < 50:
        print(f"  [novelty] Only {len(past)} past papers saved; novelty is skipped today.")
        return 0
    index = Index(past)
    for p in papers:
        sim, other = index.closest(p, skip=p.get("id"))
        p["novelty"] = round(1 - sim, 3)
        p["closest"] = other
    print(f"  [novelty] Compared {len(papers)} papers with {index.n} from the last {HISTORY_DAYS} days.")
    return len(papers)
