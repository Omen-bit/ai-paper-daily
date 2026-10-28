# 🧠 AI Paper Daily

<div align="center">

> **Autonomous AI & Machine Learning Research Intelligence.**
> Curating the top 2 breakthrough papers daily at 07:00 AM IST, with "Why It Matters" summaries, heuristic scoring, and automatic GitHub publishing.

[![Daily Digest](https://github.com/Omen-bit/ai-paper-daily/actions/workflows/daily-digest.yml/badge.svg)](https://github.com/Omen-bit/ai-paper-daily/actions/workflows/daily-digest.yml)
![Papers Tracked](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/Omen-bit/ai-paper-daily/main/stats/stats.json&query=$.total_papers&label=Papers%20Curated&color=7c3aed)
![Digests](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/Omen-bit/ai-paper-daily/main/stats/stats.json&query=$.total_digests&label=Daily%20Editions&color=10b981)
![Schedule](https://img.shields.io/badge/schedule-daily%2007%3A00%20IST%20%2F%2001%3A30%20UTC-orange)
![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)
![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)

[**Today's Picks**](#-todays-featured-papers) &nbsp;•&nbsp;
[**Categories**](#-browse-by-category) &nbsp;•&nbsp;
[**Archive**](#-digest-archive) &nbsp;•&nbsp;
[**Analytics**](#-analytics--coverage) &nbsp;•&nbsp;
[**Architecture**](#-system-architecture) &nbsp;•&nbsp;
[**Repository Layout**](#-repository-layout)

---

</div>

## 🔥 Today's Featured Papers

<!-- TODAY_START -->
### Wednesday, October 28, 2026 · [2026-10-28](digests/2026-10-28.md)

#### 1. [PDRVLA: A Vision-Language-Action Model with Physical Dynamics Representations](https://arxiv.org/abs/2610.37381)
`⭐ Top Pick` `🔥 Trending on HF` `🎨 Generative AI & Diffusion` `👁️ Computer Vision` `61 HF upvotes`

> 💡 **Abstract highlight:**  
> Video world models can capture scene dynamics, yet generating future videos introduces high latency into the control loop.

**Authors:** Hanqing Wang, Zhaotian Cai, Ruichuan An et al.  
**Links:** [arXiv Paper](https://arxiv.org/abs/2610.37381) &nbsp;|&nbsp; [Direct PDF](https://arxiv.org/pdf/2610.37381) &nbsp;|&nbsp; [HF Community](https://huggingface.co/papers/2610.37381)  

#### 2. [Hy-Nomas: Towards Free-form Interactive World Generation](https://arxiv.org/abs/2610.36729)
`🔥 Trending on HF` `🔖 Other ML` `79 HF upvotes`

> 💡 **Abstract highlight:**  
> We present Hy-Nomas, a video world model with an 8B diffusion backbone that supports free-form text instructions and continuous camera control across multiple interaction turns.

**Authors:** Qiaoling Chen, Jiaxiang Cheng, Xueqing Deng et al.  
**Links:** [arXiv Paper](https://arxiv.org/abs/2610.36729) &nbsp;|&nbsp; [Direct PDF](https://arxiv.org/pdf/2610.36729) &nbsp;|&nbsp; [HF Community](https://huggingface.co/papers/2610.36729)  

**[Read the full digest with abstracts](digests/2026-10-28.md)**
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
| **2026-10-28** | `2` | Generative AI & Diffusion | [Read digest](digests/2026-10-28.md) |
| **2026-10-27** | `2` | Other ML | [Read digest](digests/2026-10-27.md) |
| **2026-10-26** | `2` | Other ML | [Read digest](digests/2026-10-26.md) |
| **2026-10-25** | `2` | Other ML | [Read digest](digests/2026-10-25.md) |
| **2026-10-24** | `2` | Other ML | [Read digest](digests/2026-10-24.md) |
| **2026-10-23** | `2` | Other ML | [Read digest](digests/2026-10-23.md) |
| **2026-10-22** | `2` | Other ML | [Read digest](digests/2026-10-22.md) |
| **2026-10-21** | `2` | Other ML | [Read digest](digests/2026-10-21.md) |
| **2026-10-20** | `2` | Reasoning & Agents | [Read digest](digests/2026-10-20.md) |
<!-- ARCHIVE_END -->

---

## 📊 Analytics & Coverage

<!-- STATS_START -->
| Metric | Value |
| :--- | :--- |
| Papers curated | **18** |
| Daily editions | **9** |
| Tracking since | `2026-10-20` |
| Last run | `2026-10-28` |

**Most active categories:**

- 🔖 **Other ML**: `14` papers
- 🎨 **Generative AI & Diffusion**: `2` papers
- 🧠 **Reasoning & Agents**: `2` papers
- 👁️ **Computer Vision**: `1` paper
- 📊 **ML Theory & Optimization**: `1` paper
<!-- STATS_END -->

---

## 🛠️ System Architecture

Every morning at **01:30 UTC (07:00 AM IST)**, GitHub Actions runs the pipeline:

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

## 📂 Repository Layout

```text
ai-paper-daily/
├── .github/workflows/
│   └── daily-digest.yml      # Automated 01:30 UTC (07:00 AM IST) daily runner
├── src/                      # All pipeline code
│   ├── main.py               # Pipeline orchestrator and entrypoint
│   ├── classifier.py         # 12-category research classifier
│   ├── fetcher.py            # arXiv and HuggingFace API fetcher
│   ├── groq_summarizer.py    # LLM summarizer with fallback chain
│   ├── readme_updater.py     # Live README section manager
│   ├── renderer.py           # Markdown digest and category builder
│   ├── scorer.py             # Heuristic scoring and status badges
│   └── stats_tracker.py      # Cumulative JSON analytics manager
├── digests/                  # Published daily edition markdown files
├── categories/               # Dedicated archive per research field
├── stats/                    # stats.json + last_run.txt
├── requirements.txt          # Runtime dependencies (pinned)
├── LICENSE                   # MIT License
└── README.md                 # Public project dashboard
```

---

<div align="center">

*Engineered with Python · Powered by [arXiv](https://arxiv.org) · [Hugging Face](https://huggingface.co) · [Groq](https://groq.com) · [GitHub Actions](https://github.com/features/actions)*

</div>
