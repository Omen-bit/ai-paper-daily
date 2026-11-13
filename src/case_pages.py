"""
case_pages.py
The Case studies pages: engineering write-ups from company blogs. Every card links out to the
company's own blog.

  case-studies/index.html     the finder: a search box and category chips, then a section per
                              topic, the write-ups with the most build details first. Search runs
                              in the browser (assets/case-finder.js) over an inline JSON index of
                              every write-up (search_index): keywords only, no LLM, no network
  case-studies/<topic>.html   every write-up on one topic, with the same search and filters

site_builder.build_site calls build_all with the posts from data/cases.json.
"""
import html
import json
import os
import shutil

import zlib

import case_logos
import making_of
from case_sources import (BY_NAME, BUILD_DETAILS, INDUSTRIES, TECHNIQUES, TOPICS as TOPIC_INFO, category_norm,
                          category_slug, clean_category, topic_of)

DIR = "case-studies"
ROOT = "../"
# Topic order on the filter chips: the LLM topics first, then the rest; categories the classifier
# proposed (CUSTOM, filled in by _clean) come after them
TOPICS = list(TOPIC_INFO)
SHORT = {k: name for k, (name, _) in TOPIC_INFO.items()}
MIN_CASES = 3  # a proposed category gets its own chip and page from this many write-ups; fewer stay under their closest topic
PALETTE = 8    # --l-x0 .. --l-x7 in style.css, for the proposed categories
CUSTOM: dict[str, tuple[str, str]] = {}  # key -> (name, about) of the proposed categories shown
PAGE_SIZE = 24
# New write-ups arrive every week (100+ a month), so the website keeps it focused:
# it shows the last 12 months, and the main page's search and filters cover the newest
# INDEX_FEED of them (each topic page still covers all of its own). Older posts stay in
# data/cases.json and in Supabase, so Scout still finds every one.
WINDOW_DAYS = 365
INDEX_FEED = 150
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "case_brands.json"), encoding="utf-8") as _f:
    BRAND_ICONS = json.load(_f)

EXT = ('<svg class="cs-ext" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
       'stroke-linejoin="round" aria-hidden="true"><path d="M15 3h6v6"/><path d="M10 14 21 3"/>'
       '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>')
BOOKMARK = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            'stroke-linejoin="round" aria-hidden="true"><path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/></svg>')
EXT_ARROW = ('<svg class="cs-ext" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
             'stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>')
PAPER_ICON = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
              'stroke-linejoin="round" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>'
              '<path d="M14 3v5h5M9 13h6M9 17h4"/></svg>')
TREND = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
         'stroke-linejoin="round" aria-hidden="true"><path d="M22 7 13.5 15.5 8.5 10.5 2 17"/><path d="M16 7h6v6"/></svg>')
SEARCH = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
          'aria-hidden="true"><circle cx="11" cy="11" r="7.5"/><path d="m20.5 20.5-4.2-4.2"/></svg>')
GOOGLE_G = ('<path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 '
            '2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55'
            'H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" '
            'd="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 '
            '2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 '
            '2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>')


def esc(text) -> str:
    return html.escape(str(text or ""), quote=True)


def problem_name(key: str) -> str:
    return (TOPIC_INFO.get(key) or CUSTOM.get(key) or ("Case study",))[0]


def topic_about(key: str) -> str:
    return (TOPIC_INFO.get(key) or CUSTOM.get(key) or ("", ""))[1]


def topic_keys() -> list[str]:
    """Every topic in chip order: the stable topics, then the proposed categories."""
    return TOPICS + [k for k in CUSTOM if k not in TOPIC_INFO]


def color(key: str) -> str:
    """The topic's colour: its own token for the stable topics, and for a proposed category one of the
    palette tokens picked from a hash of its name, so it keeps the same colour from build to build."""
    if key in TOPIC_INFO:
        return f"var(--l-{key})"
    return f"var(--l-x{zlib.crc32(category_norm(problem_name(key)).encode()) % PALETTE})"


def page_slug(key: str) -> str:
    return SLUGS.get(key) or key


def host(url: str) -> str:
    rest = (url or "").split("://", 1)[-1]
    return rest.split("/", 1)[0].removeprefix("www.")


