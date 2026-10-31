"""
tests/test_curator.py
Unit tests for curator.py. No network calls: the Groq client is mocked.
"""
import sys
import os
import json
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import curator
import groq_summarizer as gs

GOOD = {
    "tldr": "A small model learns to compress speech features for phones.",
    "whats_new": "It distils a large mixture-of-experts model into one that runs on a phone CPU.",
    "key_result": "Word error rate stays within 0.3 points of the teacher at a tenth of the size.",
    "why_it_matters": "Speech recognition can now run offline on cheap phones without a server.",
    "build_ideas": ["Build an offline voice notes app.", "Add voice commands to a mobile game."],
    "difficulty": "Intermediate",
    "difficulty_reason": "Needs a GPU for distillation and basic audio knowledge.",
}


def test_parse_notes_accepts_good_json_and_normalises():
    notes = curator.parse_notes(json.dumps(GOOD))
    assert notes["difficulty"] == "intermediate"
    assert len(notes["build_ideas"]) == 2
    assert notes["key_result"].startswith("Word error rate")


def test_parse_notes_handles_code_fence():
    raw = "```json\n" + json.dumps(GOOD) + "\n```"
    assert curator.parse_notes(raw)["tldr"] == GOOD["tldr"]


def test_parse_notes_rejects_bad_output():
    assert curator.parse_notes("") is None
    assert curator.parse_notes("not json") is None
    assert curator.parse_notes("[1, 2]") is None
    assert curator.parse_notes(json.dumps(dict(GOOD, difficulty="easy"))) is None
    assert curator.parse_notes(json.dumps(dict(GOOD, build_ideas=["Only one idea here."]))) is None
    assert curator.parse_notes(json.dumps(dict(GOOD, tldr=" ".join(["word"] * 40)))) is None
    assert curator.parse_notes(json.dumps(dict(GOOD, why_it_matters="This paper shows a speech model."))) is None


def test_parse_notes_drops_bad_optional_fields():
    notes = curator.parse_notes(json.dumps(dict(GOOD, key_result=None, difficulty_reason=5)))
    assert notes is not None
    assert notes["key_result"] is None
    assert notes["difficulty_reason"] is None


def test_find_code_url_never_invents_links():
    assert curator.find_code_url({"github_repo": "https://github.com/a/b"}) == "https://github.com/a/b"
    assert curator.find_code_url({"abstract": "Code is at https://github.com/x/y."}) == "https://github.com/x/y"
    assert curator.find_code_url({"abstract": "No links here."}) is None


def _response(content, finish="stop"):
    choice = MagicMock(finish_reason=finish)
    choice.message.content = content
    return MagicMock(choices=[choice])


def test_curate_papers_fills_notes_and_why_it_matters():
    client = MagicMock()
    client.chat.completions.create.return_value = _response(json.dumps(GOOD))
    paper = {"id": "1", "title": "T", "abstract": "A."}
    with patch.object(gs, "_get_api_key", return_value="key"), \
         patch.object(gs, "_get_client", return_value=client), \
         patch.object(gs, "_active_models", ["m1"]), patch.object(gs, "_auth_failed", False):
        curator.curate_papers([paper])
    assert paper["curator"]["tldr"] == GOOD["tldr"]
    assert paper["why_it_matters"] == GOOD["why_it_matters"]
    assert paper["summary_source"] == "groq:m1"
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["response_format"] == {"type": "json_object"}


def test_curate_falls_back_when_output_is_bad():
    client = MagicMock()
    client.chat.completions.create.return_value = _response("{}")
    paper = {"id": "1", "title": "T", "abstract": "A."}
    with patch.object(gs, "_get_api_key", return_value="key"), \
         patch.object(gs, "_get_client", return_value=client), \
         patch.object(gs, "_active_models", ["m1", "m2"]), patch.object(gs, "_auth_failed", False), \
         patch.object(curator.time, "sleep"):
        curator.curate_papers([paper])
    assert paper["curator"] is None
    assert "why_it_matters" not in paper  # groq_summarizer writes it next
    assert client.chat.completions.create.call_count == 2


def test_curate_skips_without_api_key():
    paper = {"id": "1", "title": "T", "abstract": "A."}
    with patch.object(gs, "_get_api_key", return_value=""):
        curator.curate_papers([paper])
    assert paper["curator"] is None


def test_summarizer_keeps_curator_line():
    paper = {"id": "1", "title": "T", "abstract": "A.", "why_it_matters": "Kept.", "summary_source": "groq:m1"}
    with patch.object(gs, "get_summary") as get_summary:
        gs.summarize_papers([paper])
    get_summary.assert_not_called()
    assert paper["why_it_matters"] == "Kept."
