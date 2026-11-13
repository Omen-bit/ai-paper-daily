"""
tests/test_case_detail.py
A page per case study (case_detail.py): stable addresses, the page's own content and SEO parts,
noindex for thin pages, the sitemap entries, related cases, and the cards' Details link.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import case_detail as cd
import case_pages
import case_studies as cs
import site_builder

TODAY = "2026-11-13"
SITE = site_builder.SITE_URL  # the canonical address and the JSON-LD use the same site address
ORIGINAL_BODY = "VERBATIM SENTENCE FROM THE ORIGINAL BLOG POST THAT MUST NEVER APPEAR"


def _post(n, problem="rag", company="Acme", title=None, **extra):
    post = {"url": f"https://eng.acme.example/post-{n}", "company": company, "title": title or f"Post number {n}",
            "problem": problem, "published": "2026-11-0" + str(1 + n % 9), "added": "2026-11-10",
            "issue": f"Search answers were wrong in case {n}.", "summary": f"A retriever with reranking, case {n}.",
            "tags": ["RAG", "Reranking"], "text": ORIGINAL_BODY}
    post.update(extra)
    return post


def _build(tmp_path, posts):
    written = {}
    paths = case_pages.build_all(posts, {}, site_builder.page, lambda path, text: written.__setitem__(path, text),
                                 str(tmp_path), site_url=SITE, today=TODAY)
    return written, paths


def _case_page(written, tmp_path, slug):
    return written[os.path.join(str(tmp_path), "case-studies", f"{slug}.html")]


# ---------- addresses

def test_slugs_are_readable_and_stay_once_given():
    posts = [_post(1, company="Netflix", title="Netflix: Ranking the home feed, with two towers!")]
    assert cs.assign_slugs(posts) == 1
    assert posts[0]["slug"] == "netflix-ranking-the-home-feed-with-two-towers"
    posts[0]["title"] = "A completely new title"
    assert cs.assign_slugs(posts) == 0 and posts[0]["slug"] == "netflix-ranking-the-home-feed-with-two-towers"
    long = [_post(2, title="word " * 40)]
    cs.assign_slugs(long)
    assert len(long[0]["slug"]) <= 31 + cs.SLUG_TITLE_MAX and not long[0]["slug"].endswith("-")
    assert cs.base_slug({"company": "Zoë Café", "title": "Über RAG"}) == "zoe-cafe-uber-rag"


def test_slug_collisions_get_a_number_in_the_order_posts_arrived():
    a = _post(1, title="Same title", added="2026-11-01")
    b = _post(2, title="Same title", added="2026-11-05")
    c = _post(3, title="Same title", added="2026-11-03")
    cs.assign_slugs([b, a, c])
    assert (a["slug"], c["slug"], b["slug"]) == ("acme-same-title", "acme-same-title-2", "acme-same-title-3")
    taken = [{**_post(9), "slug": "acme-same-title"}]
    d = _post(4, title="Same title")
    cs.assign_slugs(taken + [d])
    assert d["slug"] == "acme-same-title-2"
    reserved = {"company": "index", "title": ""}
    cs.assign_slugs([reserved])
    assert reserved["slug"] == "index-2"  # never a page the site already has


# ---------- the pages

def test_every_shown_case_gets_a_page_and_indexable_ones_go_in_the_sitemap(tmp_path):
    posts = [_post(i) for i in range(5)] + [_post(9, issue="", summary="")]  # the last one is thin
    written, paths = _build(tmp_path, posts)
    cs.assign_slugs(slugs_src := [dict(p) for p in posts])
    for p in slugs_src:
        assert os.path.join(str(tmp_path), "case-studies", f"{p['slug']}.html") in written
    entries = [e for e in paths if isinstance(e, tuple)]
    assert len(entries) == 5 and all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) for _, d in entries)
    thin_slug = next(p["slug"] for p in slugs_src if p["url"].endswith("post-9"))
    assert f"case-studies/{thin_slug}.html" not in [e[0] for e in entries]
    thin = _case_page(written, tmp_path, thin_slug)
    assert '<meta name="robots" content="noindex">' in thin and 'rel="canonical"' not in thin
    assert all("slug" not in p for p in posts)  # build_all works on copies


def test_a_case_page_has_its_seo_parts_and_sends_readers_to_the_original(tmp_path):
    post = _post(1, company="Netflix", title="Ranking the home feed", result="Clicks up 12%",
                 techniques=["rag", "embeddings"], industry="media", build_score=4,
                 build_details={"architecture": True, "stack": True, "evaluation": True, "failure_modes": False,
                                "numbers": True}, suggested_by="Priya K.")
    written, _ = _build(tmp_path, [post, _post(2, company="Netflix"), _post(3, problem="evals")])
    page = _case_page(written, tmp_path, "netflix-ranking-the-home-feed")
    assert "<title>Netflix: Ranking the home feed | AI Papers Daily case study</title>" in page
    assert f'<link rel="canonical" href="{SITE}case-studies/netflix-ranking-the-home-feed.html">' in page
    assert '<meta property="og:type" content="article">' in page and 'name="twitter:card"' in page
    desc = re.search(r'<meta name="description" content="([^"]*)">', page).group(1)
    assert desc.startswith("Search answers were wrong in case 1.") and len(desc) <= cd.DESCRIPTION_MAX
    assert "noindex" not in page
    # The button to the original, at the top and the bottom: a plain followed link in a new tab
    buttons = re.findall(r'<a class="cd-go" href="([^"]+)" rel="([^"]+)" target="_blank">Read the full write-up on ([^ <]+)', page)
    assert buttons == [("https://eng.acme.example/post-1", "noopener", "eng.acme.example")] * 2
    assert "nofollow" not in page
    # Our own words only
    assert ORIGINAL_BODY not in page
    assert "Search answers were wrong in case 1." in page and "A retriever with reranking, case 1." in page
    assert "Clicks up 12%" in page
    # Breadcrumb, pills, chips that filter the Case studies page, the checklist, credit, follow, suggest
    assert 'aria-label="Breadcrumb"><a href="index.html">Case studies</a>' in page and 'href="rag.html">RAG and search</a>' in page
    assert "Build details 4/5" in page and page.count('class="cd-yes"') == 4 and page.count('class="cd-no"') == 1
    assert 'href="index.html?tech=rag">RAG</a>' in page and 'href="index.html?ind=media">Media</a>' in page
    assert 'href="index.html?q=Reranking">Reranking</a>' in page
    assert "Suggested by <b>Priya K.</b>" in page and 'data-follow="rag"' in page and 'href="index.html?suggest=1"' in page
    # JSON-LD that parses: the article, based on the original, and a breadcrumb list
    ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S).group(1))
    article, crumbs = ld["@graph"]
    assert article["@type"] == "TechArticle" and article["headline"] == "Ranking the home feed"
    assert article["citation"] == "https://eng.acme.example/post-1"
    assert article["isBasedOn"] == {"@type": "CreativeWork", "name": "Ranking the home feed",
                                    "url": "https://eng.acme.example/post-1",
                                    "publisher": {"@type": "Organization", "name": "Netflix"}}
    assert article["publisher"] == {"@type": "Organization", "name": "AI Papers Daily", "url": SITE,
                                    "logo": {"@type": "ImageObject", "url": f"{SITE}og/site.png"}}
    assert "author" not in article and "Netflix" not in json.dumps(article["publisher"])
    assert article["datePublished"] == "2026-11-02"
    assert article["url"] == f"{SITE}case-studies/netflix-ranking-the-home-feed.html"
    assert [i["name"] for i in crumbs["itemListElement"]] == ["Case studies", "RAG and search", "Netflix"]


def test_the_checklist_shows_only_for_tagged_posts(tmp_path):
    written, _ = _build(tmp_path, [_post(1)])
    page = _case_page(written, tmp_path, "acme-post-number-1")
    assert "cd-build" not in page and "Techniques" not in page


def test_related_cases_share_topic_and_techniques_and_never_include_the_case():
    posts = [_post(1, techniques=["rag"]), _post(2, techniques=["rag"], build_score=5), _post(3, problem="evals"),
             _post(4, problem="evals", tags=[]), _post(5, problem="vision", tags=["Multimodal"])]
    related = cd.related_cases(posts)
    first = [p["url"][-1] for p in related[posts[0]["url"]]]
    assert "1" not in first and first[0] == "2"  # same topic and technique first
    assert "5" not in first  # nothing in common
    assert all(p["url"] != q["url"] for p in posts for q in related[p["url"]])
    assert related[posts[4]["url"]] == []


def test_cards_keep_the_title_on_the_original_and_add_a_details_link(tmp_path):
    written, _ = _build(tmp_path, [_post(1), _post(2)])
    index = written[os.path.join(str(tmp_path), "case-studies", "index.html")]
    card = index.split('href="https://eng.acme.example/post-1"', 1)
    assert card[0].rsplit("<h3>", 1)[1].startswith('<a class="cs-link"')  # the title still opens the original
    assert '<a class="cs-details" href="acme-post-number-1.html" aria-label="Details: Post number 1">Details</a>' in index
    topic = written[os.path.join(str(tmp_path), "case-studies", "rag.html")]
    assert 'href="acme-post-number-1.html"' in topic  # topic pages link to the case pages
    rows = json.loads(index.split('id="cf-index">', 1)[1].split("</script>", 1)[0])["posts"]
    assert {r["sl"] for r in rows} == {"acme-post-number-1", "acme-post-number-2"}


def test_descriptions_are_cut_at_a_word():
    long = {"issue": "word " * 50, "summary": "more " * 50, "company": "A", "title": "T"}
    d = cd.description(long)
    assert len(d) <= cd.DESCRIPTION_MAX and d.endswith("…") and not d.endswith(" …")
    assert cd.description({"company": "Acme", "title": "Thing"}).startswith("How Acme built it")
