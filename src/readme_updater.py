"""
readme_updater.py
Dynamically updates README.md with the latest digest info, archive table, and stats.
Uses HTML comment markers to identify and replace specific sections.
Headings live OUTSIDE the sentinel markers in README.md.
The updater writes only content (no heading) between the markers.
"""

import os
import re
import sys
from datetime import datetime

try:
    from .stats_tracker import get_top_categories, get_recent_digests, scan_digests_folder
    from .classifier import get_category_display
except (ImportError, ValueError):
    from stats_tracker import get_top_categories, get_recent_digests, scan_digests_folder
    from classifier import get_category_display

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README_PATH = os.path.join(ROOT_DIR, "README.md")

# Marker pairs for dynamic sections
MARKERS = {
    "today": ("<!-- TODAY_START -->", "<!-- TODAY_END -->"),
    "archive": ("<!-- ARCHIVE_START -->", "<!-- ARCHIVE_END -->"),
    "stats": ("<!-- STATS_START -->", "<!-- STATS_END -->"),
}


def _replace_section(content: str, key: str, new_body: str) -> str:
    """
    Replace content between a pair of markers.
    Exits with a non-zero status and a clear message if either marker is missing.
    """
    start_marker, end_marker = MARKERS[key]
    if start_marker not in content:
        print(f"  [readme] ERROR: Start marker '{start_marker}' not found in README.md")
        sys.exit(1)
    if end_marker not in content:
        print(f"  [readme] ERROR: End marker '{end_marker}' not found in README.md")
        sys.exit(1)

    pattern = re.compile(
        rf"{re.escape(start_marker)}.*?{re.escape(end_marker)}",
        re.DOTALL,
    )
    replacement = f"{start_marker}\n{new_body}\n{end_marker}"
    updated, count = pattern.subn(replacement, content)
    if count == 0:
        print(f"  [readme] ERROR: Could not replace section '{key}' despite markers being present")
        sys.exit(1)
    return updated


def _render_today_section(papers: list[dict], date_str: str) -> str:
    """
    Render the 'Today's Papers' section content for README.
    Heading lives outside the markers in README.md, so no heading is written here.
    """
    weekday = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %B %d, %Y")
    digest_link = f"digests/{date_str}.md"

    lines = [
        f"### {weekday} · [{date_str}]({digest_link})",
        "",
    ]

    for i, paper in enumerate(papers, 1):
        title = paper.get("title", "Untitled")
        url = paper.get("url", "#")
        pdf_url = paper.get("pdf_url", "#")
        why = paper.get("why_it_matters", "")
        badges = paper.get("badges", [])
        categories = paper.get("categories", [])
        authors = paper.get("authors", [])
        arxiv_id = paper.get("id", "")
        hf_upvotes = paper.get("hf_upvotes", 0)

        chips = []
        for b in badges[:2]:
            chips.append(f"`{b[0]} {b[1]}`")
        for c in categories[:2]:
            chips.append(f"`{c['emoji']} {c['name']}`")
        if hf_upvotes > 0:
            chips.append(f"`{hf_upvotes} HF upvotes`")
        chips_str = " ".join(chips)

        if authors:
            auth_str = ", ".join(authors[:3])
            if len(authors) > 3:
                auth_str += " et al."
        else:
            auth_str = "Various Authors"

        hf_link = f"https://huggingface.co/papers/{arxiv_id}" if arxiv_id else None
        links_list = [f"[arXiv Paper]({url})", f"[Direct PDF]({pdf_url})"]
        if hf_link:
            links_list.append(f"[HF Community]({hf_link})")
        links_str = " &nbsp;|&nbsp; ".join(links_list)

        lines.append(f"#### {i}. [{title}]({url})")
        if chips_str:
            lines.append(chips_str)
            lines.append("")
        if why:
            source = paper.get("summary_source", "groq")
            label = "Abstract highlight" if source == "heuristic" else "Why It Matters"
            lines.append(f"> 💡 **{label}:**  ")
            lines.append(f"> {why}")
            lines.append("")
        lines.append(f"**Authors:** {auth_str}  ")
        lines.append(f"**Links:** {links_str}  ")
        lines.append("")

    lines.append(f"**[Read the full digest with abstracts]({digest_link})**")
    return "\n".join(lines)


