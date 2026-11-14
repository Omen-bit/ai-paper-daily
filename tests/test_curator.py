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


def test_check_question_needs_its_answer():
    good = dict(GOOD, check_question="What does the model trade for speed?",
                check_answer="It drops the decoder cache to run on a phone.")
    notes = curator.parse_notes(json.dumps(good))
    assert notes["check_question"] == good["check_question"]
    assert notes["check_answer"] == good["check_answer"]
    lone = curator.parse_notes(json.dumps(dict(good, check_answer=None)))
    assert lone["check_question"] is None and lone["check_answer"] is None
    assert curator.parse_notes(json.dumps(GOOD))["check_question"] is None


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


def test_reading_levels_and_terms_are_checked_against_the_paper():
    abstract = "We compress each frame 300 times and learn a latent action space from video."
    good = dict(GOOD, tldr="It learns a latent action space from video.",
                tldr_simple="It learns how things move by watching videos.",
                tldr_expert="Video features compressed 300 times give a latent action space.",
                terms=[{"term": "latent action space", "meaning": "A few numbers that describe what moved between frames."},
                       {"term": "made-up term", "meaning": "This term is not in the paper at all."},
                       "not a dict"])
    notes = curator.parse_notes(json.dumps(good), abstract)
    assert notes["tldr_simple"] and notes["tldr_expert"]
    assert [t["term"] for t in notes["terms"]] == ["latent action space"]


def test_reading_level_with_a_new_number_is_dropped():
    abstract = "We compress each frame 300 times."
    bad = dict(GOOD, tldr_expert="Frames are compressed 500 times with a new tokenizer.")
    notes = curator.parse_notes(json.dumps(bad), abstract)
    assert notes is not None and notes["tldr_expert"] is None and notes["terms"] == []


# --- The repair loop and grounding check (Phase 5) ---

ABSTRACT = "We distil a speech model to run on a phone CPU, keeping word error rate within 0.3 points."


def _run(replies, models=("m1",), abstract=ABSTRACT):
    """Curate one paper with the model's replies given in call order."""
    client = MagicMock()
    client.chat.completions.create.side_effect = [_response(r if isinstance(r, str) else json.dumps(r))
                                                  for r in replies]
    paper = {"id": "1", "title": "T", "abstract": abstract}
    with patch.object(gs, "_get_api_key", return_value="key"), \
         patch.object(gs, "_get_client", return_value=client), \
         patch.object(gs, "_active_models", list(models)), patch.object(gs, "_auth_failed", False), \
         patch.object(curator.time, "sleep"):
        notes, source, log = curator.curate_with_log(paper)
    return notes, source, log, client


def _users(client):
    return [c.kwargs["messages"][1]["content"] for c in client.chat.completions.create.call_args_list]


def test_check_notes_says_which_fields_failed_and_why():
    notes, problems = curator.check_notes(dict(GOOD, tldr=" ".join(["word"] * 40), difficulty="easy",
                                               build_ideas=["One idea only."]))
    assert notes is None
    assert "tldr: 40 words, the limit is 30" in problems
    assert any(p.startswith("difficulty: must be one of") for p in problems)
    assert any(p.startswith("build_ideas: need 2 or 3") for p in problems)
    assert curator.check_notes(None)[1] == ["the reply was not a JSON object"]


def test_numbers_the_abstract_lacks_are_problems_or_dropped():
    bad = dict(GOOD, tldr="A small model cuts errors by 45% on phones.", key_result="Errors fall 12 points.")
    notes, problems = curator.check_notes(bad, ABSTRACT)
    assert notes is None and problems == ["tldr: mentions 45, which the abstract doesn't"]
    notes, problems = curator.check_notes(dict(GOOD, key_result="Errors fall 12 points."), ABSTRACT)
    assert problems == [] and notes["key_result"] is None