def brand_hex(company: str) -> str:
    src = BY_NAME.get(company)
    return "#" + (src[4] if src else "5D5C63")


def _dark_brand(company: str) -> bool:
    """Black logos (Uber, Apple, GitHub) are drawn in the page's ink so they show in dark mode."""
    h = brand_hex(company).lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) < 40


def _slug(company: str) -> str:
    src = BY_NAME.get(company)
    return src[3] if src and src[3] in BRAND_ICONS else ""


def sprite(companies) -> str:
    """One hidden SVG holding each company's logo once; cards point at it with <use>."""
    out = []
    for company in sorted(set(companies)):
        slug = _slug(company)
        if not slug:
            continue
        if slug == "google":
            out.append(f'<symbol id="b-google" viewBox="0 0 48 48">{GOOGLE_G}</symbol>')
        elif slug == "meta":
            out.append('<linearGradient id="b-meta-g" x1="0" x2="1" y1="0" y2="0"><stop offset="0" stop-color="#0064E1"/>'
                       '<stop offset=".6" stop-color="#0073EE"/><stop offset="1" stop-color="#0082FB"/></linearGradient>'
                       f'<symbol id="b-meta" viewBox="0 0 24 24"><path fill="url(#b-meta-g)" d="{BRAND_ICONS["meta"]["path"]}"/></symbol>')
        elif slug == "spotify":
            out.append(f'<symbol id="b-spotify" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9.6" fill="#121212"/>'
                       f'<path fill="#1ED760" d="{BRAND_ICONS["spotify"]["path"]}"/></symbol>')
        elif BRAND_ICONS[slug].get("svg"):  # a full-colour logo
            out.append(f'<symbol id="b-{slug}" viewBox="{BRAND_ICONS[slug]["vb"]}">{BRAND_ICONS[slug]["svg"]}</symbol>')
        else:
            fill = "currentColor" if _dark_brand(company) else brand_hex(company)
            out.append(f'<symbol id="b-{slug}" viewBox="0 0 24 24"><path fill="{fill}" d="{BRAND_ICONS[slug]["path"]}"/></symbol>')
    if not out:
        return ""
    return f'<svg class="cs-sprite" aria-hidden="true" focusable="false"><defs>{"".join(out)}</defs></svg>'


LOGO_FILES: dict[str, str] = {}  # company -> saved icon file, filled in by build_all


def logo(company: str, cls: str = "") -> str:
    """The company's real logo from the sprite, or its initials on its brand colour when there is none."""
    slug = _slug(company)
    dark = " cs-ink" if _dark_brand(company) else ""
    if slug:
        return f'<svg class="{cls}{dark}" aria-hidden="true"><use href="#b-{slug}"/></svg>'
    if company in LOGO_FILES:  # the icon from the company's own website, saved by case_logos.py
        return f'<img class="{cls} cs-img" src="logos/{esc(LOGO_FILES[company])}" alt="" loading="lazy" decoding="async">'
    letters = (company[:1] or "?").upper()
    return f'<span class="{cls} cs-mono" style="--b:{brand_hex(company)}" aria-hidden="true">{esc(letters)}</span>'


# ---------- cards

def search_text(*parts) -> str:
    return esc(" ".join(str(p) for p in parts if p).lower())


def nice_date(day: str) -> str:
    try:
        y, m, d = (int(x) for x in day.split("-"))
        return f"{d} {MONTHS[m - 1]} {y}"
    except (ValueError, IndexError, AttributeError):
        return ""


def build_score(post: dict) -> int:
    """How many of the five build details the post describes; 0 when it is not tagged yet."""
    n = post.get("build_score")
    return max(0, min(len(BUILD_DETAILS), n)) if isinstance(n, int) and not isinstance(n, bool) else 0


def by_detail(posts: list[dict]) -> list[dict]:
    """The write-ups with the most build details first (untagged ones count as 0), then the newest."""
    return sorted(posts, key=lambda p: (build_score(p), p.get("published") or "", p.get("url", "")), reverse=True)


