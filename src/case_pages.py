"""
case_pages.py
The Case studies pages: engineering write-ups from company blogs. Every card links out to the
company's own blog.

  case-studies/index.html     the newest write-ups, then a section per topic; search, company
                              or a tag switches to one list of every match
  case-studies/<topic>.html   every write-up on one topic, with the same search and filters

site_builder.build_site calls build_all with the posts from data/cases.json.
"""
import html
import json
import math
import os
import shutil

import case_logos
import making_of
from case_sources import BY_NAME, TOPICS as TOPIC_INFO, topic_of

DIR = "case-studies"
ROOT = "../"
# Topic order on the filter chips: the LLM topics first, then the rest
TOPICS = list(TOPIC_INFO)
SHORT = {k: name for k, (name, _) in TOPIC_INFO.items()}
PAGE_SIZE = 24
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
    return TOPIC_INFO[key][0]


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
    rel = (f'<a class="cs-rel" href="../paper/{esc(paper[0])}.html">{PAPER_ICON}<div><span>Related paper on AI Papers Daily</span>'
           f'<b>{esc(paper[1])}</b></div></a>' if paper else "")
    date = nice_date(post.get("published", ""))
    when = f'<time datetime="{esc(post.get("published", ""))}">{date}</time>' if date else ""
    return f"""<li class="cs-card" style="--c:var(--l-{problem});--b:{brand_hex(company)}" data-cs-item data-p="{problem}" data-co="{esc(company)}" data-tags="|{esc("|".join(tags))}|" data-t="{search_text(post['title'], company, problem_name(problem), *tags, post.get('summary', ''), post.get('issue', ''), post.get('result', ''))}">
<div class="cs-cover">{logo(company, "cs-big")}<span class="cs-co">{logo(company, "cs-badge")}{esc(company)}</span>{when}<span class="cs-topic">{esc(problem_name(problem))}</span></div>
<div class="cs-body"><h3><a class="cs-link" href="{esc(post['url'])}" rel="noopener" target="_blank">{esc(post['title'])}</a></h3>{summary}{tag_html}{rel}
<div class="cs-foot"><span class="cs-src">Read on {esc(host(post['url']))}{EXT}</span><button class="cs-save" type="button" data-cs-save="cs:{esc(post['url'])}" data-title="{esc(post['title'])}" data-url="{esc(post['url'])}" data-co="{esc(company)}" aria-pressed="false">{BOOKMARK}<span>Save</span></button></div></div></li>"""


# ---------- related papers

STOP = set("""a an and are as at be by for from has have in into is it its of on or our that the their this to via we with
which while using use used based new show shows can these than more over between both such also not only how what when
where who model models method methods paper approach results part scale scaling system systems production building
build engineering data learning machine""".split())


def _words(text: str) -> set[str]:
    words = "".join(ch if ch.isalnum() or ch == "-" else " " for ch in (text or "").lower()).split()
    return {w for w in words if len(w) > 3 and w not in STOP}


