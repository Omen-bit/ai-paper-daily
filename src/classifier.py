"""
classifier.py
Multi-label keyword-based classifier for AI/ML research papers.
Assigns papers to one or more of 12 thematic categories plus a fallback "Other ML".

Design notes:
- Specific/rare keywords score 3 points in title, 1 point in abstract.
- Generic broad keywords score 1 point in title, 0 in abstract (weight 1/3 of specific ones).
- arXiv category bonus contributes at most 2 points (cannot alone cross the threshold).
- A category is assigned only if its score >= MIN_CATEGORY_SCORE.
- Up to 3 categories per paper; minimum 1 (fallback to "Other ML" if none pass).
"""

import re
from typing import Optional


# Minimum score a category must reach to be assigned to a paper.
MIN_CATEGORY_SCORE = 3

# Category definitions: (emoji, display_name, slug, specific_keywords, broad_keywords)
# specific_keywords score 3 (title) / 1 (abstract)
# broad_keywords score 1 (title) / 0 (abstract) -- used only as a weak tie-breaker
CATEGORIES = [
    (
        "🤖", "LLMs & Language Models", "llms",
        # specific
        [
            "large language model", "gpt", "transformer architecture", "bert",
            "tokenization", "tokenizer", "pre-training", "pretraining", "fine-tuning",
            "finetuning", "instruction tuning", "chatbot", "text generation",
            "autoregressive", "encoder-decoder", "t5", "llama", "palm",
            "gemini", "claude", "mistral", "falcon", "few-shot", "zero-shot",
            "in-context learning", "next token prediction", "causal lm",
            "masked language modeling", "finetuned language",
        ],
        # broad (weak signal)
        ["llm", "language model", "prompt"],
    ),
    (
        "🎨", "Generative AI & Diffusion", "generative-ai",
        [
            "diffusion model", "denoising diffusion", "ddpm", "ddim", "score matching",
            "flow matching", "generative adversarial", "variational autoencoder",
            "text-to-image", "stable diffusion", "dall-e", "dalle", "imagen",
            "latent diffusion", "image synthesis", "inpainting", "image editing",
            "video generation", "text-to-video", "consistency model", "rectified flow",
        ],
        ["generative model", "gan", "vae", "synthesis"],
    ),
    (
        "👁️", "Computer Vision", "computer-vision",
        [
            "object detection", "image classification", "semantic segmentation",
            "instance segmentation", "panoptic segmentation", "vision transformer",
            "convolutional neural network", "depth estimation", "3d reconstruction",
            "point cloud", "neural radiance field", "nerf", "pose estimation",
            "optical flow", "bounding box", "yolo", "scene understanding",
            "image recognition", "visual representation learning",
        ],
        ["computer vision", "visual", "vit", "cnn", "resnet"],
    ),
    (
        "🎵", "Audio, Speech & Music", "audio-speech",
        [
            "automatic speech recognition", "asr", "text-to-speech", "speech synthesis",
            "voice conversion", "wav2vec", "whisper model", "whisper", "music generation",
            "speech translation", "acoustic model", "phoneme", "prosody", "vocoder",
            "speech enhancement", "audio generation", "speaker recognition",
        ],
        ["speech", "audio", "voice", "sound"],
    ),
    (
        "🤝", "RLHF & Alignment", "alignment",
        [
            "reinforcement learning from human feedback", "rlhf", "reward modeling",
            "direct preference optimization", "dpo", "constitutional ai",
            "value alignment", "proximal policy optimization", "ppo",
            "red teaming", "jailbreak", "refusal training", "human preferences",
            "preference learning",
        ],
        ["alignment", "reward model", "feedback"],
    ),
    (
        "🧠", "Reasoning & Agents", "reasoning-agents",
        [
            "chain-of-thought", "chain of thought", "tree of thought",
            "multi-agent system", "autonomous agent", "tool use", "tool calling",
            "function calling", "retrieval augmented generation", "rag",
            "self-reflection", "self-refinement", "mathematical reasoning",
            "logical reasoning", "commonsense reasoning", "coding agent", "web agent",
            "decision making under uncertainty", "react prompting",
        ],
        ["reasoning", "agent", "agentic", "planning"],
    ),
    (
        "📊", "ML Theory & Optimization", "ml-theory",
        [
            "convergence analysis", "loss landscape", "gradient descent", "adam optimizer",
            "regularization theory", "generalization bound", "pac learning",
            "sample complexity", "neural tangent kernel", "ntk", "double descent",
            "grokking", "lottery ticket hypothesis", "scaling law", "emergent ability",
            "training dynamics", "bias-variance tradeoff",
        ],
        ["optimization", "learning theory", "overfitting"],
    ),
    (
        "🏥", "AI for Science & Healthcare", "ai-science",
        [
            "medical imaging", "clinical nlp", "drug discovery", "protein structure",
            "alphafold", "molecular generation", "genomics", "radiology ai",
            "pathology detection", "electronic health record", "ehr",
            "materials science", "climate modeling", "physics simulation",
            "scientific discovery", "bioinformatics", "dna", "rna sequencing",
        ],
        ["medical", "healthcare", "clinical", "biology", "chemistry"],
    ),
    (
        "💻", "Code & Software Engineering", "code-ai",
        [
            "code generation", "program synthesis", "automated debugging",
            "github copilot", "codex model", "code completion", "bug detection",
            "test generation", "static analysis", "decompiler", "code understanding",
            "automated program repair", "vulnerability detection", "code review automation",
        ],
        ["programming", "software engineering", "repository"],
    ),
    (
        "🔒", "AI Safety & Privacy", "safety-privacy",
        [
            "adversarial attack", "adversarial robustness", "differential privacy",
            "federated learning", "fairness in ml", "algorithmic bias",
            "toxicity detection", "hallucination reduction", "uncertainty quantification",
            "out-of-distribution detection", "anomaly detection", "interpretability",
            "explainability", "trustworthy ai", "watermarking", "deepfake detection",
        ],
        ["safety", "robustness", "privacy", "bias"],
    ),
    (
        "📱", "Efficient AI & Edge", "efficient-ai",
        [
            "quantization", "knowledge distillation", "model compression",
            "neural network pruning", "mobile inference", "edge computing",
            "inference optimization", "speculative decoding", "early exit network",
            "mixture of experts", "low-rank adaptation", "lora", "parameter efficient",
            "sparse attention", "parameter-efficient", "8-bit",
        ],
        ["efficient", "lightweight", "latency", "throughput"],
    ),
    (
        "🌐", "Multimodal AI", "multimodal",
        [
            "vision-language model", "vlm", "clip model", "image text alignment",
            "image-text alignment", "video-language model", "visual question answering",
            "vqa", "image captioning", "visual reasoning", "cross-modal retrieval",
            "audio-visual learning", "gpt-4v", "llava", "flamingo model",
            "visual instruction tuning",
        ],
        ["multimodal", "vision language"],
    ),
    (
        "🔖", "Other ML", "other-ml",
        # No keywords: this is the fallback only; it is never matched by keyword scoring
        [],
        [],
    ),
]


