<div align="center">

<a href="https://omen-bit.github.io/ai-paper-daily/">
  <img src="docs/logo.svg" alt="AI Papers Daily logo" width="84" height="84">
</a>

<h1>AI Papers Daily</h1>

<p><strong>Papers worth building on.</strong><br>
The best new AI paper each day, plus the one everyone is reading,<br>explained so you can build with it.</p>

<p>
  <a href="https://omen-bit.github.io/ai-paper-daily/"><img src="https://img.shields.io/badge/live%20site-omen--bit.github.io-ff4f00?style=flat-square" alt="Live site"></a>
  <a href="https://github.com/Omen-bit/ai-paper-daily/actions/workflows/daily-digest.yml"><img src="https://img.shields.io/github/actions/workflow/status/Omen-bit/ai-paper-daily/daily-digest.yml?branch=main&label=daily%20edition&style=flat-square" alt="Daily edition"></a>
  <a href="https://github.com/Omen-bit/ai-paper-daily/actions/workflows/tests.yml"><img src="https://img.shields.io/github/actions/workflow/status/Omen-bit/ai-paper-daily/tests.yml?branch=main&label=tests&style=flat-square" alt="Tests"></a>
  <img src="https://img.shields.io/badge/python-3.11+-3776ab?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-111111?style=flat-square" alt="MIT license"></a>
</p>

<h3>
  <a href="https://omen-bit.github.io/ai-paper-daily/">Open the site</a>
  &nbsp;·&nbsp;
  <a href="https://omen-bit.github.io/ai-paper-daily/scout.html">Try Project Scout</a>
  &nbsp;·&nbsp;
  <a href="https://omen-bit.github.io/ai-paper-daily/feed.xml">RSS feed</a>
</h3>

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/home-dark.png">
  <img src="docs/screenshots/home.png" alt="The AI Papers Daily home page with today's pick and the trending paper" width="900">
</picture>

</div>

<br>

Hundreds of AI papers land on arXiv every day, and most people never get past the titles.

AI Papers Daily reads all of them every morning and publishes a small edition: **one top pick**, ranked by a published formula over measured signals (GitHub, Hugging Face, Hacker News, Semantic Scholar), not by an LLM, and **one trending paper** the community is upvoting on Hugging Face. Each one is explained in plain words, from a ten-second summary to what you would need to build with it.

Behind the picks sits a library of about a year of AI research, **more than 8,000 papers**, that you can search by meaning, question directly and plan projects from.

<div align="center">
<table>
  <tr>
    <td align="center" width="25%"><h3>2</h3>papers picked<br>every morning</td>
    <td align="center" width="25%"><h3>8,000+</h3>papers to search<br>by meaning</td>
    <td align="center" width="25%"><h3>3</h3>depths of notes<br>for every pick</td>
    <td align="center" width="25%"><h3>07:00 IST</h3>new edition<br>every day</td>
  </tr>
</table>
</div>

## Features

### A page for every paper

<img src="docs/screenshots/paper.png" alt="A paper page with upvotes, reading level, links to the PDF, code and Hugging Face" width="100%">

- **Notes at three depths.** Switch between *New to this*, *Practitioner* and *Researcher*, then check yourself with a short quiz question.
- **Ask this paper.** Ask a question and get an answer from the full paper, with the section and the exact sentence it relies on. Select any sentence and press **Ask** to ask about it.
- **The full breakdown.** Contributions, results tables, limitations and conclusion, copied straight from the paper.
- **Where it fits.** Citations from Semantic Scholar, the code, models and demos built on it, and the lab that wrote it.

### Search by meaning

<img src="docs/screenshots/papers-dark.png" alt="The All papers page in dark mode with search, filters and paper cards" width="100%">

Search by idea, not keyword: *"run a model on a phone"* finds quantization and distillation papers even when they never use those words. Narrow the list by topic, or show only this week's top papers, our picks, papers with code, papers not yet on Hugging Face, or beginner-friendly ones.

### Papers by lab

<img src="docs/screenshots/labs.png" alt="The By lab page with lab logos and their latest papers" width="100%">

See who is behind each paper, with the lab's own logo, and browse companies, universities, or labs and startups. A lab is only named when Hugging Face, the paper's code or its authors' institutions say so, never guessed from the abstract.

### Project Scout

<img src="docs/screenshots/scout.png" alt="Project Scout: describe a project and get the papers to build on" width="100%">

Describe what you want to build in plain words. Scout splits it into the parts it needs (you can edit them), searches each one by meaning and by keywords, and returns the papers to build on, best first, with one line on why each fits. If part of your project has no good paper, Scout searches once more with better phrases before it says so. Press **Watch this project** to see new papers that match it later.

