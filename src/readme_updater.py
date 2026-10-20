"""
readme_updater.py
Dynamically updates README.md with the latest digest info, archive table, and stats.
Uses HTML comment markers to identify and replace specific sections.
"""

import os
import re
from datetime import datetime
try:
    from .stats_tracker import get_top_categories, get_recent_digests
    from .classifier import get_category_display
except (ImportError, ValueError):
    from stats_tracker import get_top_categories, get_recent_digests
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
    """Render the 'Today's Papers' section for README with a sleek, card-like format."""
    weekday = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %B %d, %Y")
    digest_link = f"digests/{date_str}.md"

    lines = [
        f"### 📅 Today's Featured Papers — [{weekday}]({digest_link})",
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

        # Build clean chips
        chips = []
        for b in badges[:2]:
            chips.append(f"`{b[0]} {b[1]}`")
        for c in categories[:2]:
            chips.append(f"`{c['emoji']} {c['name']}`")
        if hf_upvotes > 0:
            chips.append(f"`🔥 {hf_upvotes} upvotes`")
        chips_str = " ".join(chips)

        # Authors string (first 3 + et al.)
        if authors:
            auth_str = ", ".join(authors[:3])
            if len(authors) > 3:
                auth_str += " et al."
        else:
            auth_str = "Various Authors"

        hf_link = f"https://huggingface.co/papers/{arxiv_id}" if arxiv_id else None
        links_list = [f"[📄 arXiv Paper]({url})", f"[📥 Direct PDF]({pdf_url})"]
        if hf_link:
            links_list.append(f"[🤗 Community Discussion]({hf_link})")
        links_str = " &nbsp;•&nbsp; ".join(links_list)

        lines.append(f"#### {i}. [{title}]({url})")
        if chips_str:
            lines.append(f"{chips_str}\n")
        if why:
            lines.append(f"> 💡 **Why It Matters:**  \n> {why}\n")
        lines.append(f"👥 **Authors:** {auth_str}  ")
        lines.append(f"🔗 **Links:** {links_str}  \n")

    lines.append(f"👉 **[Read the Full Markdown Digest with Abstracts →]({digest_link})**")
    return "\n".join(lines)


def _render_archive_section(recent_digests: list[dict]) -> str:
    """Render the archive table in a compact, scannable format."""
    lines = [
        "### 📁 Digest Archive",
        "",
        "| Date | Papers | Top Category Covered | Digest Link |",
        "| :--- | :---: | :--- | :--- |",
    ]

    for entry in recent_digests[:15]:
        date = entry.get("date", "")
        count = entry.get("paper_count", 0)
        top_cat = entry.get("top_category", "—")
        link = f"[📄 Read Digest →](digests/{date}.md)"
        lines.append(f"| **{date}** | `{count}` | {top_cat} | {link} |")

    if not recent_digests:
        lines.append("| — | — | — | *No digests archived yet* |")

    if len(recent_digests) > 15:
        lines.append("\n<details><summary><b>View Older Digests</b></summary>\n")
        lines.append("| Date | Papers | Top Category Covered | Digest Link |")
        lines.append("| :--- | :---: | :--- | :--- |")
        for entry in recent_digests[15:50]:
            date = entry.get("date", "")
            count = entry.get("paper_count", 0)
            top_cat = entry.get("top_category", "—")
            link = f"[📄 Read Digest →](digests/{date}.md)"
            lines.append(f"| **{date}** | `{count}` | {top_cat} | {link} |")
        lines.append("\n</details>")

    return "\n".join(lines)


def _render_stats_section(stats: dict) -> str:
    """Render the stats summary section cleanly."""
    total_papers = stats.get("total_papers", 0)
    total_digests = stats.get("total_digests", 0)
    first_digest = stats.get("first_digest", "—")
    last_updated = stats.get("last_updated", "—")
    if last_updated and last_updated != "—":
        try:
            last_updated = last_updated[:10]
        except Exception:
            pass

    top_cats = get_top_categories(stats, top_n=5)

    lines = [
        "### 📊 Project Insights",
        "",
        "| Metric | Value |",
        "| :--- | :--- |",
        f"| 📄 **Total Research Papers Curated** | **{total_papers:,}** |",
        f"| 📅 **Total Daily Editions Published** | **{total_digests:,}** |",
        f"| 🗓️ **Tracking Since** | `{first_digest}` |",
        f"| 🔄 **Last Pipeline Execution** | `{last_updated}` |",
        "",
        "**🏆 Most Active Research Categories:**",
        "",
    ]

    for slug, count in top_cats:
        disp = get_category_display(slug)
        if disp:
            emoji, name = disp
            lines.append(f"- {emoji} **{name}**: `{count}` papers")
        else:
            lines.append(f"- **{slug}**: `{count}` papers")

    if not top_cats:
        lines.append("- *No data tracked yet*")

    return "\n".join(lines)


def update_readme(papers: list[dict], date_str: str, stats: dict) -> None:
    """Update all dynamic sections of README.md."""
    if not os.path.exists(README_PATH):
        print(f"⚠️ README.md not found at {README_PATH}")
        return

    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    recent_digests = get_recent_digests(stats)

    content = _replace_section(content, "today", _render_today_section(papers, date_str))
    content = _replace_section(content, "archive", _render_archive_section(recent_digests))
    content = _replace_section(content, "stats", _render_stats_section(stats))

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅ README.md updated successfully")
