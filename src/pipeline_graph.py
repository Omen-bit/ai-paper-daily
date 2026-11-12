"""
pipeline_graph.py
The daily pipeline as a LangGraph StateGraph. Each step is a node that reads
and writes one shared state, so every run can be traced step by step in
LangSmith (set LANGSMITH_TRACING=true and LANGSMITH_API_KEY).

  fetch -> classify -> choose_pool -> evidence -> shortlist -> judge -> pick -> notes -> save
    |                                                                    |
    +-- nothing fetched: stop                     nothing picked: stop --+

  fetch        new papers from arXiv and Hugging Face, minus the last 7 days' picks
  classify     research topics for each paper
  choose_pool  today's papers, or yesterday's with fresh upvotes (PICK_FROM, pick_pool.py)
  evidence     measured signals for the leading candidates: novelty against the last 90 days
               (novelty.py), GitHub / Hugging Face / Hacker News / Semantic Scholar
               (signals.py), and benchmark claims checked against the abstract (claims.py)
  shortlist    score every candidate out of 100 (scorer.py) and keep the best few
  judge        only when the leaders are within 3 points: the LLM compares them two at a
               time (judge.py) to break the tie; skipped without a key
  pick         today's pick (the best score, or the tie-break winner) plus Trending
  notes        Curator notes and "Why it matters" lines; a failure keeps the picks
  save         every candidate to data/daily/<date>.json

Every step that calls a model can fail without stopping the edition.
"""
import os
from typing import Callable, Optional, TypedDict

from langgraph.graph import END, START, StateGraph


class DailyState(TypedDict, total=False):
    date: str
    recent_ids: set
    papers: list          # this morning's papers, saved for the site and tomorrow
    pool: list            # the papers the picks come from
    pool_source: str      # "today" or the date the pool was saved
    shortlist: list
    tied: list            # the leaders within scorer.TIE_MARGIN points, sent to the judge
    verdict: Optional[dict]
    selected: list
    status: str           # "ok", "no_papers" or "no_selection"


def default_deps() -> dict:
    """The real pipeline functions. Tests pass their own."""
    from fetcher import fetch_all_papers, fetch_hf_papers_for_date
    from classifier import classify_papers
    from groq_summarizer import summarize_papers
    from curator import curate_papers
    import judge
    import paper_store
    import signals
    import novelty
    import claims
    return {
        "recent_featured": paper_store.recent_featured,
        "fetch_all_papers": fetch_all_papers,
        "fetch_hf_papers_for_date": fetch_hf_papers_for_date,
        "classify_papers": classify_papers,
        "judge_enabled": judge.enabled,
        "judge": judge.judge,
        "curate_papers": curate_papers,
        "summarize_papers": summarize_papers,
        "save_day": paper_store.save_day,
        "data_dir": paper_store.DATA_DIR,
        "shortlist_size": judge.SHORTLIST,
        "score_novelty": novelty.score,
        "collect_signals": signals.collect,
        "extract_claims": claims.extract,
        "claims_size": int(os.environ.get("CLAIMS_SHORTLIST") or 8),
    }