def detail_pill(post: dict) -> str:
    """The card's "Build details N/5" pill: green for 4-5, amber for 2-3, none below that."""
    n = build_score(post)
    if n < 2:
        return ""
    level = "hi" if n >= 4 else "mid"
    covered = ", ".join(k.replace("_", " ") for k in BUILD_DETAILS if (post.get("build_details") or {}).get(k))
    title = f' title="Describes: {esc(covered)}"' if covered else ""
    return f'<span class="cs-bd cs-bd-{level}"{title}>\u2713 Build details {n}/{len(BUILD_DETAILS)}</span>'


def post_card(post: dict, paper: tuple | None = None) -> str:
    """One write-up: brand cover with the company and topic, then our summary, tags and a link out.
    paper is (id, title) of a related paper from our library, or None."""
    problem, company = post["problem"], post["company"]
    tags = [t for t in post.get("tags") or [] if isinstance(t, str)][:3]
    summary = f'<p>{esc(post["summary"])}</p>' if post.get("summary") else ""
    if post.get("issue"):  # the problem in plain words, then how they solved it
        summary = (f'<p class="cs-issue"><b>Problem</b> {esc(post["issue"])}</p>'
                   + (f'<p class="cs-fix"><b>Solution</b> {esc(post["summary"])}</p>' if post.get("summary") else ""))
    if post.get("result"):
        summary += f'<p class="cs-result">{TREND}<span>{esc(post["result"])}</span></p>'
    tag_html = ("<ul class=\"cs-tags\" aria-label=\"Techniques\">" +
                "".join(f'<li><button type="button" data-cs-tag="{esc(t)}">{esc(t)}</button></li>' for t in tags) +
                "</ul>") if tags else ""
    rel = research_block(paper)
    date = nice_date(post.get("published", ""))
    when = f'<time datetime="{esc(post.get("published", ""))}">{date}</time>' if date else ""
    return f"""<li class="cs-card" style="--c:{color(problem)};--b:{brand_hex(company)}" data-cs-item data-p="{problem}" data-co="{esc(company)}" data-tags="|{esc("|".join(tags))}|" data-t="{search_text(post['title'], company, problem_name(problem), *tags, post.get('summary', ''), post.get('issue', ''), post.get('result', ''))}">
<div class="cs-cover">{logo(company, "cs-big")}<span class="cs-co">{logo(company, "cs-badge")}{esc(company)}</span>{when}<span class="cs-pills"><span class="cs-topic">{esc(problem_name(problem))}</span>{detail_pill(post)}</span></div>
<div class="cs-body"><h3><a class="cs-link" href="{esc(post['url'])}" rel="noopener" target="_blank">{esc(post['title'])}</a></h3>{summary}{tag_html}{rel}
<div class="cs-foot"><span class="cs-src">Read on {esc(host(post['url']))}{EXT}</span><button class="cs-save" type="button" data-cs-save="cs:{esc(post['url'])}" data-title="{esc(post['title'])}" data-url="{esc(post['url'])}" data-co="{esc(company)}" aria-pressed="false">{BOOKMARK}<span>Save</span></button></div></div></li>"""


# ---------- research behind a case (case_research.py matches them at build time, no LLM)

RESEARCH_LABEL = "Research behind this, on AI Papers Daily"


def research_block(paper: tuple | None) -> str:
    """The inset above the card's footer: the paper on this site behind the case, or nothing."""
    if not paper:
        return ""
    return (f'<a class="cs-rel" href="../paper/{esc(paper[0])}.html">{PAPER_ICON}<div><span>{RESEARCH_LABEL}</span>'
            f'<b>{esc(paper[1])}</b></div></a>')


# ---------- the page

def custom_categories(posts: list[dict], min_cases: int = MIN_CASES) -> dict[str, str]:
    """The proposed categories with at least min_cases write-ups: normal form -> page key.
    Names that differ only in case or plural are one category; the name used most is shown."""
    names: dict[str, dict[str, int]] = {}
    for p in posts:
        name = p.get("category")
        if isinstance(name, str) and name.strip():
            spelled = names.setdefault(category_norm(name), {})
            spelled[name.strip()] = spelled.get(name.strip(), 0) + 1
    out = {}
    taken = set(TOPIC_INFO) | set(SLUGS.values())
    for norm, spelled in sorted(names.items(), key=lambda kv: (-sum(kv[1].values()), kv[0])):
        if sum(spelled.values()) < min_cases:
            continue
        shown = clean_category(max(spelled.items(), key=lambda kv: (kv[1], kv[0]))[0]) or "Other"
        key = category_slug(shown) or "other"
        while key in taken:
            key += "-x"
        taken.add(key)
        CUSTOM[key] = (shown, f"Write-ups the classifier filed under {shown.lower()}.")
        out[norm] = key
    return out


