"""The "How I built AI Papers Daily" case study: the one case study on the site written about the site itself.

build() writes the page, a Markdown copy of it (for "View as Markdown", "Copy for LLM" and cross-posting to
dev.to) and returns their paths; card() is its pixel-art card at the top of the Case studies page.
The page has its own engineering-blog layout (making-of.css). Its short videos and screenshots live in
site_assets/making-of/ and are copied to the site with the other assets."""
import html
import math
import os
import random
import re
from html.parser import HTMLParser
from urllib.parse import quote, urljoin

SLUG = "how-i-built-ai-papers-daily"
TITLE = "How I built AI Papers Daily"
PUBLISHED = "2026-11-08"
AUTHOR = "Prathamesh Salokhe"
READ_MIN = 25
REPO_URL = "https://github.com/Omen-bit/ai-paper-daily"
# After cross-posting the Markdown copy to dev.to, paste the post's link here; the "Read on dev.to" links
# appear once it is set.
DEVTO_URL = ""
DESCRIPTION = ("How AI Papers Daily works, explained simply with short videos: the morning job, the AI judge, "
               "the notes check, search, Ask this paper, Project Scout and the website.")
CARD_TEXT = ("How every part of this site works, from the 07:00 morning job to the AI judge, Ask this paper "
             "and Project Scout, explained simply with short videos.")
MEDIA = "../assets/making-of/"  # from case-studies/ to the copied site_assets/making-of/
VIDEOS = ("morning", "judge", "curator", "ask", "scout")
IMAGES = ("paper", "ask", "papers", "labs", "scout", "trends", "cases", "phone")
ARROW = ('<svg class="ar" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" '
         'fill="none" stroke="currentColor" stroke-width="1.6"/></svg>')
N = {"fig": 0}


def art(seed, w=1200, h=420, cols=60, rows=21):
    """Generative cover: one square per paper from a day; the yellow one is the pick."""
    rnd = random.Random(seed)
    cw, ch = w / cols, h / rows
    cx, cy = cols * (0.62 + rnd.random() * .1), rows * .5
    out = [f'<svg class="art" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice" aria-hidden="true">']
    for r in range(rows):
        for c in range(cols):
            d = math.hypot((c - cx) / 1.6, r - cy)
            wave = math.sin(c / 4.2 + r / 3.1 + seed) * .5 + .5
            v = max(0.0, 1 - d / 13) * .85 + wave * .18 + rnd.random() * .08
            if v < .12:
                continue
            s = min(cw, ch) * (.25 + .55 * min(v, 1))
            cls = "a4" if v > .85 else "a3" if v > .65 else "a2" if v > .42 else "a1"
            out.append(f'<rect class="{cls}" x="{c*cw + (cw-s)/2:.1f}" y="{r*ch + (ch-s)/2:.1f}" width="{s:.1f}" height="{s:.1f}" rx="1"/>')
    px, py = cx * cw, cy * ch
    out.append(f'<rect class="pick" x="{px-10}" y="{py-10}" width="20" height="20" rx="2"/>')
    out.append("</svg>")
    return "".join(out)


def fig(inner, caption, cls=""):
    N["fig"] += 1
    return (f'<figure class="fig {cls}"><div class="fig-box">{inner}</div>'
            f'<figcaption><span class="fig-n">[ Fig. {N["fig"]} ]</span><span>{caption}</span></figcaption></figure>')


def shot(src, alt, caption, cls=""):
    return fig(f'<img src="{MEDIA}img/{src}" alt="{alt}" width="1200" loading="lazy" decoding="async">', caption, "shot " + cls)


def flow(steps, cls):
    return f'<div class="flow {cls}">' + '<i aria-hidden="true">→</i>'.join(f'<span>{t}</span>' for t in steps) + "</div>"


def note(title, text, kind="lesson"):
    return f'<aside class="note {kind}"><p class="lbl">/{title}</p><p>{text}</p></aside>'