def build_graph(deps: Optional[dict] = None):
    """The compiled graph. Call .invoke({"date": "YYYY-MM-DD"})."""
    d = {**default_deps(), **(deps or {})}
    import pick_pool
    import scorer

    def fetch(state: DailyState) -> dict:
        try:
            recent = d["recent_featured"](7)
        except Exception as exc:  # a damaged history file only means a pick could repeat
            print(f"::warning::Could not read recent picks, repeats are possible today: {exc}")
            recent = set()
        papers = d["fetch_all_papers"]()
        if not papers:
            print("\n⚠️ No papers fetched today (arXiv may not have published yet - common on weekends).")
            return {"recent_ids": recent, "papers": [], "status": "no_papers"}
        fresh = [p for p in papers if p["id"] not in recent]
        if fresh:
            print(f"  [pipeline] {len(fresh)} fresh (unfeatured in last 7 days) candidate papers available.")
            papers = fresh
        else:
            print("  [pipeline] Notice: All fetched papers were recently featured; keeping entire candidate pool.")
        return {"recent_ids": recent, "papers": papers, "status": "ok"}

    def classify(state: DailyState) -> dict:
        print("\n🏷️ Classifying papers into categories...")
        return {"papers": d["classify_papers"](state["papers"])}

    def choose_pool(state: DailyState) -> dict:
        pool, source = pick_pool.candidates(state["date"], state["papers"], state["recent_ids"],
                                            data_dir=d["data_dir"], fetch_for_date=d["fetch_hf_papers_for_date"])
        if source != "today":
            # Today's papers still need scores: they are saved, best first, for tomorrow's pick
            scorer.score_all(state["papers"])
        return {"pool": pool, "pool_source": source}

    def evidence(state: DailyState) -> dict:
        # Each source is optional: a failure leaves its signals unknown and the run goes on
        pool = state["pool"]
        print(f"\n🔎 Gathering evidence for {len(pool)} candidates...")
        try:
            d["score_novelty"](pool, state["date"], data_dir=d["data_dir"])
        except Exception as exc:
            print(f"::warning::Novelty failed, ranking without it: {exc}")
        ranked = scorer.score_all(pool)  # first pass: who is worth looking up
        try:
            d["collect_signals"](ranked, state["date"], data_dir=d["data_dir"])
        except Exception as exc:
            print(f"::warning::Signals failed, ranking on the feeds alone: {exc}")
        ranked = scorer.score_all(pool)  # second pass: who is worth reading for claims
        try:
            d["extract_claims"](ranked[:d["claims_size"]])
        except Exception as exc:
            print(f"::warning::Claims failed, ranking without them: {exc}")
        return {"pool": pool}

    def shortlist(state: DailyState) -> dict:
        print(f"\n⚡ Scoring {len(state['pool'])} papers out of 100: today's pick plus the trending paper...")
        ranked = scorer.score_all(state["pool"])
        top = ranked[:d["shortlist_size"]]
        for p in top:
            print(f"  [score] {p['score']:>3} {p['title'][:60]} {p['score_parts']}")
        return {"shortlist": top, "tied": scorer.tied_with_leader(top)}

    def judge_node(state: DailyState) -> dict:
        tied = state.get("tied") or []
        if len(tied) < 2:
            print("  [judge] The leader is clear by more than "
                  f"{scorer.TIE_MARGIN} points; no tie to break.")
            return {"verdict": None}
        if not d["judge_enabled"]():
            print("  [judge] Off (no GROQ_API_KEY, or PICK_JUDGE=off); the best score is the pick.")
            return {"verdict": None}
        print(f"\n⚖️ Breaking a tie between the top {len(tied)} papers, two at a time...")
        return {"verdict": d["judge"](tied, seed=state["date"])}

    def pick(state: DailyState) -> dict:
        verdict = state.get("verdict")
        selected = scorer.select_daily(state["pool"], prefer=verdict["winner"] if verdict else None)
        if not selected:
            print("❌ No papers selected after scoring.")
            return {"selected": [], "status": "no_selection"}
        if verdict:
            selected[0]["judge"] = {"wins": verdict["wins"][verdict["winner"]],
                                    "of": len(state.get("tied") or state["shortlist"]) - 1,
                                    "reason": verdict["reason"], "tie_break": True}
        return {"selected": selected}

    def notes(state: DailyState) -> dict:
        # Notes are a bonus: if Groq or the notes code fails outright, the edition still
        # goes out with the picks and their abstracts rather than not at all
        selected = state["selected"]
        try:
            selected = d["curate_papers"](selected)
        except Exception as exc:
            print(f"::warning::Curator notes failed, publishing the picks without them: {exc}")
        try:
            selected = d["summarize_papers"](selected)
        except Exception as exc:
            print(f"::warning::'Why it matters' summaries failed, publishing without them: {exc}")
        return {"selected": selected}

    def save(state: DailyState) -> dict:
        d["save_day"](state["papers"], state["selected"], state["date"])
        return {}

    def after(step_ok: str, stop_status: str) -> Callable[[DailyState], str]:
        return lambda state: END if state.get("status") == stop_status else step_ok

    g = StateGraph(DailyState)
    for name, fn in [("fetch", fetch), ("classify", classify), ("choose_pool", choose_pool),
                     ("evidence", evidence), ("shortlist", shortlist), ("judge", judge_node), ("pick", pick),
                     ("notes", notes), ("save", save)]:
        g.add_node(name, fn)
    g.add_edge(START, "fetch")
    g.add_conditional_edges("fetch", after("classify", "no_papers"), ["classify", END])
    g.add_edge("classify", "choose_pool")
    g.add_edge("choose_pool", "evidence")
    g.add_edge("evidence", "shortlist")
    g.add_edge("shortlist", "judge")
    g.add_edge("judge", "pick")
    g.add_conditional_edges("pick", after("notes", "no_selection"), ["notes", END])
    g.add_edge("notes", "save")
    g.add_edge("save", END)
    return g.compile()


def run_day(date_str: str, deps: Optional[dict] = None) -> DailyState:
    """One edition. Returns the final state; its "status" says whether anything was saved."""
    graph = build_graph(deps)
    return graph.invoke({"date": date_str, "status": "ok"},
                        config={"run_name": f"daily-edition-{date_str}", "tags": ["daily-edition"]})