def recent(posts: list[dict], days: int = WINDOW_DAYS) -> list[dict]:
    """The posts published within `days` of the newest one. Measured from the newest post, not
    today, so a quiet spell never empties the pages."""
    import datetime
    dates = [p.get("published") or "" for p in posts if p.get("published")]
    if not dates:
        return posts
    try:
        cutoff = (datetime.date.fromisoformat(max(dates)[:10]) - datetime.timedelta(days=days)).isoformat()
    except ValueError:
        return posts
    return [p for p in posts if (p.get("published") or max(dates))[:10] >= cutoff]


def _clean(posts: list[dict]) -> list[dict]:
    good = []
    for p in posts:
        try:
            topic = topic_of(p)  # posts saved under the old problems move onto today's topics
            if topic and p.get("url", "").startswith("https://") and p.get("title") and p.get("company"):
                good.append({**p, "problem": topic})
        except (KeyError, TypeError, AttributeError):
            continue
    CUSTOM.clear()
    active = custom_categories(good)
    for p in good:  # a proposed category with enough write-ups becomes the post's topic; the rest stay under the closest topic
        name = p.get("category")
        if isinstance(name, str) and category_norm(name) in active:
            p["problem"] = active[category_norm(name)]
    return sorted(good, key=lambda p: (p.get("published") or "", p["url"]), reverse=True)


SLUGS = {"rag": "rag", "agents": "agents", "coding": "coding-agents", "data": "data-agents", "ops": "ops-agents",
         "support": "customer-support", "platforms": "agent-platforms", "evals": "evaluation", "cost": "cost-and-speed", "tuning": "fine-tuning",
         "safety": "guardrails", "llm": "llm-products", "recs": "recommendations", "ads": "ads",
         "predict": "forecasting", "vision": "vision"}
PER_SECTION = 3  # cards per topic on the main page
NEWEST = 4  # newest write-ups at the top of the main page


CHEVRON = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
           'stroke-linejoin="round" aria-hidden="true"><path d="{d}"/></svg>')


def chip_row(chips: list[str]) -> str:
    """The topic chips in one row that scrolls sideways. app.js fades the edge that has more chips
    behind it and shows the arrow buttons (on screens with a mouse) that scroll the row; on touch
    screens the row is swiped. Without JavaScript the right edge fades and the row still scrolls.
    The arrows are left out of the tab order: every chip is a link the keyboard reaches anyway."""
    arrow = ('<button class="cs-chip-arrow cs-chip-{side}" type="button" tabindex="-1" aria-hidden="true" '
             'data-cs-chip-{side} hidden>' + CHEVRON + '</button>')
    return (f'<div class="cs-chipbar" data-cs-chipbar>{arrow.format(side="prev", d="m15 18-6-6 6-6")}'
            f'<nav class="cs-chips" aria-label="Topics" data-cs-chips>{"".join(chips)}</nav>'
            f'{arrow.format(side="next", d="m9 18 6-6-6-6")}</div>')


def filters(all_posts: list[dict], posts: list[dict], current: str = "") -> str:
    """Topic links (every topic with write-ups), search and the company menu for these posts."""
    per_topic = {k: sum(1 for p in all_posts if p["problem"] == k) for k in topic_keys()}
    here = ' aria-current="page"'
    chips = [f'<a href="index.html"{here if not current else ""}>All <span>{len(all_posts)}</span></a>']
    chips += [f'<a href="{page_slug(k)}.html" style="--c:{color(k)}"{here if k == current else ""}>'
              f'<i aria-hidden="true"></i>{esc(problem_name(k))} <span>{n}</span></a>'
              for k, n in per_topic.items() if n]
    per_co: dict[str, int] = {}
    for p in posts:
        per_co[p["company"]] = per_co.get(p["company"], 0) + 1
    options = "".join(f'<option value="{esc(c)}">{esc(c)} ({n})</option>' for c, n in sorted(per_co.items(), key=lambda kv: kv[0].lower()))
    label = "Search write-ups" if not current else f"Search {problem_name(current)} write-ups"
    return f"""{chip_row(chips)}
<div class="cs-tools">
<div class="cs-find"><label class="sr-only" for="cs-q">{esc(label)}</label><div class="cs-search">{SEARCH}<input id="cs-q" type="search" placeholder="{esc(label)}" autocomplete="off" data-cs-q></div></div>
<label class="cs-sel" for="cs-co"><span class="sr-only">Company</span><select id="cs-co" data-cs-company><option value="">All companies</option>{options}</select></label>
</div>"""


