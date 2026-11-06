"""
main.py
The daily pipeline:
  1. Fetch new papers from arXiv and Hugging Face Daily Papers
  2. Classify them into research topics
  3. Score them and pick today's paper plus the trending one
     (from yesterday's candidates instead when PICK_FROM=yesterday, see pick_pool.py)
  4. Write the notes for the picks with Groq
  5. Save every candidate to data/daily/<date>.json, which the website is built from
"""
import sys, io
# Force UTF-8 output on Windows (avoids cp1252 emoji errors)
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os
import sys
from datetime import datetime, timezone, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Resolve project root & src paths
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SRC_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from fetcher import fetch_all_papers, fetch_hf_papers_for_date
from classifier import classify_papers
from scorer import score_paper, select_daily
import pick_pool
from groq_summarizer import summarize_papers
from curator import curate_papers
import paper_store


def run() -> None:
    """Main pipeline execution."""
    # Use IST (UTC+5:30) so edition dates match the local calendar day
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    date_str = datetime.now(ist_tz).strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"[AI Paper Daily] Running for {date_str}")
    print(f"{'='*60}\n")

    # Papers featured in the last week are not picked again
    try:
        recent_paper_ids = paper_store.recent_featured(7)
    except Exception as exc:  # a damaged history file only means a pick could repeat
        print(f"::warning::Could not read recent picks, repeats are possible today: {exc}")
        recent_paper_ids = set()

    # --- Step 1: Fetch papers ---
    all_papers = fetch_all_papers()

    if not all_papers:
        print("\n⚠️ No papers fetched today (arXiv may not have published yet - common on weekends).")
        return

    # Filter out recently featured papers to ensure fresh picks, especially on weekends
    fresh_papers = [p for p in all_papers if p["id"] not in recent_paper_ids]
    if fresh_papers:
        all_papers = fresh_papers
        print(f"  [pipeline] {len(all_papers)} fresh (unfeatured in last 7 days) candidate papers available.")
    else:
        print("  [pipeline] Notice: All fetched papers were recently featured; keeping entire candidate pool.")

    # --- Step 2: Classify ---
    print("\n🏷️ Classifying papers into categories...")
    all_papers = classify_papers(all_papers)

    # --- Step 3: Score and select top N ---
    pool, pool_source = pick_pool.candidates(date_str, all_papers, recent_paper_ids,
                                             fetch_for_date=fetch_hf_papers_for_date)
    if pool_source != "today":
        # Today's papers still need scores: they are saved, best first, for tomorrow's pick
        for p in all_papers:
            score_paper(p)
    print(f"\n⚡ Scoring {len(pool)} papers: today's pick plus the trending paper...")
    selected = select_daily(pool)

    if not selected:
        print("❌ No papers selected after scoring.")
        sys.exit(1)

    # --- Step 4: Curator notes, then "Why it matters" for any paper still missing it ---
    # Notes are a bonus: if Groq or the notes code fails outright, the edition still
    # goes out with the picks and their abstracts rather than not at all
    try:
        selected = curate_papers(selected)
    except Exception as exc:
        print(f"::warning::Curator notes failed, publishing the picks without them: {exc}")
    try:
        selected = summarize_papers(selected)
    except Exception as exc:
        print(f"::warning::'Why it matters' summaries failed, publishing without them: {exc}")

    # --- Step 5: Save every candidate for the website ---
    paper_store.save_day(all_papers, selected, date_str)

    print(f"\n{'='*60}")
    print(f"[DONE] Edition for {date_str} is ready: {len(selected)} picks from {len(all_papers)} papers.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run()
