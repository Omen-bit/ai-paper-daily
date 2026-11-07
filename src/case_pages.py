"""
case_pages.py
The Case studies pages: engineering write-ups from company blogs, sorted onto a map of
problems (lines) and steps (stops). Every card links out to the company's own blog.

  case-studies/index.html       By problem: the map and one card per problem
  case-studies/companies.html   Every company, with what it writes about
  case-studies/latest.html      Every write-up, newest first
  case-studies/<problem>.html   One problem, step by step

site_builder.build_site calls build_all with the posts from data/cases.json.
"""
import html
import json
import math
import os

from case_sources import BY_NAME, PROBLEMS, STEP_QUESTIONS, lines_at, shared_with

DIR = "case-studies"
ROOT = "../"
SLUGS = {"recs": "recommendations", "search": "search", "ads": "ads", "llm": "llm-apps",
         "vision": "vision", "predict": "forecasting"}
# Map rows: lines sharing Feature pipelines sit next to each other so its interchange is one capsule
SHORT = {"recs": "Recommendations", "search": "Search", "ads": "Ads", "llm": "LLM apps", "vision": "Vision",
         "predict": "Forecasting"}
ROWS = ["recs", "ads", "predict", "search", "llm", "vision"]
CARDS_PER_STEP = 4
LATEST_PAGE = 24

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "case_brands.json"), encoding="utf-8") as _f:
    BRAND_ICONS = json.load(_f)

EXT = ('<svg class="cs-ext" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
       'stroke-linejoin="round" aria-hidden="true"><path d="M15 3h6v6"/><path d="M10 14 21 3"/>'
       '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>')
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
    return PROBLEMS[key][0]


def steps_of(key: str) -> list[str]:
    return PROBLEMS[key][2]


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
        else:
            fill = "currentColor" if _dark_brand(company) else brand_hex(company)
            out.append(f'<symbol id="b-{slug}" viewBox="0 0 24 24"><path fill="{fill}" d="{BRAND_ICONS[slug]["path"]}"/></symbol>')
    if not out:
        return ""
    return f'<svg class="cs-sprite" aria-hidden="true" focusable="false"><defs>{"".join(out)}</defs></svg>'


def logo(company: str, cls: str = "") -> str:
    """The company's real logo from the sprite, or its initials on its brand colour when there is none."""
    slug = _slug(company)
    dark = " cs-ink" if _dark_brand(company) else ""
    if slug:
        return f'<svg class="{cls}{dark}" aria-hidden="true"><use href="#b-{slug}"/></svg>'
    letters = (company[:1] or "?").upper()
    return f'<span class="{cls} cs-mono" style="--b:{brand_hex(company)}" aria-hidden="true">{esc(letters)}</span>'


# ---------- covers