def _build_archive_rows(stats: dict) -> list[dict]:
    """
    Build the archive row list from two sources of truth merged together:
    1. Scan digests/ on disk to know which dates exist.
    2. Use stats["digests"] log to get paper count and top category per date.
    Newest first. Placeholder days (no papers) are listed with a marker.
    """
    disk_entries = scan_digests_folder()  # [{"date": ..., "is_placeholder": bool}]
    stats_log = {d["date"]: d for d in stats.get("digests", [])}

    rows = []
    for entry in disk_entries:
        date = entry["date"]
        if entry["is_placeholder"]:
            rows.append({
                "date": date,
                "paper_count": 0,
                "top_category": "No papers",
                "is_placeholder": True,
            })
        else:
            log = stats_log.get(date, {})
            rows.append({
                "date": date,
                "paper_count": log.get("paper_count", "?"),
                "top_category": log.get("top_category", "Unknown"),
                "is_placeholder": False,
            })

    # Sort newest first (disk scan already does this, but be explicit)
    rows.sort(key=lambda x: x["date"], reverse=True)
    return rows


def _render_archive_section(stats: dict) -> str:
    """
    Render the archive table content. Heading lives outside the markers.
    Shows at most 30 rows; links to digests/ folder for the rest.
    """
    all_rows = _build_archive_rows(stats)

    lines = [
        "| Date | Papers | Top Category | Digest |",
        "| :--- | :---: | :--- | :--- |",
    ]

    shown = all_rows[:30]
    for row in shown:
        date = row["date"]
        count = row["paper_count"]
        top_cat = row["top_category"]
        if row.get("is_placeholder"):
            link = f"[{date}](digests/{date}.md)"
            lines.append(f"| {date} | `0` | *(no papers)* | {link} |")
        else:
            link = f"[Read digest](digests/{date}.md)"
            lines.append(f"| **{date}** | `{count}` | {top_cat} | {link} |")

    if not shown:
        lines.append("| -- | -- | -- | *No digests yet* |")

    if len(all_rows) > 30:
        lines.append(
            f"\n*Showing latest 30 of {len(all_rows)} digests. "
            f"[Browse all in digests/](digests/)*"
        )

    return "\n".join(lines)


def _render_stats_section(stats: dict) -> str:
    """Render the stats summary section content. Heading lives outside the markers."""
    total_papers = stats.get("total_papers", 0)
    total_digests = stats.get("total_digests", 0)
    first_digest = stats.get("first_digest", "unknown")
    last_updated = stats.get("last_updated", "unknown")
    if last_updated and last_updated != "unknown":
        try:
            last_updated = last_updated[:10]
        except Exception:
            pass

    top_cats = get_top_categories(stats, top_n=5)

    lines = [
        "| Metric | Value |",
        "| :--- | :--- |",
        f"| Papers curated | **{total_papers:,}** |",
        f"| Daily editions | **{total_digests:,}** |",
        f"| Tracking since | `{first_digest}` |",
        f"| Last run | `{last_updated}` |",
        "",
        "**Most active categories:**",
        "",
    ]

    for slug, count in top_cats:
        disp = get_category_display(slug)
        paper_word = "paper" if count == 1 else "papers"
        if disp:
            emoji, name = disp
            lines.append(f"- {emoji} **{name}**: `{count}` {paper_word}")
        else:
            lines.append(f"- **{slug}**: `{count}` {paper_word}")

    if not top_cats:
        lines.append("- *No data tracked yet*")

    return "\n".join(lines)


def update_readme(papers: list[dict], date_str: str, stats: dict) -> None:
    """Update all dynamic sections of README.md."""
    if not os.path.exists(README_PATH):
        print(f"  [readme] ERROR: README.md not found at {README_PATH}")
        sys.exit(1)

    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    content = _replace_section(content, "today", _render_today_section(papers, date_str))
    content = _replace_section(content, "archive", _render_archive_section(stats))
    content = _replace_section(content, "stats", _render_stats_section(stats))

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print("  [readme] README.md updated successfully")
