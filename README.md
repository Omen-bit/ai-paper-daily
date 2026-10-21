# 🧠 AI Paper Daily

<div align="center">

> **Autonomous AI & Machine Learning Research Intelligence.**
> Curating the top 2 breakthrough papers every morning, with "Why It Matters" summaries, heuristic scoring, and automatic GitHub publishing.

[![Daily Digest](https://github.com/Omen-bit/ai-paper-daily/actions/workflows/daily-digest.yml/badge.svg)](https://github.com/Omen-bit/ai-paper-daily/actions/workflows/daily-digest.yml)
[![Tests](https://github.com/Omen-bit/ai-paper-daily/actions/workflows/tests.yml/badge.svg)](https://github.com/Omen-bit/ai-paper-daily/actions/workflows/tests.yml)
![Papers Tracked](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/Omen-bit/ai-paper-daily/main/stats/stats.json&query=$.total_papers&label=Papers%20Curated&color=7c3aed)
![Digests](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/Omen-bit/ai-paper-daily/main/stats/stats.json&query=$.total_digests&label=Daily%20Editions&color=10b981)
![Schedule](https://img.shields.io/badge/schedule-daily%2006%3A30%20UTC-orange)
![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)
![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)

[**Today's Picks**](#-todays-featured-papers) &nbsp;•&nbsp;
[**Categories**](#-browse-by-category) &nbsp;•&nbsp;
[**Archive**](#-digest-archive) &nbsp;•&nbsp;
[**Analytics**](#-analytics--coverage) &nbsp;•&nbsp;
[**Architecture**](#-system-architecture) &nbsp;•&nbsp;
[**Setup**](#-quick-start-fork--run)

---

</div>

## 🔥 Today's Featured Papers

<!-- TODAY_START -->
### Wednesday, October 21, 2026 -- [2026-10-21](digests/2026-10-21.md)

#### 1. [Ropedia W0: Scaling Loco-Manipulation World Models across Embodiments with Human Experience](https://arxiv.org/abs/2610.26855)
`⭐ Top Pick` `🔥 Trending on HF` `🔖 Other ML`

> 💡 **Abstract highlight:**  
> We present Ropedia W0, the first egocentric loco-manipulation world foundation model spanning humans and robots with diverse embodiments.

**Authors:** Tianqi Liu, Hanfei Zhao, Qifeng Liang et al.  
**Links:** [arXiv Paper](https://arxiv.org/abs/2610.26855) &nbsp;|&nbsp; [Direct PDF](https://arxiv.org/pdf/2610.26855) &nbsp;|&nbsp; [HF Community](https://huggingface.co/papers/2610.26855)  

#### 2. [VLA-Rolling: Fewer Denoising Steps, Better Control via Adaptive Action Reuse](https://arxiv.org/abs/2610.25043)
`🔥 Trending on HF` `📖 Survey / Review` `🔖 Other ML`

> 💡 **Abstract highlight:**  
> We show that this discarded tail retains transferable denoising progress: action-tail initialization can match or outperform a native 10-step Gaussian baseline using fewer denoising steps.

**Authors:** Sicheng He, Yi Pan, Qiuting Yu et al.  
**Links:** [arXiv Paper](https://arxiv.org/abs/2610.25043) &nbsp;|&nbsp; [Direct PDF](https://arxiv.org/pdf/2610.25043) &nbsp;|&nbsp; [HF Community](https://huggingface.co/papers/2610.25043)  

**[Read the full digest with abstracts](digests/2026-10-21.md)**
<!-- TODAY_END -->

---

## 🏷️ Browse by Category

Explore past curated papers categorized by research subfield:

| Models & Architecture | Applied Intelligence | Theory & Systems |
| :--- | :--- | :--- |
| [🤖 **LLMs & Language Models**](categories/llms.md) | [🧠 **Reasoning & Agents**](categories/reasoning-agents.md) | [📊 **ML Theory & Scaling**](categories/ml-theory.md) |
| [🎨 **Generative AI & Diffusion**](categories/generative-ai.md) | [🤝 **RLHF & Alignment**](categories/alignment.md) | [📱 **Efficient AI & Quantization**](categories/efficient-ai.md) |
| [👁️ **Computer Vision**](categories/computer-vision.md) | [💻 **Code & Software AI**](categories/code-ai.md) | [🔒 **AI Safety & Privacy**](categories/safety-privacy.md) |
| [🌐 **Multimodal AI**](categories/multimodal.md) | [🏥 **AI for Science & Health**](categories/ai-science.md) | [🎵 **Audio & Speech**](categories/audio-speech.md) |
| [🔖 **Other ML**](categories/other-ml.md) | | |

---

## 📁 Digest Archive

<!-- ARCHIVE_START -->
| Date | Papers | Top Category | Digest |
| :--- | :---: | :--- | :--- |
| **2026-10-21** | `2` | Other ML | [Read digest](digests/2026-10-21.md) |
| **2026-10-20** | `2` | Reasoning & Agents | [Read digest](digests/2026-10-20.md) |
<!-- ARCHIVE_END -->

---

## 📊 Analytics & Coverage

<!-- STATS_START -->
| Metric | Value |
| :--- | :--- |
| Papers curated | **4** |
| Daily editions | **2** |
| Tracking since | `2026-10-20` |
| Last run | `2026-10-21` |

**Most active categories:**

- 🔖 **Other ML**: `2` papers
- 🧠 **Reasoning & Agents**: `1` papers
- 📊 **ML Theory & Optimization**: `1` papers
<!-- STATS_END -->

---

## 🛠️ System Architecture

Every morning at **06:30 UTC (12:00 IST)**, GitHub Actions runs the pipeline:

```mermaid
flowchart LR
    A["arXiv API<br/>7 ML Categories"] --> C["Keyword<br/>Classifier"]
    B["HuggingFace<br/>Trending Feed"] --> C
    C --> D["Heuristic<br/>Scorer"]
    D --> E["Top 2<br/>Selection"]
    E --> F["Groq LLM<br/>Summary Chain"]
    F --> G["Render<br/>Markdown"]
    G --> H["Git Commit<br/>and Push"]
```

### Ranking Signals
- **Community Momentum:** HuggingFace upvotes and community bookmark velocity.
- **Novelty Detection:** Title/Abstract keyword markers (*breakthrough, SOTA, novel, introduce*).
- **Interdisciplinary Cross-over:** Multi-category convergence (e.g. LLMs + Robotics).
- **Synthesis Impact:** Comprehensive surveys, position papers, and landmark benchmarks.

---

## ⚙️ Quick Start (Fork & Run)

Want to run this automated digest for your own profile?

1. **Fork this repository** to your GitHub account.
2. **Obtain a free Groq API key** from [console.groq.com](https://console.groq.com) (free tier includes 30 RPM).
3. **Save your secret**:
   - Go to your repo: `Settings > Secrets and variables > Actions`
   - Add a new secret named `GROQ_API_KEY`
4. **Trigger workflow manually**:
   - Navigate to `Actions > Daily AI Paper Digest > Run workflow`
5. That's it! GitHub Actions will run every morning automatically.

### Local Development & Execution

To test or run the pipeline on your machine:

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Omen-bit/ai-paper-daily.git
   cd ai-paper-daily
   ```
2. **Install runtime dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure local environment (optional)**:
   ```bash
   cp .env.example .env
   ```
   Add your `GROQ_API_KEY` inside `.env`. If not set, the pipeline automatically falls back to abstract heuristics.
4. **Run the pipeline**:
   ```bash
   python src/main.py
   ```

### Running Tests & Contributing

Before opening a pull request, verify that all unit tests pass:

1. **Install development and testing dependencies**:
   ```bash
   pip install -r requirements-dev.txt
   ```
2. **Execute test suite**:
   ```bash
   pytest tests/ -v
   ```

---

## 📂 Repository Layout

```text
ai-paper-daily/
├── .github/workflows/
│   ├── daily-digest.yml      # Automated 06:30 UTC daily runner with race-condition prevention
│   └── tests.yml             # Runs pytest on push and pull request
├── src/                      # All pipeline code
│   ├── main.py               # Pipeline orchestrator and entrypoint
│   ├── classifier.py         # 12-category research classifier
│   ├── fetcher.py            # arXiv and HuggingFace API fetcher
│   ├── groq_summarizer.py    # LLM summarizer with fallback chain
│   ├── readme_updater.py     # Live README section manager
│   ├── renderer.py           # Markdown digest and category builder
│   ├── scorer.py             # Heuristic scoring and status badges
│   └── stats_tracker.py      # Cumulative JSON analytics manager with auto-reconciliation
├── tests/                    # Pytest test suite
├── digests/                  # Published daily edition markdown files
├── categories/               # Dedicated archive per research field
├── stats/                    # stats.json persistent dataset
├── requirements.txt          # Runtime dependencies (pinned)
├── requirements-dev.txt      # Dev/test dependencies
├── .env.example              # Template for local environment variables
├── LICENSE                   # MIT License
└── README.md                 # Public project dashboard
```

---

<div align="center">

*Engineered with Python · Powered by [arXiv](https://arxiv.org) · [Hugging Face](https://huggingface.co) · [Groq](https://groq.com) · [GitHub Actions](https://github.com/features/actions)*

</div>