# Tags that only repeat the topic's own name, left out of that topic's "How they built it" row
SAME_AS_TOPIC = {"rag": {"RAG"}, "agents": {"Agents"}, "coding": {"Agents", "Code"}, "data": {"Agents"},
                 "ops": {"Agents"}, "support": {"Agents"}, "platforms": {"Agents"}, "evals": {"Evals"}, "cost": {"Cost"},
                 "tuning": {"Fine-tuning"}, "safety": {"Guardrails"}, "llm": {"LLMs"}, "recs": {"Personalisation"}}
MAX_APPROACHES = 12
SHOWN_APPROACHES = 6  # the rest sit behind "More"


def approaches(posts: list[dict], topic: str) -> str:
    """The techniques used across these write-ups, most used first, as tag filters."""
    count: dict[str, int] = {}
    for p in posts:
        for t in (p.get("tags") or [])[:3]:
            if isinstance(t, str) and t not in SAME_AS_TOPIC.get(topic, set()):
                count[t] = count.get(t, 0) + 1
    top = sorted(count.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_APPROACHES]
    if len(top) < 2:
        return ""
    buttons = "".join(f'<button type="button" data-cs-tag="{esc(t)}" aria-pressed="false"'
                      f'{" data-cs-ap-extra hidden" if i >= SHOWN_APPROACHES else ""}>{esc(t)} <span>{n}</span></button>'
                      for i, (t, n) in enumerate(top))
    more = (f'<button class="cs-ap-more" type="button" data-cs-ap-more>{len(top) - SHOWN_APPROACHES} more</button>'
            if len(top) > SHOWN_APPROACHES else "")
    return f'<div class="cs-ap" role="group" aria-label="Filter by how they built it"><p>Approach</p><div>{buttons}{more}</div></div>'


def status(n: int, hidden: bool = False) -> str:
    return (f'<div class="cs-status" data-cs-status{" hidden" if hidden else ""}><p data-cs-count aria-live="polite">{n} write-up{"" if n == 1 else "s"}</p>'
            '<p class="cs-active" data-cs-active hidden>Tag: <b data-cs-active-name></b> <button type="button" data-cs-clear-tag>Clear tag</button></p></div>')


NONE = ('<div class="cs-none" data-cs-none hidden><p>No write-ups match these filters.</p>'
        '<button class="cs-more" type="button" data-cs-reset>Clear all filters</button></div>')


# ---------- the finder on the main page

SUBLINE = ("Browse real engineering write-ups by category, or describe what you\u2019re building to find the "
           "closest ones. Every card opens the original post.")
HERO = ('<section class="cs-top cf-hero"><p class="cf-eyebrow">Case studies</p><h1>How companies build AI</h1>'
        f'<p>{SUBLINE}</p>')