def related_papers(posts: list[dict], papers: dict, k: int = 2, min_score: float = 2.2) -> dict[str, list[str]]:
    """For each post, up to k papers from our library that share its rarer words."""
    index: dict[str, list[str]] = {}
    for pid, rec in papers.items():
        for w in _words(f"{rec.get('title', '')} {rec.get('abstract', '')[:600]}"):
            index.setdefault(w, []).append(pid)
    limit = max(25, len(papers) // 25)
    out = {}
    for post in posts:
        scores: dict[str, float] = {}
        for w in _words(f"{post['title']} {post.get('summary', '')}"):
            posting = index.get(w, [])
            if not posting or len(posting) > limit:
                continue
            weight = 1.0 / math.log(len(posting) + 1.5)
            for pid in posting:
                scores[pid] = scores.get(pid, 0.0) + weight
        best = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
        out[post["url"]] = [pid for pid, sc in best if sc >= min_score]
    return out


# ---------- the page

def _clean(posts: list[dict]) -> list[dict]:
    good = []
    for p in posts:
        try:
            topic = topic_of(p)  # posts saved under the old problems move onto today's topics
            if topic and p.get("url", "").startswith("https://") and p.get("title") and p.get("company"):
                good.append({**p, "problem": topic})
        except (KeyError, TypeError, AttributeError):
            continue
    return sorted(good, key=lambda p: (p.get("published") or "", p["url"]), reverse=True)


SLUGS = {"rag": "rag", "agents": "agents", "evals": "evaluation", "cost": "cost-and-speed", "tuning": "fine-tuning",
         "safety": "guardrails", "llm": "llm-products", "recs": "recommendations", "ads": "ads",
         "predict": "forecasting", "vision": "vision"}
PER_SECTION = 3  # cards per topic on the main page


def filters(all_posts: list[dict], posts: list[dict], current: str = "") -> str:
    """Topic links (every topic with write-ups), search and the company menu for these posts."""
    per_topic = {k: sum(1 for p in all_posts if p["problem"] == k) for k in TOPICS}
    here = ' aria-current="page"'
    chips = [f'<a href="index.html"{here if not current else ""}>All <span>{len(all_posts)}</span></a>']
    chips += [f'<a href="{SLUGS[k]}.html" style="--c:var(--l-{k})"{here if k == current else ""}>'
              f'<i aria-hidden="true"></i>{esc(SHORT[k])} <span>{n}</span></a>'
              for k, n in per_topic.items() if n]
    per_co: dict[str, int] = {}
    for p in posts:
        per_co[p["company"]] = per_co.get(p["company"], 0) + 1
    options = "".join(f'<option value="{esc(c)}">{esc(c)} ({n})</option>' for c, n in sorted(per_co.items(), key=lambda kv: kv[0].lower()))
    label = "Search write-ups" if not current else f"Search {SHORT[current]} write-ups"
    return f"""<nav class="cs-chips" aria-label="Topics">{"".join(chips)}</nav>
<div class="cs-tools">
<div class="cs-find"><label class="sr-only" for="cs-q">{esc(label)}</label><div class="cs-search">{SEARCH}<input id="cs-q" type="search" placeholder="{esc(label)}" autocomplete="off" data-cs-q></div></div>
<label class="cs-sel" for="cs-co"><span class="sr-only">Company</span><select id="cs-co" data-cs-company><option value="">All companies</option>{options}</select></label>
</div>"""


# Tags that only repeat the topic's own name, left out of that topic's "How they built it" row
SAME_AS_TOPIC = {"rag": {"RAG"}, "agents": {"Agents"}, "evals": {"Evals"}, "cost": {"Cost"},
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


def build_all(posts: list[dict], papers: dict, page, write, site_dir: str, logo_dir: str = "",
              site_url: str = "", theme_script: str = "", head_extra: str = "") -> list[str]:
    """Write the Case studies pages: the main page with a section per topic, and one page per topic.
    page is site_builder.page; logo_dir holds the icons case_logos.py saved. It also writes "How I built
    AI Papers Daily" (making_of.py), whose card leads the main page. Returns the paths for the sitemap."""
    posts = _clean(posts)
    companies = {p["company"] for p in posts}
    LOGO_FILES.clear()
    for company in companies:
        name = case_logos.saved_file(company, logo_dir) if logo_dir and not _slug(company) else ""
        if name:
            os.makedirs(os.path.join(site_dir, DIR, "logos"), exist_ok=True)
            shutil.copyfile(os.path.join(logo_dir, name), os.path.join(site_dir, DIR, "logos", name))
            LOGO_FILES[company] = name
    related = related_papers(posts, papers, k=1) if papers else {}
    desc = "How companies like Netflix, Meta and Spotify build AI into their products, from their own engineering blogs."
    sprite_all = sprite(companies)

    def card(p: dict, hidden: bool = False) -> str:
        pid = (related.get(p["url"]) or [None])[0]
        html_ = post_card(p, (pid, papers[pid]["title"]) if pid else None)
        return html_.replace("<li ", "<li hidden ", 1) if hidden else html_

    def feed(these: list[dict], cls: str = "") -> str:
        """Every post in a filterable list: the first PAGE_SIZE shown, the rest behind Show more."""
        more = (f'<button class="cs-more" type="button" data-cs-more="{PAGE_SIZE}">Show more write-ups</button>'
                if len(these) > PAGE_SIZE else "")
        items = "".join(card(p, i >= PAGE_SIZE) for i, p in enumerate(these))
        return f'<ul class="cs-grid{cls}" data-cs-list data-cs-paged="{PAGE_SIZE}">{items}</ul>{NONE}{more}'

    def wrap(inner: str, style: str = "") -> str:
        return f'{sprite_all}<div class="cs-wrap"{style}>{inner}</div>'

    # The main page: the newest write-ups, then a section for each topic
    if posts:
        lead = (f"Write-ups from {len(companies)} company engineering blogs about AI running in real products, "
                "grouped by topic. Each card opens the original post on the company’s own blog.")
        # Our own write-up about building this site leads, beside the newest company post
        sections = [f'<section class="cs-sec"><div class="cs-sec-head"><h2>Newest</h2></div>'
                    f'<ul class="cs-grid">{making_of.card()}{"".join(card(p) for p in posts[:1])}</ul></section>']
        for k in TOPICS:
            these = [p for p in posts if p["problem"] == k]
            if not these:
                continue
            see = (f'<a class="cs-see" href="{SLUGS[k]}.html">See all {len(these)}{EXT_ARROW}</a>'
                   if len(these) > PER_SECTION else f'<a class="cs-see" href="{SLUGS[k]}.html">Open topic{EXT_ARROW}</a>')
            sections.append(
                f'<section class="cs-sec" id="{SLUGS[k]}" style="--c:var(--l-{k})"><div class="cs-sec-head">'
                f'<div><h2><i aria-hidden="true"></i><a href="{SLUGS[k]}.html">{esc(SHORT[k])}</a></h2>'
                f'<p>{esc(TOPIC_INFO[k][1])}</p></div>{see}</div>'
                f'<ul class="cs-grid cs-plain">{"".join(card(p) for p in these[:PER_SECTION])}</ul></section>')
        inner = f"""{filters(posts, posts)}
<div data-cs-sections>{"".join(sections)}</div>
<div data-cs-results hidden>{status(len(posts))}{feed(posts, " cs-plain")}</div>"""
    else:
        lead = ("Write-ups from company engineering blogs about AI running in real products, grouped by topic. "
                "Each card will open the original post on the company’s own blog.")
        inner = ('<div class="cs-empty"><p><b>No write-ups yet.</b> The first ones arrive with the next blog check, '
                 'on Monday or Thursday morning.</p></div>')
    body = f'<section class="cs-top"><h1>How companies build AI</h1><p>{lead}</p></section>{inner}'
    write(os.path.join(site_dir, DIR, "index.html"),
          page("Case studies", wrap(body), root=ROOT, active="cases", path=f"{DIR}/index.html", description=desc))
    paths = [f"{DIR}/index.html"]
    paths += making_of.build(write, site_dir, site_url, posts, theme_script, head_extra)

    # One page per topic with write-ups
    for k in TOPICS:
        these = [p for p in posts if p["problem"] == k]
        if not these:
            continue
        name, about = TOPIC_INFO[k]
        body = (f'<p class="cs-crumb"><a href="index.html">Case studies</a> / {esc(name)}</p>'
                f'<section class="cs-top cs-topic-top"><h1>{esc(name)}</h1><p>{esc(about)}</p></section>'
                f'{filters(posts, these, k)}{approaches(these, k)}{status(len(these))}{feed(these)}')
        write(os.path.join(site_dir, DIR, f"{SLUGS[k]}.html"),
              page(f"{name}: case studies", wrap(body, f' style="--c:var(--l-{k})"'), root=ROOT, active="cases",
                   path=f"{DIR}/{SLUGS[k]}.html",
                   description=f"How companies handle {name.lower()} in production, from their own engineering blogs."))
        paths.append(f"{DIR}/{SLUGS[k]}.html")
    return paths