def cover_route(problem: str, step: int) -> str:
    """A post's place in the system: its step, the steps either side, or the junction it shares."""
    names = steps_of(problem)
    out = ['<svg class="cs-r" viewBox="0 0 320 118" aria-hidden="true">']
    others = shared_with(problem, step)
    cx = 160
    if others:
        lines = [k for k in ROWS if k in [problem] + others]
        n = len(lines)
        gap = 26 if n == 2 else 13 if n <= 4 else 10
        y0 = 46 - (n - 1) * gap / 2
        for key in [k for k in lines if k != problem] + [problem]:
            y = y0 + lines.index(key) * gap
            own = key == problem
            out.append(f'<path d="M0 {y:.1f} C 80 {y:.1f} 108 46 146 46 L 174 46 C 212 46 240 {y:.1f} 320 {y:.1f}" '
                       f'fill="none" style="stroke:var(--l-{key})" stroke-width="{5 if own else 3}" '
                       f'opacity="{1 if own else .5}"/>')
        out.append(f'<circle cx="{cx}" cy="46" r="15" class="cap"/>')
        who = ("all " + ("six" if n == 6 else str(n)) + " problems") if n > 3 else " and ".join(SHORT[k] for k in others)
        out.append(f'<text class="big" x="{cx}" y="96" text-anchor="middle">{esc(names[step])}</text>')
        out.append(f'<text class="sm" x="{cx}" y="113" text-anchor="middle">Shared with {esc(who)}</text>')
    else:
        y = 44
        x1 = 110 if step == 0 else 0
        x2 = 210 if step == 5 else 320
        out.append(f'<line x1="{x1}" y1="{y}" x2="{cx}" y2="{y}" stroke-width="5" stroke-linecap="round"/>')
        out.append(f'<line x1="{cx}" y1="{y}" x2="{x2}" y2="{y}" stroke-width="5" stroke-linecap="round" class="todo"/>')
        if step > 0:
            out.append(f'<circle cx="40" cy="{y}" r="5" class="st"/><text class="sm" x="12" y="{y - 16}">{esc(names[step - 1])}</text>')
        if step < 5:
            out.append(f'<circle cx="280" cy="{y}" r="5" class="st todo-st"/>'
                       f'<text class="sm" x="308" y="{y - 16}" text-anchor="end">{esc(names[step + 1])}</text>')
        out.append(f'<circle cx="{cx}" cy="{y}" r="15" class="halo"/><circle cx="{cx}" cy="{y}" r="9" class="on"/>')
        out.append(f'<text class="big" x="{cx}" y="{y + 42}" text-anchor="middle">{esc(names[step])}</text>')
        out.append(f'<text class="sm" x="{cx}" y="{y + 60}" text-anchor="middle">Step {step + 1} of 6</text>')
    return "".join(out) + "</svg>"


def search_text(*parts) -> str:
    return esc(" ".join(str(p) for p in parts if p).lower())


def post_card(post: dict, show_line: bool = True, related: list = ()) -> str:
    problem, step, company = post["problem"], int(post["step"]), post["company"]
    lines = " ".join(lines_at(problem, step))
    line = f'<span class="cs-line">{esc(problem_name(problem))}</span>' if show_line else ""
    summary = f'<p>{esc(post["summary"])}</p>' if post.get("summary") else ""
    return f"""<li class="cs-card" style="--c:var(--l-{problem});--b:{brand_hex(company)}" data-cs-item data-p="{lines}" data-t="{search_text(post['title'], company, problem_name(problem), steps_of(problem)[step])}">
<div class="cs-cover">{logo(company, "cs-big")}<span class="cs-co">{logo(company, "cs-badge")}{esc(company)}</span>{line}{cover_route(problem, step)}</div>
<div class="cs-body"><h3><a class="cs-link" href="{esc(post['url'])}" rel="noopener" target="_blank">{esc(post['title'])}</a></h3>{summary}<span class="cs-src">Read on {esc(host(post['url']))}{EXT}</span></div></li>"""


def company_card(company: str, posts: list[dict]) -> str:
    mix: dict[str, int] = {}
    for p in posts:
        mix[p["problem"]] = mix.get(p["problem"], 0) + 1
    mix_sorted = sorted(mix.items(), key=lambda kv: (-kv[1], ROWS.index(kv[0])))
    bar = "".join(f'<i style="flex:{n};background:var(--l-{k})"></i>' for k, n in mix_sorted)
    legend = "".join(f'<li style="--c:var(--l-{k})">{esc(problem_name(k))} <b>{n}</b></li>' for k, n in mix_sorted)
    top = [problem_name(k) for k, _ in mix_sorted[:2]]
    top = [t if t.startswith("LLM") else t[0].lower() + t[1:] for t in top]
    focus = "Writes most about " + ", then ".join(top) + "."
    src = BY_NAME.get(company)
    blog = src[2] if src else posts[0]["url"]
    newest = max(posts, key=lambda p: p.get("published") or "")
    problems = " ".join(sorted({k for p in posts for k in lines_at(p["problem"], int(p["step"]))}))
    return f"""<li class="cs-cc" style="--b:{brand_hex(company)}" data-cs-item data-p="{problems}" data-t="{search_text(company, *(p['title'] for p in posts))}">
<div class="cs-ccov">{logo(company, "cs-big")}{logo(company, "cs-badge")}<h3><a class="cs-link" href="{esc(blog)}" rel="noopener" target="_blank">{esc(company)}</a></h3><span class="cs-dom">{esc(host(blog))}</span></div>
<div class="cs-ccb"><p>{esc(focus)}</p><p class="cs-newest">Newest: {esc(newest['title'])}</p>
<div class="cs-mix"><div class="cs-mixbar" aria-hidden="true">{bar}</div><ul>{legend}</ul></div>
<div class="cs-foot"><span>{len(posts)} write-up{"" if len(posts) == 1 else "s"}</span><span class="cs-src">Visit blog{EXT}</span></div></div></li>"""