PLACEHOLDER = "Describe your problem, e.g. HR policy chatbot with role-based access"
TRY = ["Policy Q&A bot", "Support chatbot with handoff", "Evaluate a RAG bot", "Cut LLM costs", "Coding agent in CI"]
# One plain-English line per topic for its section heading; proposed categories use their own description
BLURBS = {
    "rag": "Bots and search boxes that answer from a company\u2019s own documents.",
    "agents": "AI that takes actions with tools, not just answers.",
    "coding": "AI that writes, reviews and tests code.",
    "data": "Ask a question in plain words, get an answer from the company\u2019s data.",
    "ops": "AI that watches production and helps fix incidents.",
    "support": "Bots and assistants that help customers and support teams.",
    "platforms": "The plumbing for running many agents safely.",
    "evals": "How teams test whether answers are right.",
    "cost": "Making AI cheaper and faster to run.",
    "tuning": "Teaching a model a company\u2019s own data and style.",
    "safety": "Stopping leaks, prompt attacks and unsafe answers.",
    "llm": "Products built on top of a large language model.",
    "recs": "Picking what each person sees next.",
    "ads": "Choosing and pricing the ads people see.",
    "predict": "Predicting demand, prices, arrival times and fraud.",
    "vision": "Understanding and editing images and video.",
}
TECH_LABELS = {"rag": "RAG", "fine-tuning": "Fine-tuning", "embeddings": "Embeddings", "agents": "Agents and tools",
               "distillation": "Distillation", "classical-ml": "Classical ML", "prompt-engineering": "Prompt engineering",
               "evaluation-harness": "Eval harness", "guardrails": "Guardrails", "llm-routing": "LLM routing",
               "quantization": "Quantization", "caching": "Caching", "other": "Other"}
INDUSTRY_LABELS = {"fintech": "Fintech", "e-commerce": "E-commerce", "travel": "Travel", "media": "Media",
                   "healthcare": "Healthcare", "developer-tools": "Developer tools", "saas": "SaaS",
                   "marketplace": "Marketplace", "social": "Social", "logistics": "Logistics", "other": "Other"}
CHEVRON_DOWN = CHEVRON.format(d="m6 9 6 6 6-6")


def blurb(key: str) -> str:
    return BLURBS.get(key) or topic_about(key)


def _techniques(post: dict) -> list[str]:
    return [t for t in post.get("techniques") or [] if t in TECHNIQUES]


def _industry(post: dict) -> str:
    return post.get("industry") if post.get("industry") in INDUSTRIES else ""


def _select(name: str, label: str, counts: dict[str, int], labels: dict[str, str]) -> str:
    """A filter menu with the values these write-ups use, most used first; "" when none do."""
    if not counts:
        return ""
    opts = "".join(f'<option value="{esc(v)}">{esc(labels.get(v, v))} ({n})</option>'
                   for v, n in sorted(counts.items(), key=lambda kv: (kv[0] == "other", -kv[1], labels.get(kv[0], kv[0]).lower())))
    return (f'<label class="cf-sel"><span class="sr-only">{esc(label)}</span><select data-cf-{name}>'
            f'<option value="">{esc(label)}: any</option>{opts}</select></label>')


def finder_tools(posts: list[dict]) -> str:
    """The search box, the "Try" examples and the filter menus."""
    tech: dict[str, int] = {}
    ind: dict[str, int] = {}
    cos: dict[str, int] = {}
    for p in posts:
        for t in _techniques(p):
            tech[t] = tech.get(t, 0) + 1
        if _industry(p):
            ind[_industry(p)] = ind.get(_industry(p), 0) + 1
        cos[p["company"]] = cos.get(p["company"], 0) + 1
    co_menu = (f'<label class="cf-sel"><span class="sr-only">Company</span><select data-cf-co><option value="">Company: any</option>'
               + "".join(f'<option value="{esc(c)}">{esc(c)} ({n})</option>' for c, n in sorted(cos.items(), key=lambda kv: kv[0].lower()))
               + "</select></label>")
    tries = "".join(f'<button type="button" data-cf-try="{esc(t)}">{esc(t)}</button>' for t in TRY)
    return f"""<form class="cf-form" role="search" data-cf-form>
<label class="sr-only" for="cf-q">Describe what you are building</label>
<div class="cf-box">{SEARCH}<input id="cf-q" name="q" type="search" placeholder="{esc(PLACEHOLDER)}" autocomplete="off" enterkeyhint="search" data-cf-q></div>
<button class="cf-go" type="submit">Find write-ups</button>
</form>
<div class="cf-try" role="group" aria-label="Example searches"><span>Try</span>{tries}</div>
<div class="cf-filters">{_select("tech", "Technique", tech, TECH_LABELS)}{_select("ind", "Industry", ind, INDUSTRY_LABELS)}{co_menu}
<label class="cf-toggle"><input type="checkbox" data-cf-first checked><span>Build details first</span></label></div>"""