def test_a_draft_with_one_bad_field_is_repaired_not_thrown_away():
    long_tldr = dict(GOOD, tldr=" ".join(["word"] * 40))
    fixed = {"tldr": "A small speech model runs on a phone CPU."}
    notes, source, log, client = _run([long_tldr, fixed, {"unsupported": []}])
    assert notes["tldr"] == fixed["tldr"] and notes["whats_new"] == GOOD["whats_new"]
    assert source == "groq:m1" and log == {"repairs": 1, "grounded": True, "flagged": []}
    repair_prompt = _users(client)[1]
    assert "tldr: 40 words, the limit is 30" in repair_prompt and "exactly these keys, fixed: tldr" in repair_prompt


def test_after_two_failed_repairs_the_next_model_drafts():
    bad = dict(GOOD, difficulty="easy")
    notes, source, log, client = _run([bad, {"difficulty": "easy"}, {"difficulty": "trivial"},
                                       GOOD, {"unsupported": []}], models=("m1", "m2"))
    assert source == "groq:m2" and log["repairs"] == 2
    assert client.chat.completions.create.call_count == 5


def test_hopeless_drafts_skip_repair():
    notes, source, log, client = _run(["{}", "{}"], models=("m1", "m2"))
    assert notes is None and source == "none" and log["repairs"] == 0
    assert client.chat.completions.create.call_count == 2


def test_ground_check_drops_flagged_optional_fields():
    good = dict(GOOD, check_question="What does the model trade for speed?",
                check_answer="It drops the decoder cache to run on a phone.")
    notes, _, log, client = _run([good, {"unsupported": ["key_result", "check_answer", "not_a_field"],
                                         "why": "Not in the abstract."}])
    assert notes["key_result"] is None and notes["check_question"] is None and notes["check_answer"] is None
    assert notes["tldr"] == GOOD["tldr"] and log["flagged"] == ["key_result", "check_answer"]
    assert client.chat.completions.create.call_args_list[-1].kwargs["model"] == "m1"  # the last model checks


def test_ground_check_sends_a_flagged_required_field_back_to_repair():
    fixed = {"whats_new": "It shrinks a speech model so it runs on a phone CPU."}
    notes, _, log, client = _run([GOOD, {"unsupported": ["whats_new"]}, fixed, {"unsupported": []}])
    assert notes["whats_new"] == fixed["whats_new"] and log["repairs"] == 1 and log["flagged"] == []
    assert "whats_new: states something the abstract doesn't support" in _users(client)[2]


def test_a_failed_ground_check_keeps_the_notes():
    client = MagicMock()
    client.chat.completions.create.side_effect = [_response(json.dumps(GOOD)), RuntimeError("503")]
    paper = {"id": "1", "title": "T", "abstract": ABSTRACT}
    with patch.object(gs, "_get_api_key", return_value="key"), \
         patch.object(gs, "_get_client", return_value=client), \
         patch.object(gs, "_active_models", ["m1"]), patch.object(gs, "_auth_failed", False):
        notes, source, log = curator.curate_with_log(paper)
    assert notes["tldr"] == GOOD["tldr"] and source == "groq:m1" and log["grounded"] is False


def test_curate_papers_records_the_log():
    client = MagicMock()
    client.chat.completions.create.side_effect = [_response(json.dumps(GOOD)), _response('{"unsupported": []}')]
    paper = {"id": "1", "title": "T", "abstract": ABSTRACT}
    with patch.object(gs, "_get_api_key", return_value="key"), \
         patch.object(gs, "_get_client", return_value=client), \
         patch.object(gs, "_active_models", ["m1"]), patch.object(gs, "_auth_failed", False):
        curator.curate_papers([paper])
    assert paper["curator_log"] == {"repairs": 0, "grounded": True, "flagged": []}


def test_headline_is_optional_short_and_grounded():
    import curator
    src = "We delete 0.05% of weights."
    assert curator._headline("Delete 0.05% of an LLM's weights, skip fine-tuning.", src) == \
        "Delete 0.05% of an LLM's weights, skip fine-tuning"
    assert curator._headline("Delete 7% of weights", src) is None  # a number the paper doesn't have
    assert curator._headline("Is deleting weights all you need for every model?", src) is None
    assert curator._headline(None, src) is None
