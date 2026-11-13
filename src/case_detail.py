"""
case_detail.py
One page per case study, case-studies/<slug>.html, so search engines can find each write-up on
its own. The page holds only our own words (the Problem / Solution / result lines, the tags and
the build-details checks) and sends the reader to the original post: the main button, at the top
and again at the bottom, opens the company's blog in a new tab.

case_pages.build_all calls build_case_pages with the posts it shows. A case with no Problem and no
Solution line still gets a page, but noindex and out of the sitemap, since it would be thin.
"""
import json
import os

import case_pages as cp
from case_sources import BUILD_DETAILS

DIR = cp.DIR
MAX_RELATED = 6
DESCRIPTION_MAX = 155
# One line per build detail, for the checklist
DETAIL_TEXT = {
    "architecture": ("Architecture", "Shows the system's parts and how data moves between them."),
    "stack": ("Stack", "Names the models, libraries, databases or services they used."),
    "evaluation": ("Evaluation", "Explains how they measured whether it works."),
    "failure_modes": ("Failure modes", "Covers what went wrong, the limits, or lessons learned."),
    "numbers": ("Numbers", "Reports real figures: latency, cost, accuracy, scale or impact."),
}
CHECK = "✓"
DASH = "–"


def esc(text) -> str:
    return cp.esc(text)


def is_thin(post: dict) -> bool:
    return not (post.get("issue") or post.get("summary"))


def description(post: dict, limit: int = DESCRIPTION_MAX) -> str:
    """A meta description from our Problem and Solution lines, cut at a word near limit."""
    text = " ".join(x.strip().rstrip(".") + "." for x in (post.get("issue"), post.get("summary")) if x and x.strip())
    if not text:
        text = f"How {post.get('company', '')} built it: {post.get('title', '')}. Read the write-up on their blog."
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit - 1].rsplit(" ", 1)[0].rstrip(",;:.")
    return cut + "…"


def page_title(post: dict) -> str:
    return f"{post['company']}: {post['title']} | AI Papers Daily case study"


def related_cases(posts: list[dict], k: int = MAX_RELATED) -> dict[str, list[dict]]:
    """For each post, up to k others that share its topic, techniques or tags, best first: same topic
    3, each shared technique 2, each shared tag 1; ties by build details, then the newest. Uses an
    index from each feature to its posts, so it never compares every pair (a topic is only ever a
    small share of the posts)."""
    def features(p):
        return ({("p", p["problem"])} | {("x", t) for t in p.get("techniques") or [] if t != "other"}
                | {("g", t) for t in p.get("tags") or [] if isinstance(t, str)})
    weight = {"p": 3, "x": 2, "g": 1}
    index: dict[tuple, list[int]] = {}
    feats = [features(p) for p in posts]
    for i, fs in enumerate(feats):
        for f in fs:
            index.setdefault(f, []).append(i)
    out = {}
    for i, p in enumerate(posts):
        scores: dict[int, int] = {}
        for f in feats[i]:
            for j in index.get(f, []):
                if j != i:
                    scores[j] = scores.get(j, 0) + weight[f[0]]
        best = sorted(scores.items(), key=lambda kv: (-kv[1], -cp.build_score(posts[kv[0]]),
                                            _desc(posts[kv[0]].get("published") or ""), posts[kv[0]]["url"]))
        out[p["url"]] = [posts[j] for j, _ in best[:k]]
    return out


def _desc(day: str) -> str:
    """A key that sorts dates newest first."""
    return "".join(chr(255 - ord(c)) for c in day)


def _chip(href: str, text: str) -> str:
    return f'<li><a href="{esc(href)}">{esc(text)}</a></li>'


def chips(post: dict) -> str:
    """Techniques, industry and tags, each linking to the Case studies page filtered by it."""
    rows = []
    tech = [t for t in post.get("techniques") or [] if t in cp.TECH_LABELS and t != "other"]
    if tech:
        rows.append(("Techniques", "".join(_chip(f"index.html?tech={t}", cp.TECH_LABELS[t]) for t in tech)))
    industry = post.get("industry")
    if industry in cp.INDUSTRY_LABELS and industry != "other":
        rows.append(("Industry", _chip(f"index.html?ind={industry}", cp.INDUSTRY_LABELS[industry])))
    tags = [t for t in post.get("tags") or [] if isinstance(t, str)][:6]
    if tags:
        from urllib.parse import quote
        rows.append(("Tags", "".join(_chip(f"index.html?q={quote(t)}", t) for t in tags)))
    if not rows:
        return ""
    return ('<section class="cd-tags" aria-label="How it was built"><dl>'
            + "".join(f'<div><dt>{esc(label)}</dt><dd><ul>{items}</ul></dd></div>' for label, items in rows)
            + "</dl></section>")