def category_chips(posts: list[dict], counts: dict[str, int]) -> str:
    """One chip per topic with write-ups, biggest first; a chip filters the page to its topic."""
    chips = "".join(f'<button type="button" style="--c:{color(k)}" data-cf-topic="{esc(k)}" aria-pressed="false">'
                    f'<i aria-hidden="true"></i>{esc(problem_name(k))} <span>{n}</span></button>'
                    for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], problem_name(kv[0]))) if n)
    return (f'<section class="cf-browse" aria-labelledby="cf-browse-h"><h2 id="cf-browse-h">Browse by category</h2>'
            f'<div class="cf-chips" role="group" aria-label="Categories">{chips}</div></section>')


FINDER_RESULTS = ('<section class="cf-results" data-cf-results hidden aria-label="Matching write-ups">'
                  '<div class="cs-status"><p data-cf-status aria-live="polite"></p>'
                  '<button class="cf-clear" type="button" data-cf-clear>Clear</button></div>'
                  '<ul class="cs-grid cs-plain" data-cf-list></ul>'
                  '<div class="cs-none" data-cf-none hidden><p>No write-ups match yet. Try fewer words or pick a category above.</p></div>'
                  '<button class="cs-more" type="button" data-cf-more hidden>Show more write-ups</button></section>')


def search_index(posts: list[dict]) -> dict:
    """Everything case-finder.js needs to search and draw the cards: the write-ups (short keys,
    most build details first), topic names and colours, labels, and each company's logo markup."""
    ordered = by_detail(posts)
    rows = []
    for p in ordered:
        row = {"u": p["url"], "c": p["company"], "t": p["title"], "p": p["problem"], "d": p.get("published") or "",
               "i": p.get("issue") or "", "s": p.get("summary") or "", "r": p.get("result") or "",
               "g": [t for t in p.get("tags") or [] if isinstance(t, str)][:3], "x": _techniques(p),
               "n": _industry(p), "b": build_score(p)}
        if p.get("related_papers"):
            row["rp"] = [p["related_papers"][0]["id"], p["related_papers"][0]["title"]]
        covered = [k for k in BUILD_DETAILS if (p.get("build_details") or {}).get(k)]
        if covered:
            row["bd"] = covered
        rows.append(row)
    companies = sorted({p["company"] for p in posts})
    topics = sorted({p["problem"] for p in posts})
    return {"posts": rows,
            "topics": {k: [problem_name(k), color(k)] for k in topics},
            "labels": {"x": TECH_LABELS, "n": INDUSTRY_LABELS},
            "brands": {c: [logo(c, "cs-big"), logo(c, "cs-badge"), brand_hex(c)] for c in companies}}


