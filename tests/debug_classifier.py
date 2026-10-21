import sys
sys.path.insert(0, "src")
from classifier import CATEGORIES, _normalize, MIN_CATEGORY_SCORE

cases = [
    ("efficient-ai", "LLM.int8(): 8-bit Matrix Multiplication for Transformers at Scale",
     "We develop a quantization procedure that reduces transformer model size via 8-bit quantization and knowledge distillation, enabling low-rank adaptation and parameter efficient fine-tuning on mobile devices."),
    ("audio-speech", "Whisper: Robust Speech Recognition via Large-Scale Weak Supervision",
     "We present Whisper, a general-purpose automatic speech recognition model trained on diverse multilingual data. It achieves strong results in speech translation and spoken language understanding."),
    ("multimodal", "CLIP: Learning Transferable Visual Models from Natural Language Supervision",
     "We introduce CLIP, a vision-language model trained with contrastive learning on image-text alignment tasks. It enables zero-shot image classification and visual question answering without task-specific fine-tuning."),
    ("llms", "FLAN: Finetuned Language Models Are Zero-Shot Learners",
     "We show that instruction tuning on a mixture of tasks substantially improves zero-shot performance on held-out language model benchmarks. We fine-tune T5 and encoder-decoder architectures using task descriptions."),
    ("generative-ai", "Sora: Video Generation Models as World Simulators",
     "We present a text-to-video model trained on diverse video data using a latent diffusion approach. The model produces high-fidelity video generation and demonstrates video-language understanding capabilities."),
]

print(f"Threshold: {MIN_CATEGORY_SCORE}")
for target_slug, title, abstract in cases:
    title_norm = _normalize(title)
    abstract_norm = _normalize(abstract)
    print(f"\n-- target: {target_slug} | '{title[:50]}'")
    for emoji, name, slug, specific_kws, broad_kws in CATEGORIES:
        if slug != target_slug:
            continue
        score = 0
        hits = []
        for kw in specific_kws:
            kw_norm = _normalize(kw)
            if kw_norm in title_norm:
                score += 3
                hits.append(f"T:{kw}(+3)")
            elif kw_norm in abstract_norm:
                score += 1
                hits.append(f"A:{kw}(+1)")
        for kw in broad_kws:
            kw_norm = _normalize(kw)
            if kw_norm in title_norm:
                score += 1
                hits.append(f"Bt:{kw}(+1)")
        print(f"   score={score} (threshold={MIN_CATEGORY_SCORE}) hits={hits}")
