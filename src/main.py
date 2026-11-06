"""
main.py
The daily pipeline, run as a LangGraph graph (pipeline_graph.py):
  1. Fetch new papers from arXiv and Hugging Face Daily Papers
  2. Classify them into research topics
  3. Choose the pool: today's papers, or yesterday's when PICK_FROM=yesterday (pick_pool.py)
  4. Score them and shortlist the best few
  5. The LLM judge compares the shortlist two at a time (judge.py; PICK_JUDGE=off skips it)
  6. Pick today's paper plus the trending one
  7. Write the notes for the picks with Groq
  8. Save every candidate to data/daily/<date>.json, which the website is built from
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

from pipeline_graph import run_day


def run() -> None:
    """Main pipeline execution."""
    # Use IST (UTC+5:30) so edition dates match the local calendar day
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    date_str = datetime.now(ist_tz).strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"[AI Paper Daily] Running for {date_str}")
    print(f"{'='*60}\n")

    state = run_day(date_str)
    if state.get("status") == "no_papers":
        return
    if state.get("status") == "no_selection":
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"[DONE] Edition for {date_str} is ready: {len(state['selected'])} picks "
          f"from {len(state['pool'])} candidates ({state.get('pool_source', 'today')}).")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run()