def index_json(posts: list[dict]) -> str:
    """search_index as JSON that is safe inside a <script> tag."""
    text = json.dumps(search_index(posts), ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def build_all(posts: list[dict], papers: dict, page, write, site_dir: str, logo_dir: str = "",
              site_url: str = "", theme_script: str = "", head_extra: str = "", asset_v: str = "") -> list[str]:
    """Write the Case studies pages: the main page with a section per topic, and one page per topic.
    page is site_builder.page; logo_dir holds the icons case_logos.py saved. It also writes "How I built
    AI Papers Daily" (making_of.py), whose card leads the main page. Returns the paths for the sitemap."""
    posts = recent(_clean(posts))
    companies = {p["company"] for p in posts}
    LOGO_FILES.clear()
    for company in companies:
        name = case_logos.saved_file(company, logo_dir) if logo_dir and not _slug(company) else ""
        if name:
            os.makedirs(os.path.join(site_dir, DIR, "logos"), exist_ok=True)
            shutil.copyfile(os.path.join(logo_dir, name), os.path.join(site_dir, DIR, "logos", name))
            LOGO_FILES[company] = name
    # The paper behind each case, matched once here so the browser does nothing extra
    import case_research
    found = case_research.related(posts, papers, k=1, labels=TECH_LABELS) if papers else {}
    for p in posts:
        p["related_papers"] = [{k: m[k] for k in ("id", "title", "url", "score")} for m in found.get(p["url"], [])]
    desc = "How companies like Netflix, Meta and Spotify build AI into their products, from their own engineering blogs."
    sprite_all = sprite(companies)

    def card(p: dict, hidden: bool = False) -> str:
        rp = (p.get("related_papers") or [None])[0]
        html_ = post_card(p, (rp["id"], rp["title"]) if rp else None)
        return html_.replace("<li ", "<li hidden ", 1) if hidden else html_

    def feed(these: list[dict], cls: str = "") -> str:
        """Every post in a filterable list: the first PAGE_SIZE shown, the rest behind Show more."""
        more = (f'<button class="cs-more" type="button" data-cs-more="{PAGE_SIZE}">Show more write-ups</button>'
                if len(these) > PAGE_SIZE else "")
        items = "".join(card(p, i >= PAGE_SIZE) for i, p in enumerate(these))
        return f'<ul class="cs-grid{cls}" data-cs-list data-cs-paged="{PAGE_SIZE}">{items}</ul>{NONE}{more}'

    def wrap(inner: str, style: str = "") -> str:
        return f'{sprite_all}<div class="cs-wrap"{style}>{inner}</div>'

    # The main page: the finder (search box, category chips), then a section for each topic,
    # biggest first, each with the write-ups that show the most build details
    if posts:
        counts = {k: sum(1 for p in posts if p["problem"] == k) for k in topic_keys()}
        sections = []
        for k in sorted((k for k in topic_keys() if counts[k]), key=lambda t: (-counts[t], problem_name(t))):
            these = by_detail([p for p in posts if p["problem"] == k])
            sections.append(
                f'<section class="cs-sec cf-sec" id="{page_slug(k)}" style="--c:{color(k)}"><div class="cs-sec-head"><div>'
                f'<p class="cf-kicker"><i aria-hidden="true"></i>{esc(problem_name(k))}</p>'
                f'<h2>{esc(blurb(k))}</h2><p>Posts with real build details first.</p></div>'
                f'<a class="cs-see" href="{page_slug(k)}.html" data-cf-see="{esc(k)}">See all {len(these)}{EXT_ARROW}</a></div>'
                f'<ul class="cs-grid cs-plain">{"".join(card(p) for p in these[:PER_SECTION])}</ul></section>')
        # Our own write-up about building this site closes the page
        sections.append('<section class="cs-sec cf-sec"><div class="cs-sec-head"><div><p class="cf-kicker">Behind this site</p>'
                        '<h2>How these write-ups are found and sorted.</h2></div></div>'
                        f'<ul class="cs-grid cs-plain">{making_of.card()}</ul></section>')
        body = (f'{HERO}{finder_tools(posts)}</section>{category_chips(posts, counts)}'
                f'<div data-cf-sections>{"".join(sections)}</div>{FINDER_RESULTS}'
                f'<script type="application/json" id="cf-index">{index_json(posts)}</script>'
                f'<script src="../assets/case-finder.js{"?v=" + asset_v if asset_v else ""}" defer></script>')
    else:
        body = (f'{HERO}</section><div class="cs-empty"><p><b>No write-ups yet.</b> The first ones arrive with the '
                'next blog check, on Monday morning.</p></div>')
    write(os.path.join(site_dir, DIR, "index.html"),
          page("Case studies", wrap(body), root=ROOT, active="cases", path=f"{DIR}/index.html", description=desc))
    paths = [f"{DIR}/index.html"]
    paths += making_of.build(write, site_dir, site_url, posts, theme_script, head_extra)

    # One page per topic with write-ups
    for k in topic_keys():
        these = [p for p in posts if p["problem"] == k]
        if not these:
            continue
        name, about = problem_name(k), topic_about(k)
        body = (f'<p class="cs-crumb"><a href="index.html">Case studies</a> / {esc(name)}</p>'
                f'<section class="cs-top cs-topic-top"><h1>{esc(name)}</h1><p>{esc(about)}</p></section>'
                f'{filters(posts, these, k)}{approaches(these, k)}{status(len(these))}{feed(these)}')
        write(os.path.join(site_dir, DIR, f"{page_slug(k)}.html"),
              page(f"{name}: case studies", wrap(body, f' style="--c:{color(k)}"'), root=ROOT, active="cases",
                   path=f"{DIR}/{page_slug(k)}.html",
                   description=f"How companies handle {name.lower()} in production, from their own engineering blogs."))
        paths.append(f"{DIR}/{page_slug(k)}.html")
    return paths
