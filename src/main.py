"""
main.py
The daily pipeline:
  1. Fetch new papers from arXiv and Hugging Face Daily Papers
  2. Classify them into research topics
  3. Score them and pick today's paper plus the trending one
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

from fetcher import fetch_all_papers
from classifier import classify_papers
from scorer import select_daily
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
    recent_paper_ids = paper_store.recent_featured(7)

    # --- Step 1: Fetch papers ---
    all_papers = fetch_all_papers(max_arxiv=150)

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
    print(f"\n⚡ Scoring {len(all_papers)} papers: today's pick plus the trending paper...")
    selected = select_daily(all_papers)

    if not selected:
        print("❌ No papers selected after scoring.")
        sys.exit(1)

    # --- Step 4: Curator notes, then "Why it matters" for any paper still missing it ---
    selected = curate_papers(selected)
    selected = summarize_papers(selected)

    # --- Step 5: Save every candidate for the website ---
    paper_store.save_day(all_papers, selected, date_str)

    print(f"\n{'='*60}")
    print(f"[DONE] Edition for {date_str} is ready: {len(selected)} picks from {len(all_papers)} papers.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run()
