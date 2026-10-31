"""
technologies.py
The specific technologies the Trends page tracks (AI agents, RAG, mixture of
experts, ...), and how a paper is matched to them.

A paper counts for a technology when its title mentions it, or when its
abstract mentions it at least twice. One passing mention in an abstract
("unlike RAG, we ...") is not enough.

To track a new technology, add a line to TECHNOLOGIES. Patterns are regular
expressions, matched without regard to case unless the entry says so.
"""
import re

# (id, name shown on the site, pattern, case_sensitive_pattern or None)
TECHNOLOGIES = [
    ("agents", "AI agents", r"\bagent(?:s|ic)?\b|\bmulti-agent\b", None),
    ("computer-use", "Computer-use and web agents", r"\bGUI agents?\b|\bcomputer[- ]use\b|\bweb agents?\b|\bbrowser agents?\b|\bmobile agents?\b|\bweb navigation\b", None),
    ("tool-use", "Tool use", r"\btool[- ](?:use|using|calling|learning|augmented)\b|\bfunction[- ]calling\b", r"\bMCP\b"),
    ("reasoning", "Reasoning models", r"\breasoning\b|\bchain[- ]of[- ]thought\b|\btest[- ]time (?:compute|scaling)\b", r"\bCoT\b"),
    ("rl", "Reinforcement learning", r"\breinforcement learning\b|\breward models?\b|\bpolicy optimi[sz]ation\b", r"\b(?:RLHF|RLVR|GRPO|PPO|DPO)\b"),
    ("rag", "Retrieval (RAG)", r"\bretrieval[- ]augmented\b|\bretrieval-based generation\b", r"\bRAG\b"),
    ("long-context", "Long context and memory", r"\blong[- ]context\b|\bcontext windows?\b|\bkv[- ]cache\b|\blong[- ]term memory\b", None),
    ("moe", "Mixture of experts", r"\bmixture[- ]of[- ]experts\b", r"\bMoEs?\b"),
    ("ssm", "State-space and linear attention", r"\bstate[- ]space models?\b|\blinear attention\b|\bmamba\b", r"\bSSMs?\b"),
    ("efficient", "Small and efficient models", r"\bquanti[sz](?:ation|ed|ing)\b|\bpruning\b|\bdistillation\b|\bsmall language models?\b|\bon[- ]device\b", r"\bSLMs?\b"),
    ("multimodal", "Vision-language models", r"\bvision[- ]language models?\b|\bmultimodal large language\b|\bmultimodal llms?\b", r"\b(?:VLMs?|MLLMs?|LVLMs?)\b"),
    ("diffusion", "Diffusion and flow matching", r"\bdiffusion\b|\bflow matching\b|\brectified flow\b", None),
    ("video-gen", "Video generation", r"\bvideo (?:generation|diffusion|synthesis|generative)\b|\btext[- ]to[- ]video\b|\bimage[- ]to[- ]video\b", None),
    ("world-models", "World models", r"\bworld models?\b", None),
    ("3d", "3D and Gaussian splatting", r"\bgaussian splatting\b|\bnerfs?\b|\bneural radiance\b|\bpoint clouds?\b|\b3d (?:generation|reconstruction|scene)\b", r"\b3DGS\b"),
    ("robotics", "Robotics and embodied AI", r"\brobot(?:s|ic|ics)?\b|\bembodied\b|\bvision[- ]language[- ]action\b", r"\bVLAs?\b"),
    ("speech", "Speech and audio", r"\bspeech\b|\baudio\b|\btext[- ]to[- ]speech\b|\bspoken\b", r"\b(?:ASR|TTS)\b"),
    ("code", "Code generation", r"\bcode generation\b|\bcoding\b|\bsoftware engineering\b|\bprogram synthesis\b|\bcode llms?\b", r"\bSWE-"),
    ("safety", "Safety and jailbreaks", r"\bjailbreak\w*\b|\bred[- ]teaming\b|\bsafety\b|\bharmful\b|\bguardrails?\b", None),
    ("hallucination", "Hallucination", r"\bhallucinat\w*\b", None),
    ("synthetic-data", "Synthetic data", r"\bsynthetic data\b|\bdata synthesis\b|\bsynthesi[sz]ed data\b", None),
    ("science", "AI for science", r"\bscientific discovery\b|\bai scientists?\b|\bprotein\w*\b|\bmolecul\w*\b|\bdrug discovery\b|\bmaterials? (?:discovery|science)\b", None),
]

TECH_NAMES = {tid: name for tid, name, _, _ in TECHNOLOGIES}

_COMPILED = [
    (tid, re.compile(p, re.IGNORECASE), re.compile(cs) if cs else None)
    for tid, _, p, cs in TECHNOLOGIES
]


def _count(rx_i, rx_cs, text: str, stop: int) -> int:
    n = 0
    for rx in (rx_i, rx_cs):
        if rx is None:
            continue
        for _ in rx.finditer(text):
            n += 1
            if n >= stop:
                return n
    return n


def tag(title: str, abstract: str | None = None) -> list[str]:
    """The technologies a paper is about, in TECHNOLOGIES order."""
    title = title or ""
    abstract = abstract or ""
    out = []
    for tid, rx_i, rx_cs in _COMPILED:
        if _count(rx_i, rx_cs, title, 1) >= 1 or (abstract and _count(rx_i, rx_cs, abstract, 2) >= 2):
            out.append(tid)
    return out