def problem_card(key: str, n: int, companies: list[str], titles: list[str]) -> str:
    xs = [24 + i * 272 / 5 for i in range(6)]
    stops = "".join(f'<circle cx="{x:.1f}" cy="38" r="8" class="cap"/>' if shared_with(key, i) else
                    f'<circle cx="{x:.1f}" cy="38" r="6" class="st"/>' for i, x in enumerate(xs))
    svg = f'<svg class="cs-r" viewBox="0 0 320 60" aria-hidden="true"><line x1="0" y1="38" x2="320" y2="38" stroke-width="6"/>{stops}</svg>'
    steps = "".join(f"<li>{esc(s)}</li>" for s in steps_of(key))
    logos = "".join(f'<span title="{esc(c)}">{logo(c, "cs-mini")}</span>' for c in companies[:5])
    who = (f'{logos}<em>{len(companies)} compan{"y" if len(companies) == 1 else "ies"}</em>' if companies
           else "<em>No write-ups yet</em>")
    return f"""<li class="cs-card cs-pc" style="--c:var(--l-{key})" data-cs-item data-p="{key}" data-t="{search_text(problem_name(key), PROBLEMS[key][1], *steps_of(key), *companies, *titles)}">
<div class="cs-cover"><span class="cs-co cs-pname"><a class="cs-link" href="{SLUGS[key]}.html">{esc(problem_name(key))}</a></span><span class="cs-line">{n} write-up{"" if n == 1 else "s"}</span>{svg}</div>
<div class="cs-body"><p>{esc(PROBLEMS[key][1])}</p><ol class="cs-steps">{steps}</ol><span class="cs-logos">{who}</span></div></li>"""


# ---------- the map

def map_svg(counts: dict) -> str:
    """Every problem as a line and every step as a stop, with how many write-ups each has."""
    X = [250, 430, 590, 745, 905, 1045]
    y0, dy, width = 78, 74, 1110
    height = y0 + dy * (len(ROWS) - 1) + 58
    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Map of the steps companies write about, by problem">']
    for i, key in enumerate(ROWS):
        y = y0 + i * dy
        out.append(f'<line x1="170" y1="{y}" x2="{width - 20}" y2="{y}" style="stroke:var(--l-{key})" stroke-width="8" stroke-linecap="round"/>')
    for i, key in enumerate(ROWS):
        y = y0 + i * dy
        page = f"{SLUGS[key]}.html"
        out.append(f'<a href="{page}"><rect x="0" y="{y - 16}" width="176" height="32" rx="16" style="fill:var(--l-{key})"/>'
                   f'<text class="ln" x="16" y="{y + 5}">{esc(problem_name(key))}</text></a>')
        for s, x in enumerate(X):
            if shared_with(key, s):
                continue
            label, n = steps_of(key)[s], counts.get((key, s), 0)
            if n:
                out.append(f'<a href="{page}#s{s}"><circle cx="{x}" cy="{y}" r="8.5" style="fill:var(--surface);stroke:var(--l-{key})" stroke-width="4.5"/>'
                           f'<text class="st" x="{x}" y="{y + 29}" text-anchor="middle">{esc(label)} <tspan class="n">{n}</tspan></text></a>')
            else:
                out.append(f'<circle cx="{x}" cy="{y}" r="8.5" style="fill:var(--surface);stroke:var(--muted)" stroke-width="2" stroke-dasharray="3 3"/>'
                           f'<text class="n" x="{x}" y="{y + 29}" text-anchor="middle">{esc(label)}, none yet</text>')
    # Interchanges: one capsule over the rows that share the stop
    for s in (1, 4, 5):
        rows = [i for i, key in enumerate(ROWS) if shared_with(key, s)]
        first, last = min(rows), max(rows)
        ya, yb = y0 + first * dy - 17, y0 + last * dy + 17
        n = counts.get(("shared", s), 0)
        out.append(f'<a href="{SLUGS[ROWS[first]]}.html#s{s}"><rect x="{X[s] - 15}" y="{ya}" width="30" height="{yb - ya}" rx="15" '
                   f'style="fill:var(--surface);stroke:var(--ink)" stroke-width="3"/>'
                   f'<text class="ic" x="{X[s]}" y="{ya - 12}" text-anchor="middle">{esc(steps_of(ROWS[first])[s])} <tspan class="n">{n}</tspan></text></a>')
    return "\n".join(out) + "</svg>"