def _normalize(text: str) -> str:
    """Lowercase and remove special characters for matching."""
    return re.sub(r"[^a-z0-9 ]", " ", text.lower())


def classify_paper(paper: dict, top_n: int = 3) -> list[dict]:
    """
    Classify a paper into one or more categories based on keyword matching.
    Returns list of matched category dicts sorted by score, up to top_n.
    A category is only included if its score >= MIN_CATEGORY_SCORE.
    Falls back to "Other ML" if nothing passes the threshold.
    """
    title_norm = _normalize(paper.get("title", ""))
    abstract_norm = _normalize(paper.get("abstract", ""))
    full_text = f"{title_norm} {abstract_norm}"
    arxiv_cats = " ".join(paper.get("arxiv_categories", [])).lower()

    matched = []
    for emoji, name, slug, specific_kws, broad_kws in CATEGORIES:
        if slug == "other-ml":
            continue  # never matched directly

        score = 0

        # Specific keywords: 3 pts in title, 1 pt in abstract
        for kw in specific_kws:
            if kw in title_norm:
                score += 3
            elif kw in abstract_norm:
                score += 1

        # Broad/generic keywords: 1 pt in title only (0 in abstract)
        for kw in broad_kws:
            if kw in title_norm:
                score += 1

        # arXiv category bonus: at most 2 pts total, and capped so it cannot
        # alone push a category over MIN_CATEGORY_SCORE.
        arxiv_bonus_map = {
            "llms": ["cs.cl", "cs.lg"],
            "generative-ai": ["cs.cv", "cs.lg"],
            "computer-vision": ["cs.cv"],
            "audio-speech": ["cs.sd", "eess.as"],
            "alignment": ["cs.ai", "cs.lg"],
            "reasoning-agents": ["cs.ai", "cs.lg", "cs.cl"],
            "ml-theory": ["stat.ml", "cs.lg"],
            "ai-science": ["q-bio", "cs.ce"],
            "code-ai": ["cs.se", "cs.pl"],
            "safety-privacy": ["cs.cr", "cs.ai"],
            "efficient-ai": ["cs.lg", "cs.ar"],
            "multimodal": ["cs.cv", "cs.cl"],
        }
        bonus = 0
        for code in arxiv_bonus_map.get(slug, []):
            if code in arxiv_cats:
                bonus += 1
        # Cap: bonus can be at most 2 and cannot alone reach the threshold
        bonus = min(bonus, 2)
        score += bonus

        if score >= MIN_CATEGORY_SCORE:
            matched.append({
                "emoji": emoji,
                "name": name,
                "slug": slug,
                "score": score,
            })

    # Sort by score descending, keep top_n
    matched.sort(key=lambda x: x["score"], reverse=True)
    result = matched[:top_n]

    # Fallback: if nothing passed the threshold, assign "Other ML"
    if not result:
        result = [{"emoji": "🔖", "name": "Other ML", "slug": "other-ml", "score": 0}]

    return result


def classify_papers(papers: list[dict]) -> list[dict]:
    """Classify all papers and attach 'categories' field to each."""
    for paper in papers:
        paper["categories"] = classify_paper(paper)
    return papers


def get_all_category_slugs() -> list[str]:
    """Return list of all category slugs."""
    return [slug for _, _, slug, _, _ in CATEGORIES]


def get_category_display(slug: str) -> Optional[tuple]:
    """Get emoji and display name for a category slug."""
    for emoji, name, s, _, _ in CATEGORIES:
        if s == slug:
            return emoji, name
    return None
