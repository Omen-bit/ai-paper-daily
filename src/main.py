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
from renderer import render_digest, save_digest, render_category_page
from readme_updater import update_readme
from stats_tracker import update_stats, load_stats


CATEGORIES_DIR = os.path.join(ROOT_DIR, "categories")
TOP_N_PAPERS = 2  # Number of papers to feature per day


def update_category_pages(selected_papers: list[dict], all_existing_stats: dict) -> None:
    """
    Update category landing pages by appending today's papers.
    Loads existing paper data from stats to rebuild tables.
    """
    os.makedirs(CATEGORIES_DIR, exist_ok=True)

    # Collect papers per category (from today only - we rebuild incrementally)
    # For full category pages, we track paper data in a separate file per category
    for paper in selected_papers:
        for cat in paper.get("categories", []):
            slug = cat["slug"]
            cat_file = os.path.join(CATEGORIES_DIR, f"{slug}.md")

            # Load existing category page papers list (parse table rows)
            existing_papers = _load_category_papers(cat_file)

            # Add today's paper if not already there
            paper_ids = {p["id"] for p in existing_papers}
            if paper["id"] not in paper_ids:
                existing_papers.append(paper)

            # Render and save
            emoji, name = get_category_display(slug) or ("📄", slug.title())
            content = render_category_page(slug, emoji, name, existing_papers)
            with open(cat_file, "w", encoding="utf-8") as f:
                f.write(content)

    print(f"✅ Category pages updated in {CATEGORIES_DIR}")


def _load_category_papers(cat_file: str) -> list[dict]:
    """
    Parse existing papers from a category page table.
    Returns list of minimal paper dicts for reconstruction.
    """
    if not os.path.exists(cat_file):
        return []

    papers = []
    with open(cat_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Find table rows (skip header and separator)
    in_table = False
    for line in lines:
        line = line.strip()
        if line.startswith("| Date |"):
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and line.startswith("|") and line.endswith("|"):
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 3:
                # Parse: Date | Title (linked) | Authors | Links
                date = parts[0]

                # Extract URL and title from markdown link: [... title](url)
                import re
                link_match = re.search(r"\[(.+?)\]\((.+?)\)", parts[1])
                if link_match:
                    raw_title = link_match.group(1)
                    url = link_match.group(2)
                    # Remove badge emojis from title start
                    title = re.sub(r"^[\U0001F300-\U0001FFFF\u2600-\u26FF\u2700-\u27BF⭐🔥💡📖🔀\s]+", "", raw_title).strip()
                    arxiv_id = url.split("/abs/")[-1] if "/abs/" in url else ""

                    papers.append({
                        "id": arxiv_id,
                        "title": title,
                        "authors": [parts[2]] if len(parts) > 2 else [],
                        "abstract": "",
                        "url": url,
                        "pdf_url": url.replace("/abs/", "/pdf/"),
                        "submitted": date,
                        "categories": [],
                        "badges": [],
                        "source": "arXiv",
                    })
        elif in_table and not line.startswith("|"):
            in_table = False

    return papers


def run() -> None:
    """Main pipeline execution."""
    # Use IST (UTC+5:30) date so digest dates match local calendar days
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    date_str = datetime.now(ist_tz).strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"[AI Paper Daily] Running for {date_str}")
    print(f"{'='*60}\n")

    # --- Step 1: Fetch papers ---
    all_papers = fetch_all_papers(max_arxiv=150)

    if not all_papers:
        print("\n⚠️ No papers fetched today (arXiv may not have published yet - common on weekends).")
        print("💡 Creating a 'no digest today' placeholder...")
        _create_placeholder(date_str)
        return

    # --- Step 2: Classify ---
    print("\n🏷️ Classifying papers into categories...")
    all_papers = classify_papers(all_papers)

    # --- Step 3: Score and select top N ---
    print(f"\n⚡ Scoring {len(all_papers)} papers and selecting top {TOP_N_PAPERS}...")
    selected = score_and_rank_papers(all_papers, top_n=TOP_N_PAPERS)

    if not selected:
        print("❌ No papers selected after scoring.")
        sys.exit(1)

    # --- Step 4: Summarize with Groq ---
    selected = summarize_papers(selected)

    # --- Step 5: Update stats ---
    print("\n📊 Updating stats.json...")
    stats = update_stats(selected, date_str)

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
