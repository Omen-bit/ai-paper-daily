# 🧠 AI Paper Daily

> **Automatically curated AI & ML research — 2 top papers every day, zero effort.**  
> Powered by arXiv · HuggingFace Papers · Groq AI · GitHub Actions

[![Daily Digest](https://github.com/YOUR_USERNAME/ai-paper-daily/actions/workflows/daily-digest.yml/badge.svg)](https://github.com/YOUR_USERNAME/ai-paper-daily/actions/workflows/daily-digest.yml)
![Papers Tracked](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/YOUR_USERNAME/ai-paper-daily/main/stats/stats.json&query=$.total_papers&label=Papers%20Tracked&color=blueviolet)
![Digests](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/YOUR_USERNAME/ai-paper-daily/main/stats/stats.json&query=$.total_digests&label=Daily%20Digests&color=green)

---

## 🔥 Today's Top Picks

<!-- TODAY_START -->
### 📅 Latest Digest — [Tuesday, October 20 2026](digests/2026-10-20.md)

**1. ⭐ 🔥 🔀 📖 [Evidence-First Agentic Verification](https://arxiv.org/abs/2610.17724)**  
*🧠 Reasoning & Agents · 🤖 LLMs & Language Models*  
💡 _We introduce Sauron, an evidence-first agentic verifier that investigates both state and trace and relies on a claim only after independently validating it against its source._  

**2. 🔥 🔀 📖 [Where is Physical RSI capability from? An Observational Scaling Law of LLM-as-policy](https://arxiv.org/abs/2610.26848)**  
*📊 ML Theory & Optimization · 🤖 LLMs & Language Models*  
💡 _We introduce PhysRSI-eval to quantify physical RSI through a five-axis metric: First-Attempt Performance, Efficiency, Success, Budget and Improvement from failure._  

[📖 Read full digest →](digests/2026-10-20.md)
<!-- TODAY_END -->

---

## 🏷️ Browse by Category

| Category | Description |
|----------|-------------|
| [🤖 LLMs & Language Models](categories/llms.md) | GPT, BERT, transformers, instruction tuning |
| [🎨 Generative AI & Diffusion](categories/generative-ai.md) | Diffusion models, GANs, image/video generation |
| [👁️ Computer Vision](categories/computer-vision.md) | Object detection, segmentation, ViT |
| [🎵 Audio, Speech & Music](categories/audio-speech.md) | ASR, TTS, speech synthesis |
| [🤝 RLHF & Alignment](categories/alignment.md) | Reward modeling, preference learning, safety |
| [🧠 Reasoning & Agents](categories/reasoning-agents.md) | Chain-of-thought, tool use, planning |
| [📊 ML Theory & Optimization](categories/ml-theory.md) | Convergence, scaling laws, training dynamics |
| [🏥 AI for Science & Healthcare](categories/ai-science.md) | Drug discovery, protein folding, climate AI |
| [💻 Code & Software Engineering](categories/code-ai.md) | Code generation, debugging, software agents |
| [🔒 AI Safety & Privacy](categories/safety-privacy.md) | Robustness, fairness, adversarial attacks |
| [📱 Efficient AI & Edge](categories/efficient-ai.md) | Quantization, pruning, LoRA, MoE |
| [🌐 Multimodal AI](categories/multimodal.md) | Vision-language, VQA, CLIP, image-text |

---

<!-- ARCHIVE_START -->
### 📁 Digest Archive

| Date | Papers | Top Category | Link |
|------|--------|--------------|------|
| 2026-10-20 | 2 | Reasoning & Agents | [📄 Read](digests/2026-10-20.md) |
<!-- ARCHIVE_END -->

---

<!-- STATS_START -->
### 📊 Project Stats

| Metric | Value |
|--------|-------|
| 📄 Total papers tracked | **4** |
| 📅 Total daily digests | **2** |
| 🗓️ Tracking since | **2026-10-20** |
| 🔄 Last updated | **2026-10-20** |

**🏆 Top Categories (all time):**

- 🧠 **Reasoning & Agents**: 4 papers
- 🤖 **LLMs & Language Models**: 4 papers
- 🎨 **Generative AI & Diffusion**: 2 papers
- 📊 **ML Theory & Optimization**: 2 papers
<!-- STATS_END -->

---

## 🛠️ How It Works

```
Every day at 06:30 UTC (noon IST):

  arXiv API ──┐
              ├──► Fetch ~150 papers
  HF Papers ──┘
                    │
                    ▼
             🏷️ Classify into 12 categories
                    │
                    ▼
             ⚡ Score & rank all papers
                    │
                    ▼
             🤖 Groq AI generates "Why it matters"
                    │
                    ▼
             📝 Render beautiful markdown digest
                    │
                    ▼
             📤 Auto-commit & push to GitHub ✅
```

**Sources:**
- 📡 **[arXiv](https://arxiv.org)** — 7 AI/ML categories (cs.AI, cs.LG, cs.CL, cs.CV, cs.NE, cs.RO, stat.ML)
- 🤗 **[HuggingFace Papers](https://huggingface.co/papers)** — Community-curated trending papers

**Scoring signals used to pick the top 2:**
- 🔥 HuggingFace upvotes (community validation)
- 💡 Novel method keywords in title/abstract
- 🔀 Interdisciplinary cross-category papers
- 📖 Survey/review identification
- 👥 Author collaboration size

---

## ⚙️ Setup (Fork & Run Yours)

1. **Fork this repo**
2. Get a free **[Groq API key](https://console.groq.com)** (takes 30 seconds)
3. Add it as a GitHub Secret:  
   `Settings → Secrets → Actions → New secret → GROQ_API_KEY`
4. Go to **Actions → Daily AI Paper Digest → Run workflow** to test it immediately
5. Done! It will auto-run every day at 06:30 UTC 🎉

---

## 📂 Repository Structure

```
ai-paper-daily/
├── 📄 README.md              ← You are here (auto-updated daily)
├── 📁 digests/               ← Daily digest files (YYYY-MM-DD.md)
├── 📁 categories/            ← Per-category landing pages
├── 📁 stats/
│   └── stats.json            ← Cumulative tracking data
├── 🐍 main.py                ← Pipeline orchestrator
├── 🐍 fetcher.py             ← arXiv + HuggingFace fetcher
├── 🐍 classifier.py          ← 12-category keyword classifier
├── 🐍 scorer.py              ← Heuristic paper scorer
├── 🐍 groq_summarizer.py     ← Groq AI summarizer (with fallbacks)
├── 🐍 renderer.py            ← Markdown renderer
├── 🐍 readme_updater.py      ← README dashboard updater
├── 🐍 stats_tracker.py       ← stats.json manager
└── 📁 .github/workflows/
    └── daily-digest.yml      ← GitHub Actions (runs daily at 06:30 UTC)
```

---

*Built with ❤️ using Python · [arXiv API](https://arxiv.org/help/api) · [HuggingFace Papers](https://huggingface.co/papers) · [Groq](https://groq.com) · [GitHub Actions](https://github.com/features/actions)*
