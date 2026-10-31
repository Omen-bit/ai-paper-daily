"""
tests/test_technologies.py
Unit tests for technologies.py: which papers count for which technology.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from technologies import TECHNOLOGIES, TECH_NAMES, tag


def test_titles_are_enough():
    assert tag("AgentFlow: Multi-Agent Planning with Tool Calling") == ["agents", "tool-use"]
    assert tag("GRPO for Math Reasoning") == ["reasoning", "rl"]
    assert tag("Mamba-2 for Long-Context Video Generation") == ["long-context", "ssm", "video-gen"]


def test_one_passing_mention_in_the_abstract_is_not_enough():
    assert tag("Rethinking Benchmarks", "Unlike RAG, we do not retrieve.") == []
    assert tag("Better Retrieval", "We build a RAG system. Our RAG pipeline is faster.") == ["rag"]


def test_lookalike_words_do_not_match():
    assert tag("Ragged Tensors for Agentless Pipelines", "drag and drop, image ragging") == []
    assert tag("Hello world") == []
    assert tag("", None) == []


def test_every_technology_has_a_unique_id_and_name():
    ids = [t[0] for t in TECHNOLOGIES]
    assert len(ids) == len(set(ids)) == len(TECH_NAMES)
    assert all(TECH_NAMES[i] for i in ids)