# ---------- shared page parts

def top(current: str, n_posts: int, n_companies: int) -> str:
    views = [("By problem", "index.html", ""), ("Companies", "companies.html", str(n_companies) if n_companies else ""),
             ("Latest", "latest.html", "")]
    tabs = "".join(f'<a href="{href}"{" aria-current=\"page\"" if name == current else ""}>{name}'
                   f'{f"<sup>{n}</sup>" if n else ""}</a>' for name, href, n in views)
    lead = (f"Engineering write-ups from {n_companies} company blogs about AI running in real products, sorted by the problem "
            "they solve and the step they explain. Every link opens the original post on the company’s own blog."
            if n_posts else
            "Engineering write-ups from company blogs about AI running in real products, sorted by the problem they solve "
            "and the step they explain. The first write-ups arrive with the next daily update.")
    return f"""<section class="cs-top"><h1>How companies<br>build AI</h1><p>{lead}</p>
<div class="cs-bar"><nav class="cs-views" aria-label="Case study views">{tabs}</nav>
<div class="cs-find"><label for="cs-q">Search write-ups and companies</label><div class="cs-search">{SEARCH}<input id="cs-q" type="search" placeholder="Feature store, RAG, Netflix" autocomplete="off" data-cs-q></div></div></div></section>"""


def problem_select() -> str:
    options = "".join(f'<option value="{k}">{esc(problem_name(k))}</option>' for k in ROWS)
    return (f'<label class="cs-sel"><span>Problem</span><select data-cs-filter><option value="">All problems</option>'
            f'{options}</select></label>')


NO_MATCH = '<p class="cs-none" data-cs-none hidden>Nothing matches. Try a company name or a broader word, or clear the search.</p>'


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


# ---------- pages

def _clean(posts: list[dict]) -> list[dict]:
    good = []
    for p in posts:
        try:
            if p["problem"] in PROBLEMS and 0 <= int(p["step"]) <= 5 and p.get("url", "").startswith("https://") and p.get("title"):
                good.append(p)
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(good, key=lambda p: (p.get("published") or "", p["url"]), reverse=True)


