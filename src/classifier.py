"""
classifier.py
Multi-label keyword-based classifier for AI/ML research papers.
Assigns papers to one or more of 12 thematic categories.
"""

import re
from typing import Optional


# Category definitions: (emoji, display_name, slug, keywords)
CATEGORIES = [
    (
        "🤖", "LLMs & Language Models", "llms",
        [
            "large language model", "llm", "gpt", "transformer", "bert", "language model",
            "tokenization", "tokenizer", "pre-training", "pretraining", "fine-tuning",
            "finetuning", "instruction tuning", "chat", "chatbot", "text generation",
            "autoregressive", "decoder", "encoder-decoder", "t5", "llama", "palm",
            "gemini", "claude", "mistral", "falcon", "prompt", "few-shot", "zero-shot",
            "in-context learning", "next token", "causal lm", "masked language"
        ]
    ),
    (
        "🎨", "Generative AI & Diffusion", "generative-ai",
        [
            "diffusion", "denoising", "ddpm", "ddim", "score matching", "flow matching",
            "gan", "generative adversarial", "vae", "variational autoencoder",
            "image generation", "text-to-image", "text to image", "stable diffusion",
            "dall-e", "dalle", "imagen", "midjourney", "latent diffusion",
            "generative model", "synthesis", "inpainting", "image editing",
            "video generation", "text-to-video", "consistency model", "rectified flow"
        ]
    ),
    (
        "👁️", "Computer Vision", "computer-vision",
        [
            "computer vision", "object detection", "image classification", "segmentation",
            "vit", "vision transformer", "convolutional", "cnn", "resnet", "feature extraction",
            "visual representation", "depth estimation", "3d reconstruction", "point cloud",
            "nerf", "neural radiance", "pose estimation", "tracking", "optical flow",
            "image recognition", "visual", "bounding box", "yolo", "semantic segmentation",
            "instance segmentation", "panoptic", "scene understanding"
        ]
    ),
    (
        "🎵", "Audio, Speech & Music", "audio-speech",
        [
            "speech recognition", "asr", "automatic speech", "text-to-speech", "tts",
            "speech synthesis", "voice", "audio", "speaker", "whisper", "wav2vec",
            "sound", "music generation", "speech translation", "spoken language",
            "acoustic", "phoneme", "prosody", "vocoder", "speech enhancement",
            "noise reduction", "audio generation", "music", "singing"
        ]
    ),
    (
        "🤝", "RLHF & Alignment", "alignment",
        [
            "rlhf", "reinforcement learning from human feedback", "alignment", "reward model",
            "reward modeling", "preference", "constitutional ai", "harmless", "helpful",
            "honest", "safety alignment", "value alignment", "dpo", "direct preference",
            "ppo", "proximal policy", "red teaming", "jailbreak", "refusal",
            "human preferences", "feedback", "rating"
        ]
    ),
    (
        "🧠", "Reasoning & Agents", "reasoning-agents",
        [
            "reasoning", "chain-of-thought", "chain of thought", "cot", "tree of thought",
            "agent", "agentic", "planning", "tool use", "tool calling", "function calling",
            "react", "retrieval augmented", "rag", "self-reflection", "self-refinement",
            "multi-agent", "autonomous", "decision making", "problem solving",
            "mathematical reasoning", "logical reasoning", "commonsense", "benchmark",
            "gsm8k", "math", "coding agent", "web agent"
        ]
    ),
    (
        "📊", "ML Theory & Optimization", "ml-theory",
        [
            "optimization", "convergence", "loss landscape", "gradient descent", "adam",
            "regularization", "generalization", "overfitting", "bias-variance",
            "learning theory", "pac learning", "sample complexity", "neural tangent kernel",
            "ntk", "double descent", "grokking", "lottery ticket", "pruning theory",
            "loss function", "training dynamics", "scaling law", "emergent", "data efficiency"
        ]
    ),
    (
        "🏥", "AI for Science & Healthcare", "ai-science",
        [
            "medical", "healthcare", "clinical", "drug discovery", "protein",
            "alphafold", "molecular", "biology", "genomics", "radiology", "pathology",
            "disease", "diagnosis", "patient", "electronic health record", "ehr",
            "chemistry", "materials science", "climate", "physics simulation",
            "scientific discovery", "biomedical", "bioinformatics", "dna", "rna"
        ]
    ),
    (
        "💻", "Code & Software Engineering", "code-ai",
        [
            "code generation", "code synthesis", "program synthesis", "programming",
            "debugging", "software engineering", "github copilot", "codex", "code llm",
            "code completion", "bug detection", "test generation", "static analysis",
            "compiler", "decompiler", "code understanding", "repository", "pull request",
            "automated repair", "vulnerability detection", "code review"
        ]
    ),
    (
        "🔒", "AI Safety & Privacy", "safety-privacy",
        [
            "safety", "robustness", "adversarial", "adversarial attack", "defense",
            "privacy", "differential privacy", "federated learning", "fairness",
            "bias", "toxicity", "hallucination", "uncertainty", "calibration",
            "out-of-distribution", "ood", "anomaly detection", "interpretability",
            "explainability", "xai", "trustworthy", "responsible ai", "watermarking",
            "deepfake detection"
        ]
    ),
    (
        "📱", "Efficient AI & Edge", "efficient-ai",
        [
            "quantization", "pruning", "knowledge distillation", "distillation",
            "model compression", "efficient", "lightweight", "mobile", "edge computing",
            "inference optimization", "latency", "throughput", "hardware", "accelerator",
            "gpu", "tpu", "speculative decoding", "early exit", "mixture of experts",
            "moe", "sparse", "low-rank", "lora", "adapter", "parameter efficient"
        ]
    ),
    (
        "🌐", "Multimodal AI", "multimodal",
        [
            "multimodal", "vision-language", "vision language", "vlm", "clip",
            "image-text", "image text", "video-language", "video understanding",
            "visual question answering", "vqa", "image captioning", "visual reasoning",
            "cross-modal", "audio-visual", "video-text", "gpt-4v", "llava",
            "flamingo", "blip", "visual instruction", "visual chat"
        ]
    ),
]