def checklist(post: dict) -> str:
    """The five build-detail checks, only for a tagged post."""
    details = post.get("build_details")
    if not isinstance(details, dict) or not isinstance(post.get("build_score"), int):
        return ""
    items = "".join(
        f'<li class="{"cd-yes" if details.get(k) else "cd-no"}"><span class="cd-mark" aria-hidden="true">'
        f'{CHECK if details.get(k) else DASH}</span><div><b>{esc(DETAIL_TEXT[k][0])}</b>'
        f'<span class="sr-only">{"described" if details.get(k) else "not described"}. </span>'
        f'<p>{esc(DETAIL_TEXT[k][1])}</p></div></li>' for k in BUILD_DETAILS)
    return (f'<section class="cd-build" aria-labelledby="cd-build-h"><h2 id="cd-build-h">Build details '
            f'{cp.build_score(post)}/{len(BUILD_DETAILS)}</h2><p class="cd-note">What the original post describes.</p>'
            f'<ul>{items}</ul></section>')


def more_from(post: dict, related: list[dict]) -> str:
    if not related:
        return ""
    items = "".join(
        f'<li style="--c:{cp.color(r["problem"])}"><a href="{esc(r["slug"])}.html"><span class="cd-rel-co">'
        f'{cp.logo(r["company"], "cs-badge")}{esc(r["company"])}</span><b>{esc(r["title"])}</b>'
        f'<span class="cs-pills">{cp.NEW_PILL if r.get("is_new") else ""}<span class="cs-topic">{esc(cp.problem_name(r["problem"]))}</span>'
        f'{cp.detail_pill(r)}</span></a></li>' for r in related)
    name = cp.problem_name(post["problem"])
    return (f'<section class="cd-more" aria-labelledby="cd-more-h"><h2 id="cd-more-h">More from {esc(name)}</h2>'
            f'<ul>{items}</ul><p><a class="cs-see" href="{esc(cp.page_slug(post["problem"]))}.html">'
            f'All {esc(name)} write-ups{cp.EXT_ARROW}</a></p></section>')