### And more

| Feature | What it does |
| :-- | :-- |
| **Trends** | A year of AI research in charts: technologies to watch, topic share month by month, momentum by topic and words on the rise. |
| **For you** | Recommendations based on the papers you have opened. |
| **Saved** | Saves, highlights, notes and BibTeX citations, all kept in your browser with no account. |
| **Daily email and RSS** | The top pick and the trending paper in your inbox each morning, or in your feed reader. |
| **Light and dark** | Every page in both themes, and built for phones too. |

<p align="center">
  <img src="docs/screenshots/mobile.png" alt="The home page on a phone" width="260">
  &nbsp;&nbsp;&nbsp;
  <img src="docs/screenshots/mobile-paper.png" alt="A paper page on a phone" width="260">
</p>

> [!NOTE]
> Notes and answers are written from the papers by a language model. Check the paper itself before relying on a claim.

## How it works

Every morning at 01:30 UTC (07:00 IST) the **Daily edition** workflow fetches every new paper, picks two, writes their notes, publishes the site to GitHub Pages and emails the edition. It is started on time by [cron-job.org](https://cron-job.org), with GitHub's own schedule at 02:30 UTC as a backup.

```mermaid
flowchart LR
    A["arXiv<br/>7 ML categories"] --> C["Classify<br/>13 research topics"]
    B["Hugging Face<br/>Daily Papers"] --> C
    C --> S["Evidence<br/>GitHub, HF, HN, S2,<br/>novelty, checked claims"]
    S --> D["Score out of 100<br/>shortlist of 6"]
    D --> J2["LLM tie-break<br/>only within 3 points"]
    J2 --> E["Write notes<br/>draft, check, repair, ground"]
    E --> F[("data/<br/>daily JSON")]
    F --> L["Links and labs<br/>code, citations, logos"]
    F --> G["Sync + embed"]
    G --> H[("Supabase<br/>Postgres + pgvector")]
    L --> J["Build site"]
    F --> J
    H --> J
    J --> K["GitHub Pages"]
    J --> M["Daily email<br/>Buttondown"]
```

The site itself is static. Its live features call **Supabase Edge Functions** straight from the browser:

| Function | Powers | What it does |
| :-- | :-- | :-- |
| `search` | All papers | Finds papers by meaning with vector search |
| `recommend` | For you | Finds papers close to the ones you have read |
| `scout` | Project Scout | A LangGraph agent: splits the project into needs, runs a hybrid search for each, scores every match and says why it fits, then searches again for any need left without a strong paper |
| `ask` | Ask this paper | Reads the full paper from arXiv once, stores it in sections, then answers from the best-matching sections and quotes its source |
| `breakdown` | Paper pages | Copies the contributions, results, limitations and conclusion from the paper once (no LLM), plus a short AI summary for papers without notes |
| `track` | Most read, site numbers | Counts anonymous views, "worth it" votes, clicks on each pick, "seen it before?" answers and returning visitors |
| `embed` | Daily sync | Turns each paper into a `gte-small` vector (pipeline only) |

<details>
<summary><strong>How papers are picked</strong></summary>
<br>

Every paper gets a score out of 100 from public numbers, in four capped groups so no single source decides the pick. The [Methodology page](https://omen-bit.github.io/ai-paper-daily/methodology.html) and `src/scorer.py` have the full formula.

| Group | Max | Signals |
| :--- | ---: | :--- |
| Builder evidence | 40 | Code released, GitHub stars, stars gained since the day before, models / datasets / demos on Hugging Face |
| Community attention | 30 | Hugging Face upvotes, Hacker News points |
| Author track record | 15 | Median author h-index on Semantic Scholar, known lab |
| What the paper shows | 15 | Benchmark results quoted word for word from the abstract, novelty against the last 90 days |

The numbers come from `src/signals.py` (plain HTTP, no AI), saved each day in `data/signals/`. `src/novelty.py` measures how far a paper's words are from the last 90 days of papers (TF-IDF). `src/claims.py` is the LLM's only part in the ranking: it lists the benchmark results an abstract claims, and code keeps a claim only if its sentence and number appear word for word in the abstract. Answers are cached by arXiv ID, so no paper is sent twice. A signal that couldn't be looked up gets the day's median and is marked "estimated", never counted as zero. Every paper page shows "Why this ranked" with these numbers.

The best-scored paper is the pick. The most upvoted of the rest becomes Trending, from a different topic than the pick whenever one has enough upvotes.
Once the site has enough views, the home page shows the week's most read paper in the second slot instead.

Only when the leaders are within 3 points does an LLM judge compare them two at a time to break the tie, and the paper's page says so. Without a Groq key, or with `PICK_JUDGE=off`, the best score is the pick.

**Does it work?** `scripts/scoreboard.py` runs weekly (`scoreboard.yml`) and checks every saved day against what happened 30 days later: Semantic Scholar citations and GitHub stars, not Hugging Face upvotes, which the ranking reads itself. It compares the live ranking with upvotes alone, the earlier scorers and random picks, and with each signal group removed. The results are in `data/scoreboard.json` and on the Methodology page.

By default the picks come from the papers fetched that morning. Set the repository variable `PICK_FROM` to `yesterday` to pick from the previous day's papers instead, once their upvotes have had a day to build up. Run `python scripts/backtest_picker.py --day-late` first to compare the two.

Papers featured in the last seven editions are not picked again. The pipeline reads every new paper in the tracked arXiv categories each day (often over 1,000) and keeps the best 200 in `data/`.

To check how good the picks turn out, `python scripts/backtest_picker.py` replays every saved day and compares each pick with the papers' Hugging Face upvotes a few days later (hit rate in the day's top 10, rank in the pool, and share of the best paper's upvotes).

Each morning `paper_links.py` also gathers citations, code, models and labs into `data/links.json`, and lab logos into `data/logos/`, with no AI. A lab comes from evidence that names it directly: the organization that claimed the paper on Hugging Face, the owner of its GitHub code, the arXiv comment field, or the authors' institutions on OpenAlex. Logos come from [Lobe Icons](https://github.com/lobehub/lobe-icons) for the big AI companies, then Hugging Face, Wikidata, GitHub or the lab's own website, and optionally Logo.dev. Each is saved once in the repo, so pages never load logos from a third party. A new lab is picked up on its own: Lobe Icons matches companies by brand name, and two names that share a Wikidata id ("ucas" and "University of Chinese Academy of Sciences") are shown as one lab.
</details>

<details>
<summary><strong>Is the pick worth reading? How it is measured</strong></summary>
<br>

The site counts, as daily totals with no visitor data:

- clicks on today's pick against clicks on the Trending card,
- answers to "Seen this paper before today?" on each pick,
- visits from new readers, readers back within a week, and readers back after longer.

To read them, run `select * from site_report(28);` in the Supabase SQL editor.
</details>

<details>
<summary><strong>Are Scout and Ask getting better? Eval sets</strong></summary>
<br>

`evals/` holds fixed test sets, so a prompt or model change can be measured before and after:

- `scout_cases.json`: 26 project descriptions, each with the papers in the library that clearly serve it.
- `ask_cases.json`: 30 questions about 6 papers with reference answers, 5 of them questions the paper can't answer.

`python scripts/run_evals.py scout|ask|all` runs them against the live functions and saves the results to `evals/results/`. Scout is scored on whether an expected paper is in the top 10 (hit@10), how high it ranks (MRR), whether it is marked a strong fit, how many of the project's needs come back missing, and how often Scout searched a second round. Ask is scored on whether the answer quotes the paper and whether it is right, graded by an LLM against the reference; for a question the paper can't answer, right means saying so. Add `--langsmith` to log the run as a LangSmith experiment and compare runs side by side. With `SYNC_SECRET` in `.env` the hourly limits are skipped; without it the script paces itself.
</details>

<details>
<summary><strong>Limits and safety</strong></summary>
<br>

- Every public function has a per-visitor hourly limit.
- `embed` only accepts calls carrying the pipeline's `SYNC_SECRET`; calls with it also skip the hourly limits.
- If the LLM is unavailable, Scout still returns its search results, marked as not checked.
- AI summaries in `breakdown` are capped per day; past the cap the page shows the breakdown without one.
- Stored full texts that nobody has asked about for 30 days are removed by the daily run.
</details>

### The Weekly Express (Sundays)

On Sundays the daily email is replaced by **The Weekly Express**, a newspaper-style email with the week's five most upvoted new papers, the case studies published that week and a few numbers. `src/weekly_edition.py` builds it in three steps around one file per week, `data/weekly/<YYYY>-W<NN>.json`:

1. **Collect** (no AI): reads the week's `data/daily/` files and `cases.json`, keeps each paper's highest upvote count, refreshes the top 15 from Hugging Face, ranks the week and saves Figure 1 of the top two papers from arXiv into `data/weekly/<week>/`.
2. **Write** (Groq): a plain headline and short copy per story, written from the abstract, then checked against the abstract by a second Groq call. Copy that fails twice falls back to the paper's own title and notes. Saved copy is never rewritten, so you can edit the week file by hand before the email goes out.
3. **Send**: renders the email from the week file and sends it through Buttondown after the site is published, so the hosted masthead (`src/site_assets/weekly-masthead.png`) and figures (copied to `site/weekly/<week>/`) are live.

Set the repository variable `WEEKLY_SEND=draft` to review it in Buttondown first, or `WEEKLY_EMAIL=off` to turn it off. Preview locally with `python src/weekly_edition.py --preview 2026-11-08`.

## Agents

Four parts of the project are LangGraph agents: graphs of small steps that share one state, with checks and retries between the LLM calls, so a bad answer gets caught instead of published. Every LLM step can fail without stopping the step around it.

### Daily pipeline

`src/pipeline_graph.py` runs the whole morning edition as a `StateGraph`. Each run can be traced step by step in LangSmith.

```mermaid
flowchart LR
    fetch --> classify --> choose_pool --> evidence --> shortlist --> judge --> pick --> notes --> save
    fetch -.->|"nothing fetched"| stop((stop))
    pick -.->|"nothing picked"| stop
```

The **evidence** step gathers novelty, the measured signals and the checked benchmark claims; every source is optional and a failure leaves its signals unknown. The **judge** (`src/judge.py`, LangChain on Groq) only runs when the leaders are within 3 points, and compares just those papers two at a time, with the sides shuffled. If more than a quarter of the comparisons fail, the best score is the pick.

### Curator

`src/curator.py` writes each pick's reading notes, and doesn't trust the first draft.

```mermaid
flowchart LR
    draft --> validate
    validate -->|"fields fail"| repair --> validate
    validate -->|"still failing"| next_model --> draft
    validate -->|"all good"| ground
    ground -->|"required fact unsupported"| repair
    ground --> finish
```

Every field is checked for word limits, required fields and numbers that aren't in the abstract. Only the failed fields go back for repair, up to two rounds. A second model then checks each fact against the abstract.

### Project Scout

`supabase/functions/_shared/scout_agent.ts` is a LangGraph.js graph inside a Supabase edge function.

```mermaid
flowchart LR
    plan_needs --> retrieve --> fuse --> rank
    rank -->|"a need has no strong paper (round 1)"| expand_search --> fuse
    rank --> respond
```

It splits a project into needs, searches each by meaning and keywords, fuses the lists and has the LLM score every candidate. If a need is left without a strong paper, it searches once more with the ranker's suggested phrases and scores only the new papers, and the page says "Searched again for: …". Needs the visitor edited skip `plan_needs`. The steps have no network calls, so they are tested with fakes, and the same steps run without LangGraph (`SCOUT_ENGINE=loop`) as a fallback. Loading LangGraph costs about 0.1 to 0.2 s of the edge function's 2 s CPU budget.

### Code review agent

Every Monday, `scripts/code_review_agent.py` reviews the week's changes and opens GitHub issues for likely bugs.

```mermaid
flowchart LR
    collect --> review --> verify --> dedupe --> file
    collect -.->|"nothing changed, checks pass"| stop((stop))
```

It runs pytest, the function tests and ruff (bug rules only), then has the LLM read each changed file's diff and name likely bugs, each with a line and the code on it. Findings whose code isn't really on that line are dropped, failing checks rank first, and anything filed before, open or closed, is skipped. It opens at most 3 issues labelled `agent-found` using the workflow's own `GITHUB_TOKEN`. Run the workflow by hand with **dry run** ticked to see what it would file.

### How they are measured

- **Picker backtest.** `python scripts/backtest_picker.py` replays every saved day and compares each pick with the papers' Hugging Face upvotes a few days later. Over the first 4 days with settled upvotes:

  | Picker | Pick in the day's top 10 | Share of the best paper's upvotes |
  | :-- | :-: | :-: |
  | Random | 9% | |
  | Old scorer | 4 of 4 | 0.88 |
  | New scorer | 4 of 4 | 0.85 |
  | Picking a day late | 3 of 3 | 0.94 |

  Both scorers already find a top-10 paper every day. The new one wins on evidence (no points for buzzwords or long author lists), and picking a day late, once upvotes have built up, is the clearest gain so far. With a week of data these numbers are noisy and are re-run as days are added.
- **Eval sets.** 26 Project Scout cases and 30 Ask this paper cases in `evals/`, run with `python scripts/run_evals.py` and logged as LangSmith experiments (see *Are Scout and Ask getting better?* above).

## Tech stack

| Layer | Built with |
| :-- | :-- |
| Pipeline | Python 3.11, [LangGraph](https://langchain-ai.github.io/langgraph/) (the daily run is a StateGraph), arXiv API, Hugging Face Daily Papers, Semantic Scholar, OpenAlex |
| Agents and tracing | LangGraph (daily pipeline, Curator, code review agent), LangGraph.js (Project Scout), LangChain (the pairwise judge, with model fallback), LangSmith tracing and experiments (optional) |
| Language model | [Groq](https://groq.com) running `gpt-oss-120b`, with `gpt-oss-20b` as fallback |
| Database and search | [Supabase](https://supabase.com) Postgres, pgvector, Edge Functions (Deno, TypeScript) |
| Website | Static HTML, CSS and vanilla JavaScript, hand-drawn SVG charts |
| Email | [Buttondown](https://buttondown.com) |
| Hosting and automation | GitHub Pages, GitHub Actions |

<details>
<summary><strong>Project structure</strong></summary>
<br>

```text
ai-paper-daily/
├── .github/workflows/
│   ├── daily-digest.yml        Daily edition: pick, sync, build, deploy, email
│   ├── supabase-functions.yml  Deploys the Edge Functions
│   ├── supabase-sync.yml       One-time full sync and history backfill
│   ├── scoreboard.yml          Weekly ranking scoreboard
│   └── tests.yml               Python and TypeScript tests on every push
├── src/
│   ├── main.py                 Pipeline entry point
│   ├── pipeline_graph.py       The daily run as a LangGraph graph
│   ├── judge.py                LLM tie-break between near-equal leaders
│   ├── signals.py              GitHub, Hugging Face, Hacker News and Semantic Scholar numbers per paper
│   ├── novelty.py              Distance from the last 90 days of papers (TF-IDF)
│   ├── claims.py               Benchmark claims, kept only if quoted word for word
│   ├── ranking_pages.py        "Why this ranked" and the Methodology page
│   ├── fetcher.py              arXiv and Hugging Face fetcher
│   ├── classifier.py           Research topic classifier
│   ├── scorer.py               Score out of 100: top pick and trending
│   ├── curator.py              Notes for each pick (LangGraph: draft, check, repair, ground)
│   ├── groq_summarizer.py      Groq client with model fallback
│   ├── paper_store.py          Daily JSON records in data/
│   ├── pick_pool.py            Which papers the picks come from (today or yesterday)
│   ├── paper_links.py          Code, models, citations and labs for paper pages
│   ├── labs.py                 Which lab or company wrote each paper
│   ├── lab_logos.py            Each lab's logo, saved in data/logos/
│   ├── supabase_sync.py        Upload, embed and export papers
│   ├── trends.py               Trend maths and SVG charts
│   ├── tech_trends.py          Technologies to watch
│   ├── technologies.py         Technology catalogue
│   ├── site_builder.py         Static site generator
│   ├── discovery.py            RSS feed, sitemap and share images
│   ├── send_newsletter.py      Daily email through Buttondown
│   ├── weekly_edition.py       The Weekly Express, the Sunday email
│   ├── share_fonts/            Fonts for the share images
│   └── site_assets/            CSS, JavaScript and fonts
├── supabase/
│   ├── schema.sql              Tables, vector search, rate limits
│   ├── functions/              search, recommend, scout (LangGraph.js agent), scout-spike, ask, breakdown, track, embed
│   └── tests/                  Edge Function tests
├── scripts/
│   ├── backtest_picker.py      Replays saved days to measure the picker
│   ├── scoreboard.py           Checks the ranking against citations and stars 30 days later
│   ├── run_evals.py            Scores Scout and Ask on the eval sets
│   └── code_review_agent.py    Weekly review that opens issues (LangGraph)
├── evals/                      Eval sets for Scout and Ask, and saved results
├── tests/                      Python tests
├── data/                       Daily editions, links and lab logos, updated by the workflow
└── docs/                       Logo and screenshots
```
</details>

### Building the site on your computer

```bash
python src/supabase_sync.py --export-only   # downloads the year of papers Trends needs (SUPABASE_URL and SUPABASE_SECRET_KEY in .env)
python src/site_builder.py                  # writes site/
```

Without the export, the site still builds, but Trends is hidden because the site's own papers cover only a few weeks.

## License

Released under the [MIT License](LICENSE).

<div align="center">
<br>
<sub>Data from <a href="https://arxiv.org">arXiv</a> and <a href="https://huggingface.co/papers">Hugging Face</a>. Thank you to arXiv for use of its open access interoperability.</sub>
</div>