def _normalize(text: str) -> str:
    """Lowercase and remove special characters for matching."""
    return re.sub(r"[^a-z0-9 ]", " ", text.lower())


def classify_paper(paper: dict, top_n: int = 3) -> list[dict]:
    """
    Classify a paper into one or more categories based on keyword matching.
    Returns list of matched category dicts sorted by match score, up to top_n.
    """
    text = _normalize(f"{paper.get('title', '')} {paper.get('abstract', '')}")

    # Also use arXiv category codes as signal
    arxiv_cats = " ".join(paper.get("arxiv_categories", [])).lower()

    matched = []
    for emoji, name, slug, keywords in CATEGORIES:
        score = 0
        for kw in keywords:
            if kw in text:
                # Title matches count more than abstract matches
                if kw in _normalize(paper.get("title", "")):
                    score += 3
                else:
                    score += 1

        # Bonus: arXiv category code alignment
        cat_bonus = {
            "llms": ["cs.cl", "cs.lg"],
            "generative-ai": ["cs.cv", "cs.lg"],
            "computer-vision": ["cs.cv"],
            "audio-speech": ["cs.sd", "eess.as"],
            "alignment": ["cs.ai", "cs.lg"],
            "reasoning-agents": ["cs.ai", "cs.lg", "cs.cl"],
            "ml-theory": ["stat.ml", "cs.lg"],
            "ai-science": ["q-bio", "cs.ce", "physics"],
            "code-ai": ["cs.se", "cs.pl"],
            "safety-privacy": ["cs.cr", "cs.ai"],
            "efficient-ai": ["cs.lg", "cs.ar"],
            "multimodal": ["cs.cv", "cs.cl"],
        }
        for bonus_cat in cat_bonus.get(slug, []):
            if bonus_cat in arxiv_cats:
                score += 2

        if score > 0:
            matched.append({
                "emoji": emoji,
                "name": name,
                "slug": slug,
                "score": score,
            })

    # Sort by score and take top N
    matched.sort(key=lambda x: x["score"], reverse=True)
    result = matched[:top_n]

    # Fallback if nothing matched
    if not result:
        result = [{"emoji": "🤖", "name": "LLMs & Language Models", "slug": "llms", "score": 0}]

    return result


def classify_papers(papers: list[dict]) -> list[dict]:
    """Classify all papers and attach 'categories' field to each."""
    for paper in papers:
        paper["categories"] = classify_paper(paper)
    return papers


def get_all_category_slugs() -> list[str]:
    """Return list of all category slugs."""
    return [slug for _, _, slug, _ in CATEGORIES]


def get_category_display(slug: str) -> Optional[tuple[str, str]]:
    """Get emoji and display name for a category slug."""
    for emoji, name, s, _ in CATEGORIES:
        if s == slug:
            return emoji, name
    return None
