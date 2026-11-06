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

AI Papers Daily reads all of them every morning and publishes a small edition: **one top pick** chosen by a scoring model, and **one trending paper** the community is upvoting on Hugging Face. Each one is explained in plain words, from a ten-second summary to what you would need to build with it.

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

Describe what you want to build in plain words. Scout splits it into the parts it needs (you can edit them), searches each one by meaning and by keywords, and returns the papers to build on, best first, with one line on why each fits. If part of your project has no good paper, it says so. Press **Watch this project** to see new papers that match it later.

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
    C --> D["Score<br/>top pick + trending"]
    D --> E["Write notes<br/>Groq"]
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
| `scout` | Project Scout | Splits the project into needs with an LLM, runs a hybrid search for each, then scores every match and says why it fits |
| `ask` | Ask this paper | Reads the full paper from arXiv once, stores it in sections, then answers from the best-matching sections and quotes its source |
| `breakdown` | Paper pages | Copies the contributions, results, limitations and conclusion from the paper once (no LLM), plus a short AI summary for papers without notes |
| `track` | Most read, site numbers | Counts anonymous views, "worth it" votes, clicks on each pick, "seen it before?" answers and returning visitors |
| `embed` | Daily sync | Turns each paper into a `gte-small` vector (pipeline only) |

<details>
<summary><strong>How papers are picked</strong></summary>
<br>

- **Community momentum.** Hugging Face upvotes. The most upvoted paper of the day becomes Trending.
- **Novelty.** Signals in the title and abstract that the paper introduces something new.
- **Cross-over.** Papers that span several research topics.
- **Builder value.** Released code, benchmarks, surveys and position papers.
- **Readers.** Once the site has enough views, the week's most read paper takes the second slot.

Papers featured in the last seven editions are not picked again. The pipeline reads every new paper in the tracked arXiv categories each day (often over 1,000) and keeps the best 200 in `data/`.

Each morning `paper_links.py` also gathers citations, code, models and labs into `data/links.json`, and lab logos into `data/logos/`, with no AI. A lab comes from evidence that names it directly: the organization that claimed the paper on Hugging Face, the owner of its GitHub code, the arXiv comment field, or the authors' institutions on OpenAlex. Logos come from Hugging Face, Wikidata, GitHub or the lab's own website.
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
<summary><strong>Limits and safety</strong></summary>
<br>

- Every public function has a per-visitor hourly limit.
- `embed` only accepts calls carrying the pipeline's `SYNC_SECRET`.
- If the LLM is unavailable, Scout still returns its search results, marked as not checked.
- AI summaries in `breakdown` are capped per day; past the cap the page shows the breakdown without one.
- Stored full texts that nobody has asked about for 30 days are removed by the daily run.
</details>

## Tech stack

| Layer | Built with |
| :-- | :-- |
| Pipeline | Python 3.11, arXiv API, Hugging Face Daily Papers, Semantic Scholar, OpenAlex |
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
│   └── tests.yml               Python and TypeScript tests on every push
├── src/
│   ├── main.py                 Pipeline entry point
│   ├── fetcher.py              arXiv and Hugging Face fetcher
│   ├── classifier.py           Research topic classifier
│   ├── scorer.py               Scoring: top pick and trending
│   ├── curator.py              Notes for each pick
│   ├── groq_summarizer.py      Groq client with model fallback
│   ├── paper_store.py          Daily JSON records in data/
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
│   ├── share_fonts/            Fonts for the share images
│   └── site_assets/            CSS, JavaScript and fonts
├── supabase/
│   ├── schema.sql              Tables, vector search, rate limits
│   ├── functions/              search, recommend, scout, ask, breakdown, track, embed
│   └── tests/                  Edge Function tests
├── tests/                      Python tests
├── data/                       Daily editions, links and lab logos, updated by the workflow
└── docs/                       Logo and screenshots
```
</details>

## License

Released under the [MIT License](LICENSE).

<div align="center">
<br>
<sub>Data from <a href="https://arxiv.org">arXiv</a> and <a href="https://huggingface.co/papers">Hugging Face</a>. Thank you to arXiv for use of its open access interoperability.</sub>
</div>