def build_all(posts: list[dict], papers: dict, page, write, site_dir: str) -> list[str]:
    """Write every Case studies page. page is site_builder.page; returns the paths for the sitemap."""
    posts = _clean(posts)
    by_company: dict[str, list[dict]] = {}
    for p in posts:
        by_company.setdefault(p["company"], []).append(p)
    companies = sorted(by_company, key=lambda c: (-len(by_company[c]), c.lower()))
    n_posts, n_cos = len(posts), len(companies)
    on_line = {k: [p for p in posts if k in lines_at(p["problem"], int(p["step"]))] for k in ROWS}
    sprite_all = sprite(companies)
    related = related_papers(posts, papers) if papers else {}
    desc = "How companies like Netflix, Meta and Spotify build AI into their products, from their own engineering blogs."

    def wrap(inner: str) -> str:
        return f'{sprite_all}<div class="cs-wrap">{inner}</div>'

    # By problem
    counts: dict = {}
    for p in posts:
        s = int(p["step"])
        if shared_with(p["problem"], s):
            counts[("shared", s)] = counts.get(("shared", s), 0) + 1
        else:
            counts[(p["problem"], s)] = counts.get((p["problem"], s), 0) + 1
    cards = []
    for key in sorted(ROWS, key=lambda k: -len(on_line[k])):
        cos = sorted({p["company"] for p in on_line[key]}, key=lambda c: -sum(1 for p in on_line[key] if p["company"] == c))
        cards.append(problem_card(key, len(on_line[key]), cos, [p["title"] for p in on_line[key]]))
    body = f"""{top("By problem", n_posts, n_cos)}
<section class="cs-map" aria-labelledby="cs-map-h"><div class="cs-map-top"><h2 id="cs-map-h">Every problem, step by step</h2>
<p>Each line is a problem. Each stop is a step you can read about.</p>
<div class="cs-key"><span><i class="h"></i>Has write-ups</span><span><i class="c"></i>Shared by several problems</span></div></div>
<p class="cs-swipe">Swipe sideways to see the whole map</p><div class="cs-map-scroll">{map_svg(counts)}</div></section>
<div class="cs-head"><h2>Pick a problem</h2></div>
<ul class="cs-grid cs-g3">{"".join(cards)}</ul>{NO_MATCH}"""
    write(os.path.join(site_dir, DIR, "index.html"),
          page("Case studies", wrap(body), root=ROOT, active="cases", path=f"{DIR}/index.html", description=desc))

    # Companies
    if companies:
        start = "".join(company_card(c, by_company[c]) for c in companies[:4])
        rest = "".join(company_card(c, by_company[c]) for c in sorted(companies, key=str.lower))
        inner = f"""<div class="cs-head"><h2>Start here</h2></div><p class="cs-sub">The teams that write most about AI in production.</p>
<ul class="cs-grid cs-g4">{start}</ul>
<div class="cs-head"><h2>All companies</h2>{problem_select()}</div><p class="cs-sub" data-cs-count>{n_cos} companies</p>
<ul class="cs-grid cs-g4" data-cs-list>{rest}</ul>{NO_MATCH}"""
    else:
        inner = '<div class="cs-empty"><p><b>No companies yet.</b> Write-ups arrive with the next daily update.</p></div>'
    write(os.path.join(site_dir, DIR, "companies.html"),
          page("Case studies by company", wrap(top("Companies", n_posts, n_cos) + inner), root=ROOT, active="cases",
               path=f"{DIR}/companies.html", description=desc))

    # Latest
    if posts:
        items = "".join(post_card(p).replace("<li ", "<li hidden " if i >= LATEST_PAGE else "<li ", 1)
                        for i, p in enumerate(posts))
        more = (f'<button class="cs-more" type="button" data-cs-more="{LATEST_PAGE}">Show more write-ups</button>'
                if n_posts > LATEST_PAGE else "")
        inner = f"""<div class="cs-head"><h2>Newest write-ups</h2>{problem_select()}</div><p class="cs-sub" data-cs-count>{n_posts} write-ups</p>
<ul class="cs-grid" data-cs-list data-cs-paged="{LATEST_PAGE}">{items}</ul>{NO_MATCH}{more}"""
    else:
        inner = '<div class="cs-empty"><p><b>No write-ups yet.</b> They arrive with the next daily update.</p></div>'
    write(os.path.join(site_dir, DIR, "latest.html"),
          page("Latest case studies", wrap(top("Latest", n_posts, n_cos) + inner), root=ROOT, active="cases",
               path=f"{DIR}/latest.html", description=desc))

    # One page per problem
    paths = [f"{DIR}/index.html", f"{DIR}/companies.html", f"{DIR}/latest.html"]
    for key in ROWS:
        names = steps_of(key)
        by_step = {s: [p for p in on_line[key] if int(p["step"]) == s] for s in range(6)}
        route = _route_all(key, {s: len(v) for s, v in by_step.items()})
        nav = "".join(f'<li{" class=\"on\"" if s == 0 else ""}><a href="#s{s}">{esc(names[s])}</a></li>' for s in range(6))
        secs = []
        for s in range(6):
            shared = shared_with(key, s)
            note = (" Shared with " + ("every problem" if len(shared) > 3 else " and ".join(problem_name(k) for k in shared)) + "."
                    if shared else "")
            these = by_step[s]
            if these:
                cards = "".join(post_card(p, show_line=p["problem"] != key).replace("<li ", "<li hidden " if i >= CARDS_PER_STEP else "<li ", 1)
                                for i, p in enumerate(these))
                more = (f'<button class="cs-more" type="button" data-cs-showall>Show all {len(these)} write-ups</button>'
                        if len(these) > CARDS_PER_STEP else "")
                block = f'<ul class="cs-grid cs-g2">{cards}</ul>{more}'
            else:
                block = (f'<div class="cs-empty"><p><b>No write-ups on {esc(names[s].lower())} yet.</b> '
                         'New posts are added every morning.</p></div>')
            pids = []
            for p in these:
                for pid in related.get(p["url"], []):
                    if pid not in pids:
                        pids.append(pid)
            papers_box = ""
            if pids:
                items = "".join(f'<li><a href="../paper/{esc(pid)}.html">{esc(papers[pid]["title"])}</a></li>' for pid in pids[:4])
                papers_box = f'<div class="cs-papers"><h3>Papers on this step</h3><ul>{items}</ul></div>'
            secs.append(f'<section class="cs-step" id="s{s}"><h2>{esc(names[s])}</h2>'
                        f'<p class="cs-sub">{esc(STEP_QUESTIONS.get(names[s], ""))}{esc(note)}</p>{block}{papers_box}</section>')
        body = f"""<p class="cs-crumb"><a href="index.html">Case studies</a> / {esc(problem_name(key))}</p>
<header class="cs-ph"><h1>{esc(problem_name(key))}</h1><p>{esc(PROBLEMS[key][1])} Read it in the order the system runs.</p>
<div class="cs-route-wrap">{route}</div></header>
<div class="cs-pg"><ol class="cs-nav" aria-label="Steps">{nav}</ol><div>{"".join(secs)}</div></div>"""
        write(os.path.join(site_dir, DIR, f"{SLUGS[key]}.html"),
              page(f"{problem_name(key)}: case studies", f'{sprite_all}<div class="cs-wrap" style="--c:var(--l-{key})">{body}</div>',
                   root=ROOT, active="cases", path=f"{DIR}/{SLUGS[key]}.html",
                   description=f"How companies build {problem_name(key).lower()}, step by step, from their engineering blogs."))
        paths.append(f"{DIR}/{SLUGS[key]}.html")
    return paths


def _route_all(key: str, counts: dict) -> str:
    w, y = 1000, 30
    xs = [90 + i * (w - 180) / 5 for i in range(6)]
    out = [f'<svg class="cs-big-route" viewBox="0 0 {w} 90" role="img" aria-label="The six steps of {esc(problem_name(key))}">'
           f'<line x1="0" y1="{y}" x2="{w}" y2="{y}" stroke-width="8"/>']
    for i, x in enumerate(xs):
        cls = ' class="sh"' if shared_with(key, i) else ""
        n = counts.get(i, 0)
        out.append(f'<a href="#s{i}"><circle cx="{x:.1f}" cy="{y}" r="9"{cls}/><text x="{x:.1f}" y="{y + 34}" text-anchor="middle">'
                   f'{esc(steps_of(key)[i])}</text><text class="n" x="{x:.1f}" y="{y + 54}" text-anchor="middle">'
                   f'{n if n else "No"} write-up{"" if n == 1 else "s"}</text></a>')
    return "".join(out) + "</svg>"
