"""
tests/test_classifier.py
15 hand-written examples with expected primary categories.
At least one of the returned categories must match the expected value.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from classifier import classify_paper, MIN_CATEGORY_SCORE

# Each entry: (title, abstract, expected_primary_slug)
EXAMPLES = [
    # 1. Clearly a diffusion / generative AI paper
    (
        "Denoising Diffusion Probabilistic Models for High-Resolution Image Synthesis",
        "We propose a class of latent diffusion models trained with denoising score "
        "matching. Our method achieves state-of-the-art results on text-to-image "
        "benchmarks using a stable diffusion framework with ddpm objectives.",
        "generative-ai",
    ),
    # 2. Clearly reasoning / agents
    (
        "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models",
        "We explore chain-of-thought prompting as a technique for enabling mathematical "
        "reasoning and logical reasoning in autoregressive language models, showing "
        "significant gains on GSM8K.",
        "reasoning-agents",
    ),
    # 3. Computer vision object detection
    (
        "YOLO v10: Real-Time Object Detection with Transformer Backbone",
        "We present a new real-time object detection framework using bounding box "
        "regression and semantic segmentation heads. Our model achieves fast inference "
        "on edge computing devices with improved mAP.",
        "computer-vision",
    ),
    # 4. Efficient AI / quantization
    (
        "LLM.int8(): 8-bit Matrix Multiplication for Transformers at Scale",
        "We develop a quantization procedure that reduces transformer model size via "
        "8-bit quantization and knowledge distillation, enabling low-rank adaptation "
        "and parameter efficient fine-tuning on mobile devices.",
        "efficient-ai",
    ),
    # 5. Speech / audio
    (
        "Whisper: Robust Speech Recognition via Large-Scale Weak Supervision",
        "We present Whisper, a general-purpose automatic speech recognition model "
        "trained on diverse multilingual data. It achieves strong results in speech "
        "translation and spoken language understanding.",
        "audio-speech",
    ),
    # 6. AI safety / adversarial
    (
        "Certified Adversarial Robustness via Randomized Smoothing",
        "We prove certified robustness guarantees against adversarial attack using "
        "randomized smoothing. Our method also reduces hallucination and improves "
        "uncertainty quantification in deployed classifiers.",
        "safety-privacy",
    ),
    # 7. Code AI
    (
        "CodeBERT: A Pre-Trained Model for Programming and Natural Languages",
        "We propose CodeBERT for code generation and code completion tasks. The model "
        "supports automated debugging, vulnerability detection, and code review "
        "automation across multiple programming languages.",
        "code-ai",
    ),
    # 8. RLHF / alignment
    (
        "Direct Preference Optimization: Your Language Model is Secretly a Reward Model",
        "We introduce direct preference optimization (DPO), an alternative to RLHF "
        "that implicitly learns a reward model from human preferences without "
        "reinforcement learning from human feedback or a separate reward modeling step.",
        "alignment",
    ),
    # 9. ML theory / scaling laws
    (
        "Scaling Laws for Neural Language Models",
        "We study scaling laws for transformer models and find that loss follows a "
        "power law in model size, dataset size, and compute. We analyze training "
        "dynamics and convergence analysis under Adam optimizer settings.",
        "ml-theory",
    ),
    # 10. Multimodal
    (
        "CLIP: Learning Transferable Visual Models from Natural Language Supervision",
        "We introduce CLIP, a vision-language model trained with contrastive learning "
        "on image-text alignment tasks. It enables zero-shot image classification "
        "and visual question answering without task-specific fine-tuning.",
        "multimodal",
    ),
    # 11. AI for science / healthcare
    (
        "AlphaFold2: Highly Accurate Protein Structure Prediction",
        "We present AlphaFold, a system for protein structure prediction using "
        "attention-based networks. It achieves near-experimental accuracy on drug "
        "discovery benchmarks and genomics tasks.",
        "ai-science",
    ),
    # 12. LLMs (specific: instruction tuning)
    (
        "FLAN: Finetuned Language Models Are Zero-Shot Learners",
        "We show that instruction tuning on a mixture of tasks substantially improves "
        "zero-shot performance on held-out language model benchmarks. We fine-tune "
        "T5 and encoder-decoder architectures using task descriptions.",
        "llms",
    ),
    # 13. Reasoning + agents (agentic tool use)
    (
        "ReAct: Synergizing Reasoning and Acting in Language Models",
        "We propose ReAct prompting, interleaving chain-of-thought reasoning with "
        "tool calling and tool use actions. The autonomous agent outperforms baselines "
        "on web agent tasks requiring multi-step decision making.",
        "reasoning-agents",
    ),
    # 14. Fallback: obscure paper that should get Other ML
    (
        "On the Expressive Power of Tensor Networks",
        "We analyze tensor networks from an algebraic perspective. Our results "
        "concern contraction complexity bounds and have no immediate connection "
        "to deep learning systems.",
        "other-ml",
    ),
    # 15. Generative AI (video generation)
    (
        "Sora: Video Generation Models as World Simulators",
        "We present a text-to-video model trained on diverse video data using "
        "a latent diffusion approach. The model produces high-fidelity video "
        "generation and demonstrates video-language understanding capabilities.",
        "generative-ai",
    ),
]


def test_classifier_examples():
    passed = 0
    failed = 0
    failures = []

    for i, (title, abstract, expected) in enumerate(EXAMPLES, 1):
        paper = {"title": title, "abstract": abstract, "arxiv_categories": []}
        result = classify_paper(paper)
        returned_slugs = [c["slug"] for c in result]

        if expected in returned_slugs:
            passed += 1
        else:
            failed += 1
            failures.append({
                "example": i,
                "title": title[:60],
                "expected": expected,
                "got": returned_slugs,
                "scores": [(c["slug"], c["score"]) for c in result],
            })

    total = len(EXAMPLES)
    print(f"\nClassifier test: {passed}/{total} passed ({100*passed//total}%)")
    if failures:
        print("\nFailed examples:")
        for f in failures:
            print(f"  [{f['example']}] {f['title']}")
            print(f"       expected: {f['expected']}")
            print(f"       got:      {f['got']}")
            print(f"       scores:   {f['scores']}")

    assert passed / total >= 0.80, (
        f"Classifier accuracy {passed}/{total} below 80% threshold. "
        f"Failed: {[f['example'] for f in failures]}"
    )


if __name__ == "__main__":
    test_classifier_examples()