def table(head, rows, cls=""):
    th = "".join(f"<th>{h}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tbl {cls}"><table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>'


def seq():
    lanes = ["Reader", "ask function", "arXiv", "Supabase + Groq"]
    msgs = [(0, 1, "Question about paper 2611.03523"), (1, 3, "Have this paper's sections?"), (3, 1, "No, first question", 1),
            (1, 2, "Fetch the HTML version"), (2, 1, "Full text", 1), (1, 3, "Save sections, pick best 3, ask Groq"),
            (3, 1, "Answer + the sentence it used", 1), (1, 0, "Answer with section and quote", 1)]
    W, top, gap = 760, 66, 44
    xs = [80 + i * (W - 160) / 3 for i in range(4)]
    H = top + gap * len(msgs) + 20
    s = [f'<svg class="seq" viewBox="0 0 {W} {H}" role="img" aria-label="Sequence of a first Ask this paper question">']
    for x, name in zip(xs, lanes):
        s.append(f'<line x1="{x}" y1="46" x2="{x}" y2="{H-8}" class="ln"/><rect x="{x-66}" y="12" width="132" height="34" rx="4" class="ln-box"/>'
                 f'<text x="{x}" y="34" class="ln-t">{name}</text>')
    for i, m in enumerate(msgs):
        a, b, t = m[:3]
        back = len(m) > 3
        y = top + gap * i + 16
        d = 1 if xs[b] > xs[a] else -1
        s.append(f'<line x1="{xs[a]}" y1="{y}" x2="{xs[b]-d*7}" y2="{y}" class="msg{" back" if back else ""}"/>'
                 f'<path d="M{xs[b]} {y} l{-d*8} -4.5 v9 z" class="hd{" back" if back else ""}"/>'
                 f'<text x="{(xs[a]+xs[b])/2}" y="{y-8}" class="mt">{t}</text>')
    s.append("</svg>")
    return "".join(s)


ARCH = """<div class="arch">
<div class="col"><p class="lbl">/GitHub</p>
  <div class="box hot"><b>Actions</b><span>Daily edition · Deploy functions · Full sync · Tests · Weekly code review</span></div>
  <div class="box"><b>Repository</b><span><code>data/daily/*.json</code>, links, lab logos, case studies</span></div>
  <div class="box"><b>Pages</b><span>The static site, RSS feed, sitemap, share images</span></div></div>
<div class="col"><p class="lbl">/Supabase</p>
  <div class="box"><b>Postgres + pgvector</b><span>papers · paper_sections · paper_fulltext · paper_stats · rate_limits</span></div>
  <div class="box hot"><b>Edge Functions</b><span>search · recommend · scout · ask · breakdown · track · embed</span></div></div>
<div class="col"><p class="lbl">/Outside services</p>
  <div class="box"><b>Sources</b><span>arXiv · Hugging Face Papers · Semantic Scholar · OpenAlex · 65 company blogs</span></div>
  <div class="box"><b>Models</b><span>Groq: gpt-oss-120b, gpt-oss-20b as fallback · gte-small embeddings</span></div>
  <div class="box"><b>Reach</b><span>cron-job.org · Buttondown · Umami</span></div></div>
</div>"""

TIMELINE = """<ol class="tl">
<li><code>v0</code><b>A README digest</b><span>Two papers a day written into Markdown in the repo, scored by keyword rules.</span></li>
<li><code>v1</code><b>A website</b><span>A static site on GitHub Pages, with a page for every paper and an RSS feed.</span></li>
<li><code>v2</code><b>A library</b><span>A year of papers in Supabase, searchable by meaning, with For you.</span></li>
<li><code>v3</code><b>Agents</b><span>Ask this paper, Project Scout, the Curator and an LLM judge for the pick.</span></li>
<li><code>v4</code><b>Measured</b><span>A picker backtest, eval sets, reader numbers and a weekly code review agent.</span></li>
</ol>"""

CODE_YML = """<span class="k">on</span>:
  <span class="k">schedule</span>:
    - <span class="k">cron</span>: <span class="s">"30 2 * * *"</span>   <span class="c"># backup, 08:00 IST</span>
  <span class="k">workflow_dispatch</span>:        <span class="c"># the real start: cron-job.org at 01:30 UTC</span>

<span class="k">steps</span>:
  - <span class="k">name</span>: Skip the backup run if today's edition is out
    <span class="k">run</span>: [ -f <span class="s">"data/daily/$today.json"</span> ] &amp;&amp; echo <span class="s">"skip=true"</span>
  - <span class="k">name</span>: Sync to Supabase
    <span class="k">continue-on-error</span>: <span class="s">true</span>      <span class="c"># the site still builds if Supabase is down</span>"""


def video(name, caption, secs):
    return fig(f'<video src="{MEDIA}video/{name}.mp4" poster="{MEDIA}video/{name}.jpg" autoplay muted loop playsinline preload="metadata"></video>'
               f'<span class="vtag">▶ {secs}s · loops</span>', caption, "vid")


def plain(term, text):
    return f'<aside class="plain"><p class="lbl">/In plain words</p><p><b>{term}</b> {text}</p></aside>'


def pix(seed, cols=16, rows=5):
    """A small strip of the cover's pixel art for each tile."""
    rnd = random.Random(seed)
    cells = []
    hot = rnd.randrange(cols // 3, cols - 2)
    for r in range(rows):
        for c in range(cols):
            d = abs(c - hot) + abs(r - rows // 2) * 1.6
            v = max(0, 1 - d / 7) + rnd.random() * .25
            k = "p4" if v > .9 else "p3" if v > .65 else "p2" if v > .4 else "p1" if v > .2 else "p0"
            if c == hot and r == rows // 2:
                k = "pk"
            cells.append(f'<i class="{k}"></i>')
    return f'<div class="pix" style="--cols:{cols}">{"".join(cells)}</div>'


TOC = [("why", "Why I built it"), ("start", "Where it started"), ("what", "What it does"), ("morning", "One morning, step by step"),
       ("pick", "How one paper gets picked"), ("notes", "How the notes are written"), ("labs", "Who wrote the paper"),
       ("library", "The library and search"), ("ask", "Ask this paper"), ("scout", "Project Scout"), ("arch", "How it all fits together"),
       ("trends", "Trends"), ("cases", "Case studies"), ("site", "The website"), ("reach", "Email, RSS and numbers"),
       ("measure", "Checking it works"), ("limits", "Limits and safety"), ("broke", "What broke"), ("lessons", "Lessons"),
       ("next", "What's next"), ("stack", "The tools")]
TOC_HTML = "".join(f'<li><a href="#{i}"{" aria-current=true" if i=="why" else ""}><code>{n:02d}</code>{t}</a></li>' for n, (i, t) in enumerate(TOC, 1))


def h2(i, title):
    n = [k for k, _ in TOC].index(i) + 1
    return f'<h2 id="{i}"><code>{n:02d}</code>{title}</h2>'


SHORT = [("1,000+ → 1", "Every morning it reads every new AI paper and picks the one most worth your time.", 3),
         ("07:00", "The pick arrives on the site and in your inbox, explained in plain words.", 8),
         ("0 servers", "A static website plus a few small cloud functions. Nothing to keep running.", 13),
         ("Checked", "Every AI step is checked before anything is published, and none can stop the edition.", 21)]
short = "".join(f'<div class="tile">{pix(s)}<b>{n}</b><p>{t}</p></div>' for n, t, s in SHORT)

compare = (f'<div class="cmp"><div><p class="lbl">Before</p>{flow(["Open arXiv", "Skim ~300 titles", "Open 20 abstracts", "Maybe read one"], "slow")}'
           f'<p class="cmp-t">~45 min</p></div><div><p class="lbl lbl-on">With AI Papers Daily</p>'
           f'{flow(["Email at 07:00", "Read the pick in 1 minute", "Ask it a question", "Build"], "fast")}<p class="cmp-t on">~2 min</p></div></div>')

SCORE = table(["Signal", "Why it counts", "How much"], [
    ["Upvotes on Hugging Face", "Other researchers found it worth reading", "Each time upvotes double, the same number of points"],
    ["On Hugging Face's daily list", "A person picked it by hand", "A fixed bonus"],
    ["Released code", "You can actually try it", "About as much as doubling the upvotes"],
    ["A named lab", "We know who wrote it, from real evidence", "A bit more for a well-known lab"],
    ["Spans two topics", "Ideas that cross fields are often useful", "A small bonus"]])


def _article(actions: str) -> str:
    """The hero and the article, up to the end of the last section. Figures are numbered from 1 on every call."""
    N["fig"] = 0
    return f"""
<section class="hero in">
  <p class="crumb"><a href="index.html">Case studies</a> <span>/</span> Behind the build</p>
  <h1>How I built AI Papers Daily</h1>
  <p class="deck">Every morning a small program reads every new AI research paper, picks the one most worth your time, and explains it in plain words. Here is how every part of it works, step by step, with short videos of each flow.</p>
  <dl class="meta">
    <p class="lbl">/Metadata</p>
    <div><dt>Date</dt><dd><time datetime="{PUBLISHED}">{PUBLISHED.replace("-", ".")}</time></dd></div>
    <div><dt>Author</dt><dd><a href="#author">Prathamesh Salokhe</a></dd></div>
    <div><dt>Reading time</dt><dd>25 min read</dd></div>
    <div><dt>Built with</dt><dd>Python · GitHub · Supabase · Groq</dd></div>
  </dl>
  {actions}
</section>

<div class="cover in">{art(3)}<span class="fig-n on-art">[ Fig. 0 ] One square per paper from a single morning. The yellow one is the pick.</span></div>

<section class="short in"><p class="lbl">/The short version</p><div class="tiles">{short}</div></section>

<div class="body in">
<aside class="toc"><p class="lbl">/Article</p><ol>{TOC_HTML}</ol></aside>
<article>

{h2("why", "Why I built it")}
<p class="lede">Hundreds of new AI papers come out every day. Most people never read past the titles, and I was one of them.</p>
<p>The lists I tried either showed everything or showed whatever was most hyped. I wanted something smaller: <mark>one paper a day, picked for people who build things</mark>, with notes that say what I could actually do with it.</p>
<p>I couldn't find that, so I built it.</p>
{fig(compare, "Finding one good paper used to take most of an hour. Now it arrives already explained.")}

{h2("start", "Where it started")}
<p>The first version wasn't even a website. It was a page of text on GitHub that rewrote itself every morning with two papers and one line about each.</p>
<p>It worked, but not well:</p>
<ul class="feat">
<li><b>The summaries were broken.</b> For days the AI step had been failing quietly, so every "summary" was just a sentence copied from the paper.</li>
<li><b>The ranking rewarded buzzwords.</b> Papers got points for saying "novel", and nearly every paper says "novel".</li>
<li><b>Nobody could find it.</b> You had to remember to open GitHub every day.</li>
</ul>
<p>So I set three goals, in order: make the picks good, bring them to where people already are, and give readers something the plain lists don't.</p>
{fig(TIMELINE, "How the project grew. Each step kept the one before it working.", "pad")}

{h2("what", "What it does")}
<p>The daily pick is still the heart of it. Around it the site grew into a small research tool:</p>
<ul class="feat">
<li><b>Today's picks.</b> The best new paper, plus the one other researchers are upvoting most.</li>
<li><b>A page for every paper.</b> Notes at three levels (new to this, practitioner, researcher), a one-question quiz, the paper's own results and limits, and links to its code.</li>
<li><b>Ask this paper.</b> Ask a question and get an answer from the full paper, with the exact sentence it came from.</li>
<li><b>Search by meaning.</b> Over 8,000 papers from the last year. Type an idea, not exact words.</li>
<li><b>Papers by lab.</b> See which company or university wrote each paper.</li>
<li><b>Project Scout.</b> Describe what you want to build and get a reading list for it.</li>
<li><b>Trends, Case studies, For you and Saved.</b> Charts of a year of research, how companies use AI, suggestions from what you read, and your saved papers and notes.</li>
<li><b>Email and RSS.</b> The two picks every morning, wherever you read.</li>
</ul>
{shot("paper.png", "A paper page", "A paper page: upvotes, reading level, and links to the PDF, the code and Hugging Face.")}
<div class="two">
{shot("ask.png", "Ask this paper", "Ask this paper shows the sentence each answer comes from.", "tall")}
{shot("papers.png", "All papers", "All papers: one line on every paper, with its topic, upvotes and whether it has code.")}
</div>

{h2("morning", "One morning, step by step")}
<p>Everything starts at 07:00 India time, when a scheduled job wakes up on GitHub. Watch the whole morning first, then each step is explained below.</p>
{video("morning", "One morning in 13 seconds: read every new paper, sort, score, judge, pick, send.", 13)}
<ol class="walk">
<li><b>Fetch.</b> It downloads every new paper from arXiv (where researchers post papers) and Hugging Face's daily list. On a busy day that's over 1,000 papers. Papers picked in the last week are skipped.</li>
<li><b>Sort.</b> Each paper is put into up to 3 of 13 topics, like "LLMs" or "Computer vision", based on the words in its title and summary.</li>
<li><b>Score.</b> Every paper gets points for real evidence that it's good. The best 200 are saved and the top 6 go on to the judge.</li>
<li><b>Judge.</b> An AI compares the 6 two at a time. More on this below.</li>
<li><b>Pick.</b> The winner becomes today's pick. The most upvoted paper from a different topic becomes "Trending".</li>
<li><b>Send.</b> The AI writes notes for both picks, the website is rebuilt, and the email goes out.</li>
</ol>
{plain("A scheduled job", "is a program that runs by itself at a set time. Here it is a GitHub Actions workflow: GitHub lends a computer for a few minutes each morning, runs the steps, and saves the results back into the project.")}

{h2("pick", "How one paper gets picked")}
<p>This is the part I rewrote the most. The first version gave points for words like "novel" and "state of the art". Since nearly every paper says those, the points meant nothing.</p>
<p>Now a paper only gets points for <mark>evidence that it's good</mark>:</p>
{SCORE}
<p>Then comes the judge. If you ask an AI "score this paper out of 100", you get a different number every time. If you ask "which of these two should a builder read first?", it answers much more consistently. So the judge does exactly that, for every pair.</p>
{video("judge", "The judge: 6 papers, 15 head-to-head matches, and the most wins becomes the pick.", 13)}
<ul class="feat">
<li><b>15 matches.</b> 6 papers make 15 pairs. Each match looks at four things: is it new, are the results strong, can you reproduce it, and is it useful.</li>
<li><b>Fair sides.</b> Which paper is shown first is shuffled, so the AI can't favour the first one.</li>
<li><b>A safe fallback.</b> If more than a quarter of the matches fail, for example because the AI service is down, the points decide instead.</li>
</ul>
<p>How do I know the picks are good? I built a <b>backtest</b>: it replays every past day and checks whether the pick was one of that day's most upvoted papers a few days later.</p>
{table(["Way of picking", "Pick was in the day's top 10", "Share of the best paper's upvotes"], [
    ["Random", "9%", "–"], ["Old points system", "4 of 4", "0.88"], ["New points system", "4 of 4", "0.85"], ["Picking a day later", "3 of 3", "0.94"]], "num")}
<p class="small">Only a few days so far, so these numbers are rough. Picking a day later, once upvotes have built up, looks best so far, so it's a one-line setting.</p>
{plain("A backtest", "means testing a rule on the past. Instead of guessing whether a change makes the picks better, I run it on every saved day and compare.")}

{h2("notes", "How the notes are written")}
<p>Each pick gets notes: a one-line summary, what's new, the key result, ideas for what to build, and how hard it is. An AI writes them, and <mark>nothing is published until it passes a check</mark>.</p>
{video("curator", "The notes check, as an illustrated example: draft, check every field, rewrite only what failed, then fact-check.", 11)}
<ol class="walk">
<li><b>Draft.</b> The AI writes all the notes in one go.</li>
<li><b>Check.</b> Code checks every field: is it too long, is anything missing, and does it mention a number that isn't in the paper?</li>
<li><b>Repair.</b> Only the fields that failed go back to the AI, with the reason. At most twice.</li>
<li><b>Fact-check.</b> A second, smaller AI checks each fact against the paper's summary.</li>
</ol>
<p>Two more rules: links to code never come from the AI, because it could make one up. And if the notes still fail, the paper gets a simple one-line summary instead, so the morning edition always goes out.</p>
{plain("An agent", "here is a short chain of steps around an AI call, with checks and retries in between. I build them with a library called LangGraph, which draws each chain as a small map of steps.")}

{h2("labs", "Who wrote the paper")}
<p>Showing the lab behind each paper sounds easy, but it's easy to get wrong. Papers mention other labs all the time ("we compare with OpenAI's GPT-4o"), and that says nothing about who wrote them. So a lab is only shown when there is direct evidence, checked in this order:</p>
<ol class="steps"><li>The lab claimed the paper on Hugging Face</li><li>The paper's code lives in the lab's GitHub account</li><li>The paper says so ("Work done at Meta")</li><li>The authors' listed universities or companies</li></ol>
<p>Each lab's logo is found once, from a free icon set, the lab's own profile pages or Wikipedia's data, and saved with the project, so pages never load images from other sites. It is better to show no lab than the wrong one.</p>
{shot("labs.png", "Papers by lab", "Papers by lab, with each lab's own logo.")}

{h2("library", "The library and search")}
<p>Search needs more than one morning of papers, so a one-time job loaded a year of Hugging Face's daily lists into a database called Supabase, and each morning adds the new day. That's how the library passed 8,000 papers.</p>
<p>To search by meaning, each paper is turned into a list of numbers that captures what it's about. Papers about similar ideas get similar numbers, even when they use different words.</p>
{plain("An embedding", "is that list of numbers. When you search, your words are turned into numbers the same way, and the database returns the papers whose numbers are closest. That's how “run a model on a phone” finds papers about quantization.")}
{table(["Table", "What it holds"], [["<code>papers</code>", "Every paper, its numbers for search, topics and links"], ["<code>paper_fulltext</code>", "Full papers read for Ask, deleted after 30 days if nobody asks"],
    ["<code>paper_sections</code>", "Those papers split into sections"], ["<code>paper_stats</code>", "Anonymous view counts and “worth it” votes"], ["<code>rate_limits</code>", "How often each visitor can use each feature per hour"]])}

{h2("ask", "Ask this paper")}
<p>You can ask any paper a question. The first question is the slow one, because the full paper has to be read first.</p>
{video("ask", "Ask this paper: read the paper once, find the 3 best sections, answer with the exact sentence used.", 12)}
<ol class="walk">
<li><b>Read once.</b> The full paper is fetched from arXiv, split into sections and saved. Today's picks are read in advance, so they're fast from the first question.</li>
<li><b>Find.</b> Your question is matched against the sections, and the 3 closest ones are kept.</li>
<li><b>Answer.</b> The AI answers from those sections only, and shows the sentence it relied on, so you can check it.</li>
</ol>
{fig(seq(), "The same flow as a diagram. From the second question on, the arXiv step is skipped.", "pad")}

{h2("scout", "Project Scout")}
<p>Scout is for when you know what you want to build but not what to read.</p>
{video("scout", "Project Scout, with an example project: split it into needs, search each, search again if needed, get a reading plan.", 13)}
<ol class="walk">
<li><b>Split.</b> The AI breaks your project into the parts it needs. You can edit them.</li>
<li><b>Search.</b> Each part is searched by meaning and by keywords, and the results are merged.</li>
<li><b>Score.</b> The AI rates how well each paper fits and says why in one line.</li>
<li><b>Search again.</b> If a part has no strong paper, it tries once more with better words, and tells you it did.</li>
<li><b>Plan.</b> You get a reading plan: start here, build on these, read later.</li>
</ol>
{shot("scout.png", "Scout's step map and a run log", "Scout's steps as a map, with a real run log beside it.")}

{h2("arch", "How it all fits together")}
<p>Now that you've seen each part, here is the whole picture. It is three simple things: <mark>a scheduled job, a folder of files, and a website</mark>, plus a database for the parts that have to answer you live.</p>
<ul class="feat">
<li><b>The files are the archive.</b> Each morning saves one file with every paper it looked at. The website, the email and the feed are all built from those files, so any past day can be rebuilt or re-tested.</li>
<li><b>The website is static.</b> It is plain pages, made once each morning, so there is nothing that can crash at night.</li>
<li><b>Live features are small functions.</b> Search, Ask, Scout and the view counts call small functions in Supabase straight from your browser.</li>
</ul>
{fig(ARCH, "Everything that runs. Orange boxes run code; the rest store or serve things.", "pad")}
{plain("A static site", "is a website made of ready-made pages, like printed sheets. Nothing is calculated when you open a page, so it's fast, cheap to host and very hard to break.")}

{h2("trends", "Trends")}
<p>The Trends page shows a year of AI research as charts, drawn by the build script itself, so the site needs no chart library. Two rules keep the charts honest:</p>
<ul class="feat"><li><b>One steady source.</b> The trend lines use Hugging Face's daily lists for the whole year. Mixing in my own newer data would make recent weeks look bigger than they are.</li>
<li><b>Shares, not counts.</b> A topic is "growing" only if its share of all papers grew, comparing the last 90 days with the 90 before. Very small topics get no growth number at all.</li></ul>
{shot("trends.png", "Technologies to watch", "Technologies to watch, ranked by their share of recent papers.")}

{h2("cases", "Case studies")}
<p>Papers show what's possible. Company engineering blogs show what actually shipped. Twice a week the job reads 65 company blogs, and the AI decides if each new post explains how a company built something with AI. If it does, the post gets a topic, up to 3 technique tags and a short summary in our own words, and the card links to the original. You are reading the one case study that isn't from someone else's blog.</p>
{shot("cases.png", "The Case studies page", "Case studies: every card opens the company's own post.")}

{h2("site", "The website")}
<p>The whole site is made by one Python script, about 1,800 lines, with plain JavaScript and no framework. Every page works in light and dark mode, and on phones the menu moves to the bottom of the screen.</p>
<p>The design idea was <mark>"a research terminal, not a blog"</mark>. Orange marks what matters most, like today's pick. Yellow marks what you chose, like your highlights. Your saved papers, notes and highlights stay in your own browser, so there's no account to make.</p>
<div class="two">{shot("phone.png", "On a phone", "On a phone.", "tall")}{shot("papers.png", "On a desktop", "On a desktop.")}</div>

{h2("reach", "Email, RSS and numbers")}
<ul class="feat">
<li><b>Email.</b> The email service's automatic option costs money, but sending through its API is free, so the morning job sends the email itself. It is built from simple tables, because that's what Gmail and Outlook show reliably, and it can never be sent twice in one day.</li>
<li><b>RSS, sitemap and share images.</b> Every paper page gets its own preview image for when it's shared.</li>
<li><b>Numbers without cookies.</b> The site counts visits, clicks on the pick against Trending, answers to "have you seen this paper before?" and returning readers, all as daily totals with nothing about you.</li>
</ul>

{h2("measure", "Checking it works")}
<p>Changing a prompt used to be a guess. Now there are fixed tests, so every change can be measured before and after.</p>
{table(["What", "How it's checked"], [
    ["The pick", "The backtest: compare each past pick with upvotes a few days later"],
    ["Project Scout", "26 example projects with papers we know are right. Is a right paper in the top 10, and how high?"],
    ["Ask this paper", "30 questions on 6 papers, 5 of them impossible to answer. Does it quote the paper, is it right, and does it admit when it can't answer?"],
    ["Readers", "Pick vs Trending clicks, “seen it before?” answers and returning readers, in one report"],
    ["The code", "Every Monday an AI reviews the week's changes, runs the tests, and opens up to 3 issues for likely bugs"]])}
{note("Lesson", "Every change to the picks went through the backtest first. Without it I would have kept the old buzzword points forever, because the picks looked fine at a glance.")}

{h2("limits", "Limits and safety")}
<ul class="feat"><li>Each visitor can only use each live feature a set number of times per hour, so the bill can't run away.</li><li>Only the morning job can add papers to the database.</li>
<li>If the AI service is down, Scout still shows its search results, marked as not checked.</li><li>Every page says the notes are written by AI and should be checked against the paper.</li></ul>

{h2("broke", "What broke")}
<p>Most of the work after launch went into one thing: the edition arriving on time, every day.</p>
<ol class="broke">
<li><b>GitHub's timer runs late.</b> Scheduled jobs often started hours after 07:00. Now a free outside timer (cron-job.org) starts the job at exactly 07:00, and GitHub's own timer stays as a backup that does nothing if the edition is already out.</li>
<li><b>The AI failed quietly.</b> For days, every summary was a fallback and nothing said so. Now there are backup AI models, and the notes check catches a bad answer instead of publishing it.</li>
<li><b>Other services go down.</b> The links, the case studies, the database update and the email are all allowed to fail. The site still builds from what's already saved.</li>
<li><b>Old pages lost their data.</b> A stats file was being rebuilt wrongly, so topic pages lost every day but the newest. Rebuilding from the daily files fixed it for good.</li>
</ol>
{fig(f'<pre><code>{CODE_YML}</code></pre>', "From the morning job's settings: the on-time start, the backup that steps aside, and a step that's allowed to fail.", "code")}

{h2("lessons", "Lessons")}
<ol class="lessons">
<li><b>Let every step fail.</b> The morning edition matters more than any one feature in it.</li>
<li><b>Keep the data as files.</b> Every day can be rebuilt, compared and re-tested.</li>
<li><b>Count evidence, not buzzwords.</b> For ranking papers, and for naming labs.</li>
<li><b>Ask the AI easy questions.</b> "Which of these two?" beats "score out of 100".</li>
<li><b>Measure before you change.</b> A small test beats a strong opinion.</li>
</ol>

{h2("next", "What's next")}
<p>Ideas on the list: a weekly top-10, feeds for each topic, a short audio version of the morning edition, and using readers' "worth it" votes in the ranking.</p>

{h2("stack", "The tools")}
{table(["Part", "Built with"], [["The morning job", "Python, LangGraph, GitHub Actions, arXiv, Hugging Face, Semantic Scholar, OpenAlex"],
    ["AI", "Groq running gpt-oss-120b, with gpt-oss-20b as backup · gte-small for search · LangChain and LangSmith"],
    ["Database and live features", "Supabase: Postgres, pgvector, Edge Functions in TypeScript"],
    ["Website", "Plain HTML, CSS and JavaScript, charts drawn as SVG, hosted on GitHub Pages"], ["Delivery", "cron-job.org, Buttondown for email, Umami for visit counts"]])}

"""


def _esc(text) -> str:
    return html.escape(str(text or ""), quote=True)


def _actions(page_url: str) -> str:
    share = f"https://x.com/intent/post?text={_q(TITLE)}&url={_q(page_url)}"
    linked = f"https://www.linkedin.com/sharing/share-offsite/?url={_q(page_url)}"
    devto = f'<a class="ghost" href="{_esc(DEVTO_URL)}" rel="noopener">Read on dev.to {ARROW}</a>' if DEVTO_URL else ""
    return (f'<div class="acts"><button class="ghost" type="button" data-copy-md="{SLUG}.md">Copy for LLM</button>'
            f'<a class="ghost" href="{SLUG}.md">View as Markdown</a>{devto}'
            f'<span class="share">Share: <a href="{_esc(share)}" rel="noopener" target="_blank">X</a> '
            f'<a href="{_esc(linked)}" rel="noopener" target="_blank">LinkedIn</a></span></div>')


def _q(text: str) -> str:
    return quote(text, safe="")


def _related(posts: list[dict]) -> str:
    """Three of the newest company write-ups, each with its own pixel cover, linking to the company's post."""
    picked, seen = [], set()
    for p in posts:  # the newest post from each of three different companies
        if p.get("url") and p.get("title") and p.get("company") not in seen:
            picked.append(p)
            seen.add(p.get("company"))
        if len(picked) == 3:
            break
    cards = []
    for i, p in enumerate(picked, 1):
        tags = " · ".join(t for t in (p.get("tags") or [])[:2] if isinstance(t, str)) or _esc(p.get("company"))
        cards.append(f'<a href="{_esc(p["url"])}" rel="noopener" target="_blank"><div class="rel-art">{art(7 + i * 4, 600, 260, 30, 13)}'
                     f'<span class="fig-n on-art">{_esc(p.get("company"))}</span></div><b>{_esc(p["title"])}</b>'
                     f'<span>{_esc(tags)}</span></a>')
    if not cards:
        return ""
    return (f'<section class="related in"><p class="lbl">/Related articles</p><div class="rel">{"".join(cards)}</div>'
            f'<p class="rel-all"><a href="index.html">All case studies {ARROW}</a></p></section>')


def _tail() -> str:
    devto = f'<li><a href="{_esc(DEVTO_URL)}" rel="noopener">This post on dev.to {ARROW}</a></li>' if DEVTO_URL else ""
    return f"""
<div class="cta"><div><b>Get the pick every morning</b><span>One paper, explained, at 07:00 IST.</span></div><a class="btn" href="../index.html#subscribe">Subscribe {ARROW}</a></div>

<section id="author" class="author"><p class="lbl">/About the author</p>
<div class="who"><span class="av">PS</span><div><h3>{AUTHOR}</h3><p>Builds AI Papers Daily.</p></div></div></section>
<section class="res"><p class="lbl">/Additional resources</p><ul><li><a href="{REPO_URL}" rel="noopener">Source code on GitHub {ARROW}</a></li>{devto}
<li><a href="../papers.html">Search 8,000+ papers {ARROW}</a></li><li><a href="../scout.html">Try Project Scout {ARROW}</a></li></ul></section>"""


SCRIPT = """<script>
(function(){
var bar=document.querySelector('.prog'),links=[].slice.call(document.querySelectorAll('.toc a')),
heads=links.map(function(a){return document.getElementById(a.hash.slice(1))});
function on(){var h=document.documentElement,max=h.scrollHeight-h.clientHeight;
if(bar)bar.style.width=(max>0?h.scrollTop/max*100:0)+'%';
var cur=0;heads.forEach(function(e,i){if(e&&e.getBoundingClientRect().top<140)cur=i});
links.forEach(function(a,i){if(i===cur)a.setAttribute('aria-current','true');else a.removeAttribute('aria-current')})}
addEventListener('scroll',on,{passive:true});on();
var copy=document.querySelector('[data-copy-md]');
if(copy)copy.addEventListener('click',function(){fetch(copy.dataset.copyMd).then(function(r){return r.text()})
.then(function(t){return navigator.clipboard.writeText(t)}).then(function(){copy.textContent='Copied'},
function(){location.href=copy.dataset.copyMd})});
if(matchMedia('(prefers-reduced-motion: reduce)').matches)document.querySelectorAll('video[autoplay]').forEach(function(v){
v.removeAttribute('autoplay');v.pause();v.controls=true});
})();
</script>"""


def page_html(posts: list[dict], site_url: str, theme_script: str = "", head_extra: str = "") -> str:
    """The whole page. posts are the site's case studies, newest first, for the related articles."""
    url = f"{site_url}case-studies/{SLUG}.html"
    body = _article(_actions(url)) + _tail()
    image = f"{site_url}assets/making-of/video/morning.jpg"
    ld = ('{"@context":"https://schema.org","@type":"TechArticle","headline":' + _json(TITLE) +
          ',"description":' + _json(DESCRIPTION) + ',"datePublished":"' + PUBLISHED + '","author":{"@type":"Person","name":' +
          _json(AUTHOR) + '},"image":' + _json(image) + ',"mainEntityOfPage":' + _json(url) + "}")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
{theme_script}
<title>{TITLE} · AI Papers Daily</title>
<meta name="description" content="{_esc(DESCRIPTION)}">
<link rel="canonical" href="{_esc(url)}">
<link rel="alternate" type="text/markdown" href="{SLUG}.md">
<meta name="author" content="{AUTHOR}">
<meta property="og:type" content="article"><meta property="og:site_name" content="AI Papers Daily">
<meta property="og:title" content="{TITLE}"><meta property="og:description" content="{_esc(DESCRIPTION)}">
<meta property="og:url" content="{_esc(url)}"><meta property="og:image" content="{_esc(image)}">
<meta property="article:published_time" content="{PUBLISHED}">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#ff4f00">
<link rel="preload" href="../assets/fonts/geist.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="../assets/making-of.css">
<script type="application/ld+json">{ld}</script>{head_extra}
</head><body class="mo">
<div class="prog" aria-hidden="true"></div>
<header class="top"><div class="in">
  <a class="home" href="../index.html"><span class="mk"></span>AI Papers Daily<span class="sl">/</span><span class="mut">Case studies</span></a>
  <nav aria-label="Main"><a href="../index.html"><kbd>T</kbd>Today</a><a href="../papers.html"><kbd>P</kbd>Papers</a><a href="../scout.html"><kbd>S</kbd>Scout</a><a href="index.html" aria-current="page"><kbd>C</kbd>Case studies</a></nav>
  <a class="btn" href="../index.html#subscribe">Get the daily email</a>
</div></header>
<main>{body}
</article>
</div>
{_related(posts)}</main>
<footer class="foot"><div class="in">
<div><p class="lbl">/Papers</p><a href="../index.html">Today</a><a href="../papers.html">All papers</a><a href="../scout.html">Scout</a></div>
<div><p class="lbl">/Read more</p><a href="index.html">Case studies</a><a href="../feed.xml">RSS feed</a><a href="../index.html#subscribe">Daily email</a></div>
<div><p class="lbl">/Source</p><a href="{REPO_URL}" rel="noopener">GitHub</a>{f'<a href="{_esc(DEVTO_URL)}" rel="noopener">dev.to</a>' if DEVTO_URL else ""}</div>
<p class="copy">Built from arXiv and Hugging Face Papers. Summaries are written by AI; check the paper before you rely on them.</p>
</div></footer>
{SCRIPT}
</body></html>"""


def _json(text: str) -> str:
    import json
    return json.dumps(text, ensure_ascii=False).replace("</", "<\\/")


# ---------- Markdown copy

class _MD(HTMLParser):
    """Turns this page's article into Markdown. It only needs to understand the tags the article uses."""
    VOID = {"img", "br", "hr", "meta", "link", "input", "source"}

    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base, self.out, self.skip, self.lists, self.links, self.ends = base, [], 0, [], [], []
        self.cell, self.row, self.rows, self.pre, self.inline = None, None, [], False, 0

    def _w(self, text: str):
        (self.cell if self.cell is not None else self.out).append(text)

    def _skipped(self, tag: str, cls: str) -> bool:
        return (tag in ("svg", "script", "style", "button", "dl", "nav")
                or (tag in ("div", "aside", "p", "span") and any(c in cls.split() for c in
                    ("toc", "acts", "crumb", "pix", "vtag", "fig-n", "prog", "av"))))

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if self.skip:
            self.skip += tag not in self.VOID
            return
        if self._skipped(tag, cls) or (tag == "code" and self.ends and self.ends[-1] == "h2"):
            self.skip = 1
            return
        end = ""
        if tag in ("h1", "h2", "h3"):
            self._w("\n\n" + "#" * int(tag[1]) + " ")
            end = tag
        elif tag == "code" and not self.pre:
            self._w("`")
            end = "`"
        elif tag == "p":
            if self.inline:
                self._w(" ")
            elif not self.lists:
                self._w("\n\n")
            if "lbl" in cls.split():
                self._w("**")
                end = "**"
        elif tag in ("b", "strong", "mark"):
            self._w("**")
            end = "**"
        elif tag == "i":
            self._w(" ")
            end = " "
        elif tag == "span" and (self.lists or "".join(self.out[-1:]).endswith("**")):
            self._w(": ")  # a label and its text: "**Actions**: Daily edition ..."
        elif tag == "div" and "tile" in cls.split():
            self._w("\n- ")
            self.inline += 1
            end = "inline"
        elif tag == "div" and not self.inline:
            self._w("\n\n")
        elif tag in ("ul", "ol"):
            self.lists.append([tag, 0])
            self._w("\n")
            end = "list"
        elif tag == "li":
            kind = self.lists[-1] if self.lists else ["ul", 0]
            kind[1] += 1
            self._w("\n" + (f"{kind[1]}. " if kind[0] == "ol" else "- "))
        elif tag == "a":
            self.links.append(a.get("href") or "")
            self._w("[")
            end = "a"
        elif tag == "img":
            self._w(f"\n\n![{a.get('alt', '')}]({self._abs(a.get('src', ''))})")
        elif tag == "video":  # Markdown can't play a video: show its first frame, linked to the video
            self._w(f"\n\n[![Video: click to play]({self._abs(a.get('poster', ''))})]({self._abs(a.get('src', ''))})")
        elif tag == "figcaption":
            self._w("\n\n*")
            end = "*"
        elif tag == "pre":
            self.pre = True
            self._w("\n\n```\n")
            end = "pre"
        elif tag == "aside":
            self._w("\n\n>")
            self.inline += 1
            end = "inline"
        elif tag == "table":
            self.rows = []
            end = "table"
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = []
            end = "cell"
        if tag not in self.VOID:
            self.ends.append(end)

    def handle_endtag(self, tag):
        if self.skip:
            self.skip -= tag not in self.VOID
            return
        if tag in self.VOID or not self.ends:
            return
        end = self.ends.pop()
        if end in ("**", "`", "*", " "):
            self._w(end)
        elif end == "inline":
            self.inline -= 1
        elif end == "list":
            self.lists.pop()
            self._w("\n")
        elif end == "a":
            self._w(f"]({self._abs(self.links.pop())})")
        elif end == "pre":
            self.pre = False
            self._w("\n```")
        elif end == "cell":
            self.row.append(re.sub(r"\s+", " ", "".join(self.cell)).strip().replace("|", "\\|"))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        elif end == "table" and self.rows:
            w = max(len(r) for r in self.rows)
            rows = [r + [""] * (w - len(r)) for r in self.rows]
            lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * w] + ["| " + " | ".join(r) + " |" for r in rows[1:]]
            self._w("\n\n" + "\n".join(lines))

    def handle_data(self, data):
        if not self.skip:
            self._w(data if self.pre else re.sub(r"\s+", " ", data))

    def _abs(self, url: str) -> str:
        return urljoin(self.base, url) if url else url

    def text(self) -> str:
        md = "".join(self.out)
        md = re.sub(r"\*\* +", "** ", md).replace("`**", "` **").replace(")[", ") [")
        md = re.sub(r"[ \t]+\n", "\n", md)
        md = re.sub(r"\n{3,}", "\n\n", md)
        return md.strip() + "\n"


def markdown(site_url: str) -> str:
    """The article as Markdown, with links made absolute so it can be pasted anywhere (dev.to, an LLM chat)."""
    article = _article(_actions(f"{site_url}case-studies/{SLUG}.html")) + _tail()
    article = article[article.index("<h1>"):]
    parser = _MD(f"{site_url}case-studies/")
    parser.feed(article)
    front = (f"---\ntitle: {TITLE}\npublished: false\ndescription: {DESCRIPTION}\ntags: ai, python, langgraph, webdev\n"
             f"canonical_url: {site_url}case-studies/{SLUG}.html\n---\n\n")
    return front + parser.text()


# ---------- the card on the Case studies page

def card() -> str:
    """The pixel-art card that leads the Case studies page."""
    return f"""<li class="cs-own"><a href="{SLUG}.html"><div class="cs-own-cv">{art(3, 600, 420, 44, 30)}<span class="cs-own-tag"><span class="cs-own-mk"></span>Behind the build</span></div>
<div class="cs-own-bd"><p class="cs-own-lbl">/AI Papers Daily · {_nice(PUBLISHED)}</p><h3>{TITLE}</h3>
<p class="cs-own-d">{_esc(CARD_TEXT)}</p>
<div class="cs-own-chips"><span>▶ {len(VIDEOS)} videos</span><span>{READ_MIN} min read</span><span>Agents · RAG · Evaluation</span></div>
<p class="cs-own-go"><span>Read the case study</span>{ARROW}</p></div></a></li>"""


def _nice(day: str) -> str:
    y, m, d = (int(x) for x in day.split("-"))
    return f"{d} {('Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split())[m - 1]} {y}"


def build(write, site_dir: str, site_url: str, posts: list[dict] = (), theme_script: str = "", head_extra: str = "") -> list[str]:
    """Write the page and its Markdown copy into site_dir/case-studies/. Returns the page path for the sitemap."""
    folder = os.path.join(site_dir, "case-studies")
    write(os.path.join(folder, f"{SLUG}.html"), page_html(list(posts), site_url, theme_script, head_extra))
    write(os.path.join(folder, f"{SLUG}.md"), markdown(site_url))
    return [f"case-studies/{SLUG}.html"]