def json_ld(post: dict, url: str, site_url: str) -> str:
    topic_url = f"{site_url}{DIR}/{cp.page_slug(post['problem'])}.html"
    article = {
        "@type": "TechArticle", "headline": post["title"][:110], "description": description(post),
        "url": url, "mainEntityOfPage": url, "inLanguage": "en",
        "about": cp.problem_name(post["problem"]),
        # Our page is published by AI Papers Daily (no logo file of its own yet, so the share image)
        "publisher": {"@type": "Organization", "name": "AI Papers Daily", "url": site_url,
                      "logo": {"@type": "ImageObject", "url": f"{site_url}og/site.png"}},
        # The company's own post, which this page summarises: the source, and its publisher
        "isBasedOn": {"@type": "CreativeWork", "name": post["title"], "url": post["url"],
                      "publisher": {"@type": "Organization", "name": post["company"]}},
        "citation": post["url"],
        "keywords": ", ".join([cp.TECH_LABELS.get(t, t) for t in post.get("techniques") or [] if t != "other"]
                              + [t for t in post.get("tags") or [] if isinstance(t, str)]),
    }
    if post.get("published"):
        article["datePublished"] = post["published"][:10]
    if post.get("added_at"):
        article["dateModified"] = post["added_at"][:10]
    crumbs = {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Case studies", "item": f"{site_url}{DIR}/index.html"},
        {"@type": "ListItem", "position": 2, "name": cp.problem_name(post["problem"]), "item": topic_url},
        {"@type": "ListItem", "position": 3, "name": post["company"], "item": url},
    ]}
    data = json.dumps({"@context": "https://schema.org", "@graph": [article, crumbs]}, ensure_ascii=False)
    return data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def case_body(post: dict, related: list[dict], site_url: str) -> str:
    """The page body: breadcrumb, header with the button to the original, our summary, the tags, the
    build-details checklist, research behind it, credit, follow / suggest, and related cases."""
    company, problem = post["company"], post["problem"]
    domain = cp.host(post["url"])
    go = (f'<a class="cd-go" href="{esc(post["url"])}" rel="noopener" target="_blank">Read the full write-up on '
          f'{esc(domain)} <span aria-hidden="true">↗</span><span class="sr-only"> (opens in a new tab)</span></a>')
    date = cp.nice_date(post.get("published", ""))
    when = f'<time datetime="{esc(post.get("published", ""))}">{date}</time>' if date else ""
    ps = ""
    if post.get("issue"):
        ps += f'<div class="cd-p"><h2>Problem</h2><p>{esc(post["issue"])}</p></div>'
    if post.get("summary"):
        ps += f'<div class="cd-s"><h2>Solution</h2><p>{esc(post["summary"])}</p></div>'
    if post.get("result"):
        ps += f'<p class="cs-result cd-result">{cp.TREND}<span>{esc(post["result"])}</span></p>'
    ps = (f'<section class="cd-ps" aria-label="Our summary">{ps}</section>' if ps else
          '<p class="cd-thin">We haven’t summarised this one yet. The original post has the details.</p>')
    rp = (post.get("related_papers") or [None])[0]
    research = cp.research_block((rp["id"], rp["title"]) if rp else None)
    credit = cp.credit_row(post).replace('class="cs-by"', 'class="cs-by cd-by"')
    topic_page = f"{cp.page_slug(problem)}.html"
    return f"""<nav class="cs-crumb cd-crumb" aria-label="Breadcrumb"><a href="index.html">Case studies</a> <span aria-hidden="true">/</span> <a href="{esc(topic_page)}">{esc(cp.problem_name(problem))}</a> <span aria-hidden="true">/</span> <span aria-current="page">{esc(company)}</span></nav>
<article class="cd" style="--c:{cp.color(problem)};--b:{cp.brand_hex(company)}">
<header class="cd-head">
<div class="cd-meta"><span class="cd-co">{cp.logo(company, "cd-logo")}<span>{esc(company)}</span></span>{when}</div>
<div class="cs-pills cd-pills">{cp.NEW_PILL if post.get("is_new") else ""}<span class="cs-topic">{esc(cp.problem_name(problem))}</span>{cp.detail_pill(post)}</div>
<h1>{esc(post["title"])}</h1>
<p class="cd-lead">Our short summary of {esc(company)}’s engineering write-up. The full story, with all the detail, is on their blog.</p>
{go}
</header>
{ps}
{chips(post)}
{checklist(post)}
{research}{credit}
<div class="cd-actions">{cp.follow_button(problem)}<a class="cf-suggest" href="index.html?suggest=1">+ Suggest a write-up</a></div>
<div class="cd-bottom"><p>Want the architecture, code and numbers? They’re in the original post.</p>{go}</div>
</article>
{more_from(post, related)}
<script type="application/ld+json">{json_ld(post, f"{site_url}{DIR}/{post['slug']}.html", site_url)}</script>"""


def build_case_pages(posts: list[dict], page, write, site_dir: str, site_url: str, wrap) -> list:
    """Write a page per post. Returns the sitemap entries, (path, last change), for the indexable ones."""
    related = related_cases(posts)
    entries = []
    sprite_cache = {}
    for post in posts:
        thin = is_thin(post)
        rel = related.get(post["url"], [])  # up to 6; a rare topic may have fewer
        companies = {post["company"]} | {r["company"] for r in rel}
        key = frozenset(companies)
        if key not in sprite_cache:
            sprite_cache[key] = cp.sprite(companies)
        body = case_body(post, rel, site_url)
        path = f"{DIR}/{post['slug']}.html"
        html_out = page(post["title"], wrap(body, sprite_cache[key]), root=cp.ROOT, active="cases", path=path,
                        description=description(post), og_type="article", full_title=page_title(post), noindex=thin)
        write(os.path.join(site_dir, DIR, f"{post['slug']}.html"), html_out)
        if not thin:
            entries.append((path, (post.get("added_at") or post.get("published") or "")[:10]))
    return entries
