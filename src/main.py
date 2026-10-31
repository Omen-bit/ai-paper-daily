"""
main.py
Orchestrates the full pipeline:
  1. Fetch papers from arXiv + HuggingFace
  2. Classify into categories
  3. Score and select top 2
  4. Generate "Why it matters" summaries via Groq
  5. Render daily digest markdown
  6. Update category pages
  7. Update README dashboard
  8. Update stats.json
  9. Save structured paper records to data/ (used by the website)
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
from classifier import classify_papers, get_all_category_slugs, get_category_display
from scorer import score_and_rank_papers
from groq_summarizer import summarize_papers
from curator import curate_papers
from renderer import render_digest, save_digest, render_category_page
from readme_updater import update_readme
from stats_tracker import update_stats, load_stats
import paper_store


CATEGORIES_DIR = os.path.join(ROOT_DIR, "categories")
TOP_N_PAPERS = 2  # Number of papers to feature per day


def update_category_pages(selected_papers: list[dict], all_existing_stats: dict) -> None:
    """
    Update category landing pages for all categories using stats as source of truth.
    Pre-seeds all 12 categories so no dashboard links return 404.
    """
    os.makedirs(CATEGORIES_DIR, exist_ok=True)
    all_slugs = get_all_category_slugs()

    # Map slug -> list of paper dicts
    papers_by_category: dict[str, list[dict]] = {slug: [] for slug in all_slugs}
    seen_ids_per_cat: dict[str, set[str]] = {slug: set() for slug in all_slugs}

    # 1. Gather all past papers from stats.json digests
    for digest in all_existing_stats.get("digests", []):
        for p in digest.get("papers", []):
            pid = p.get("id") or p.get("title")
            for cat in p.get("categories", []):
                slug = cat if isinstance(cat, str) else cat.get("slug")
                if slug in papers_by_category and pid not in seen_ids_per_cat[slug]:
                    seen_ids_per_cat[slug].add(pid)
                    papers_by_category[slug].append(p)

    # 2. Add today's selected papers
    for paper in selected_papers:
        pid = paper.get("id") or paper.get("title")
        for cat in paper.get("categories", []):
            slug = cat if isinstance(cat, str) else cat.get("slug")
            if slug in papers_by_category and pid not in seen_ids_per_cat[slug]:
                seen_ids_per_cat[slug].add(pid)
                papers_by_category[slug].append(paper)

    # 3. Render every category page
    for slug, cat_papers in papers_by_category.items():
        cat_file = os.path.join(CATEGORIES_DIR, f"{slug}.md")
        disp = get_category_display(slug)
        emoji, name = disp if disp else ("📄", slug.replace("-", " ").title())
        content = render_category_page(slug, emoji, name, cat_papers)
        with open(cat_file, "w", encoding="utf-8") as f:
            f.write(content)

    print(f"✅ All {len(all_slugs)} category pages updated/pre-seeded in {CATEGORIES_DIR}")


def run() -> None:
    """Main pipeline execution."""
    # Use IST (UTC+5:30) date so digest dates match local calendar days
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    date_str = datetime.now(ist_tz).strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"[AI Paper Daily] Running for {date_str}")
    print(f"{'='*60}\n")

    # Load stats to check recently featured paper IDs (prevent duplicates on weekend/lookback)
    current_stats = load_stats()
    paper_store.backfill_from_stats(current_stats)
    recent_paper_ids = set()
    for d in current_stats.get("digests", [])[:7]:
        for p in d.get("papers", []):
            if p.get("id"):
                recent_paper_ids.add(p["id"])

    # --- Step 1: Fetch papers ---
    all_papers = fetch_all_papers(max_arxiv=150)

    if not all_papers:
        print("\n⚠️ No papers fetched today (arXiv may not have published yet - common on weekends).")
        print("💡 Creating a 'no digest today' placeholder...")
        _create_placeholder(date_str)
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
    print(f"\n⚡ Scoring {len(all_papers)} papers and selecting top {TOP_N_PAPERS}...")
    selected = score_and_rank_papers(all_papers, top_n=TOP_N_PAPERS)

    if not selected:
        print("❌ No papers selected after scoring.")
        sys.exit(1)

    # --- Step 4: Curator notes, then "Why it matters" for any paper still missing it ---
    selected = curate_papers(selected)
    selected = summarize_papers(selected)

    # --- Step 5: Update stats ---
    print("\n📊 Updating stats.json...")
    stats = update_stats(selected, date_str)

    # Save every candidate as a structured record for the website
    paper_store.save_day(all_papers, selected, date_str)

    # --- Step 6: Render daily digest ---
    print("\n📝 Rendering daily digest...")
    digest_content = render_digest(selected, date_str, stats)
    save_digest(digest_content, date_str)

    # --- Step 7: Update category pages ---
    print("\n📁 Updating category pages...")
    update_category_pages(selected, stats)

    # --- Step 8: Update README dashboard ---
    print("\n🏠 Updating README.md dashboard...")
    update_readme(selected, date_str, stats)

    print(f"\n{'='*60}")
    print(f"[DONE] Digest for {date_str} is ready.")
    print(f"   Papers featured    : {len(selected)}")
    print(f"   Total papers tracked: {stats['total_papers']}")
    print(f"   Digest #           : {stats['total_digests']}")
    print(f"{'='*60}\n")


def _create_placeholder(date_str: str) -> None:
    """Create a minimal placeholder file for days with no arXiv submissions."""
    digests_dir = os.path.join(ROOT_DIR, "digests")
    os.makedirs(digests_dir, exist_ok=True)
    content = f"""# 🧠 AI Paper Daily - {date_str}

> ℹ️ **No new papers available today.**
> arXiv typically does not publish papers on weekends and holidays.
> Check back tomorrow for fresh research!

[⬅️ Back to README](../README.md)
"""
    filepath = os.path.join(digests_dir, f"{date_str}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"📄 Placeholder created: {filepath}")


if __name__ == "__main__":
    run()
