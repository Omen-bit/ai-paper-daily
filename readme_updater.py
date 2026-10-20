"""
readme_updater.py
Dynamically updates README.md with the latest digest info, archive table, and stats.
Uses HTML comment markers to identify and replace specific sections.
"""

import os
import re
from datetime import datetime
from stats_tracker import get_top_categories, get_recent_digests

README_PATH = os.path.join(os.path.dirname(__file__), "README.md")

# Marker pairs for dynamic sections
MARKERS = {
    "today": ("<!-- TODAY_START -->", "<!-- TODAY_END -->"),
    "archive": ("<!-- ARCHIVE_START -->", "<!-- ARCHIVE_END -->"),
    "stats": ("<!-- STATS_START -->", "<!-- STATS_END -->"),
}


def _replace_section(content: str, key: str, new_body: str) -> str:
    """Replace the content between a pair of markers."""
    start_marker, end_marker = MARKERS[key]
    pattern = re.compile(
        rf"{re.escape(start_marker)}.*?{re.escape(end_marker)}",
        re.DOTALL,
    )
    replacement = f"{start_marker}\n{new_body}\n{end_marker}"
    updated, count = pattern.subn(replacement, content)
    if count == 0:
        print(f"⚠️ Marker pair for '{key}' not found in README — skipping section update")
    return updated


def _render_today_section(papers: list[dict], date_str: str) -> str:
    """Render the 'Today's Papers' section for README."""
    weekday = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %B %d %Y")
    digest_link = f"digests/{date_str}.md"

    lines = [
        f"### 📅 Latest Digest — [{weekday}]({digest_link})",
        "",
    ]

    for i, paper in enumerate(papers, 1):
        title = paper.get("title", "Untitled")
        url = paper.get("url", "#")
        why = paper.get("why_it_matters", "")
        badges = paper.get("badges", [])
        categories = paper.get("categories", [])

        badge_str = " ".join([b[0] for b in badges])
        cat_str = " · ".join([f"{c['emoji']} {c['name']}" for c in categories[:2]])

        lines.append(f"**{i}. {badge_str} [{title}]({url})**  ")
        if cat_str:
            lines.append(f"*{cat_str}*  ")
        if why:
            lines.append(f"💡 _{why}_  ")
        lines.append("")

    lines.append(f"[📖 Read full digest →]({digest_link})")
    return "\n".join(lines)


def _render_archive_section(recent_digests: list[dict]) -> str:
    """Render the archive table."""
    lines = [
        "### 📁 Digest Archive",
        "",
        "| Date | Papers | Top Category | Link |",
        "|------|--------|--------------|------|",
    ]

    for entry in recent_digests[:30]:  # Show last 30
        date = entry.get("date", "")
        count = entry.get("paper_count", 0)
        top_cat = entry.get("top_category", "—")
        link = f"[📄 Read](digests/{date}.md)"
        lines.append(f"| {date} | {count} | {top_cat} | {link} |")

    if not recent_digests:
        lines.append("| — | — | — | *No digests yet* |")

    return "\n".join(lines)


def _render_stats_section(stats: dict) -> str:
    """Render the stats summary section."""
    total_papers = stats.get("total_papers", 0)
    total_digests = stats.get("total_digests", 0)
    first_digest = stats.get("first_digest", "—")
    last_updated = stats.get("last_updated", "—")
    if last_updated and last_updated != "—":
        try:
            last_updated = last_updated[:10]  # Just the date
        except Exception:
            pass

    top_cats = get_top_categories(stats, top_n=5)

    lines = [
        "### 📊 Project Stats",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| 📄 Total papers tracked | **{total_papers:,}** |",
        f"| 📅 Total daily digests | **{total_digests:,}** |",
        f"| 🗓️ Tracking since | **{first_digest}** |",
        f"| 🔄 Last updated | **{last_updated}** |",
        "",
        "**🏆 Top Categories (all time):**",
        "",
    ]

    for slug, count in top_cats:
        # Find emoji for slug
        from classifier import get_category_display
        disp = get_category_display(slug)
        if disp:
            emoji, name = disp
            lines.append(f"- {emoji} **{name}**: {count} papers")
        else:
            lines.append(f"- **{slug}**: {count} papers")

    if not top_cats:
        lines.append("- *No data yet*")

    return "\n".join(lines)


def update_readme(papers: list[dict], date_str: str, stats: dict) -> None:
    """Update all dynamic sections of README.md."""
    if not os.path.exists(README_PATH):
        print(f"⚠️ README.md not found at {README_PATH}")
        return

    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Update each section
    recent_digests = get_recent_digests(stats)

    content = _replace_section(content, "today", _render_today_section(papers, date_str))
    content = _replace_section(content, "archive", _render_archive_section(recent_digests))
    content = _replace_section(content, "stats", _render_stats_section(stats))

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅ README.md updated successfully")
