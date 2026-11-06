"""
curator.py
The Curator agent: structured reading notes for each featured paper,
written by Groq as JSON (TL;DR, what's new, key result, build ideas, difficulty).

It runs as a small LangGraph graph per paper:
  draft     one call for the full notes (the next model in GROQ_MODELS if a call fails)
  validate  every field checked: word limits, required fields, and no numbers the abstract lacks
  repair    asks the same model to fix only the failing fields, with the reasons (2 rounds at most)
  ground    a smaller model checks each fact against the abstract; flagged optional
            fields are dropped and a flagged required field goes back to repair

A paper whose notes still fail keeps curator=None and gets the usual "Why it matters"
line from groq_summarizer, so the daily run never breaks because of this step.

The code link never comes from the model, because it could make one up. It is
taken from Hugging Face's githubRepo field or from a link in the abstract.
"""
import json
import re
import time
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph

import groq_summarizer as gs

DIFFICULTIES = ("beginner", "intermediate", "advanced")

# Upper word limits per field. Output over a limit is rejected, not trimmed,
# because a trimmed sentence reads as broken.
LIMITS = {
    "tldr": 30,
    "whats_new": 45,
    "key_result": 40,
    "why_it_matters": 40,
    "difficulty_reason": 25,
    "build_idea": 25,
    "check_question": 30,
    "check_answer": 40,
    "tldr_simple": 35,
    "tldr_expert": 40,
    "term": 5,
    "meaning": 30,
}

SYSTEM_PROMPT = """You are the Curator for AI Papers Daily, a site for people who read AI papers and build projects from them.
Read the paper's title and abstract and return reading notes as one JSON object with exactly these keys:

"tldr": one plain sentence, at most 25 words, saying what the paper does.
"whats_new": one or two sentences, at most 40 words, on what is new compared with earlier work.
"key_result": the single most important result stated in the abstract, with its number if one is given, at most 35 words. Use null if the abstract states no result.
"why_it_matters": one sentence, at most 30 words, on why builders should care. Do not start with "This paper".
"build_ideas": a list of 2 or 3 concrete projects a developer could build with this work, each at most 20 words and starting with a verb.
"difficulty": one of "beginner", "intermediate", "advanced", for how hard it is to reproduce or use.
"difficulty_reason": one short phrase, at most 20 words, explaining the difficulty (for example the compute or background needed).
"check_question": one short question, at most 25 words, that checks whether a reader understood the paper's main idea. Its answer must be in the abstract.
"check_answer": the answer to check_question in one or two sentences, at most 35 words.
"tldr_simple": the tldr again for someone new to AI, at most 30 words, with no jargon and no acronyms.
"tldr_expert": the tldr again for a researcher in the field, at most 35 words, naming the exact technique and setting.
"terms": a list of up to 3 objects {"term": ..., "meaning": ...} for technical terms a newcomer would not know. Each term must appear word for word in the tldr or the abstract. Each meaning is one plain sentence, at most 25 words.

Rules: use only facts from the abstract and never invent numbers, datasets or links. Write in plain language and avoid hype words such as "groundbreaking" or "revolutionary". Return only the JSON object."""

_CODE_LINK = re.compile(r"https?://(?:www\.)?(?:github\.com|gitlab\.com|huggingface\.co)/[\w.\-/]+", re.I)


def find_code_url(paper: dict) -> Optional[str]:
    """Return a real code link for the paper, or None. Never asks the model."""
    repo = (paper.get("github_repo") or "").strip()
    if repo.startswith("https://"):
        return repo
    match = _CODE_LINK.search(paper.get("abstract") or "")
    if match:
        return match.group(0).rstrip(".,;)/")
    return None


def _sentence(value, limit: int) -> Optional[str]:
    """A non-empty string within the word limit, else None."""
    if not isinstance(value, str):
        return None
    text = " ".join(value.split()).strip().strip('"')
    if len(text) < 8 or len(text.split()) > limit:
        return None
    return text


def _numbers_known(text: str, source: str) -> bool:
    """True when every number in text also appears in source."""
    plain = source.replace(",", "")
    return all(n.replace(",", "") in plain for n in re.findall(r"\d[\d,.]*\d|\d", text))


def _terms(value, source: str) -> list[dict]:
    """Up to three {term, meaning} pairs whose term really appears in the paper's text."""
    out = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        term = " ".join(str(item.get("term") or "").split()).strip().strip('"')
        if not (3 <= len(term) <= 60) or len(term.split()) > LIMITS["term"]:
            continue
        meaning = _sentence(item.get("meaning"), LIMITS["meaning"])
        if not meaning or term.lower() not in source.lower():
            continue
        if any(t["term"].lower() == term.lower() for t in out):
            continue
        out.append({"term": term, "meaning": meaning})
    return out[:3]


REQUIRED = ("tldr", "whats_new", "why_it_matters", "difficulty", "build_ideas")


def _load_json(raw) -> Optional[dict]:
    """The JSON object in a model reply, or None."""
    if not raw:
        return None
    # Models sometimes wrap JSON in a code fence despite json mode
    text = str(raw).strip()
    fence = re.search(r"\{.*\}", text, re.S)
    if fence:
        text = fence.group(0)
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _why_not(value, limit: int) -> str:
    """Why a required sentence was rejected, in words a model can act on."""
    if not isinstance(value, str) or not value.strip():
        return "missing"
    words = len(value.split())
    if words > limit:
        return f"{words} words, the limit is {limit}"
    return "too short"


def _new_numbers(text: str, source: str) -> list[str]:
    plain = source.replace(",", "")
    return [n for n in re.findall(r"\d[\d,.]*\d|\d", text or "") if n.replace(",", "") not in plain]


def check_notes(data: Optional[dict], abstract: str = "") -> tuple[Optional[dict], list[str]]:
    """
    Clean notes from the model's JSON, plus the problems with any required field.
    Notes are None when a required field fails; the problems say which and why,
    so the repair step can ask for just those fields again.
    Optional fields that fail their checks are dropped quietly.
    With an abstract, numbers it doesn't contain are not allowed in the notes.
    """
    if not isinstance(data, dict):
        return None, ["the reply was not a JSON object"]
    problems = []
    notes = {
        "tldr": _sentence(data.get("tldr"), LIMITS["tldr"]),
        "whats_new": _sentence(data.get("whats_new"), LIMITS["whats_new"]),
        "key_result": _sentence(data.get("key_result"), LIMITS["key_result"]),
        "why_it_matters": _sentence(data.get("why_it_matters"), LIMITS["why_it_matters"]),
        "difficulty": str(data.get("difficulty", "")).strip().lower(),
        "difficulty_reason": _sentence(data.get("difficulty_reason"), LIMITS["difficulty_reason"]),
        "check_question": _sentence(data.get("check_question"), LIMITS["check_question"]),
        "check_answer": _sentence(data.get("check_answer"), LIMITS["check_answer"]),
    }
    for key in ("tldr", "whats_new", "why_it_matters"):
        if not notes[key]:
            problems.append(f"{key}: {_why_not(data.get(key), LIMITS[key])}")
        elif abstract and _new_numbers(notes[key], abstract):
            problems.append(f"{key}: mentions {', '.join(_new_numbers(notes[key], abstract))}, "
                            "which the abstract doesn't")
    if notes["why_it_matters"] and notes["why_it_matters"].lower().startswith("this paper"):
        problems.append('why_it_matters: must not start with "This paper"')
    if notes["difficulty"] not in DIFFICULTIES:
        problems.append(f"difficulty: must be one of {', '.join(DIFFICULTIES)}, not {notes['difficulty'] or 'empty'}")
    # Optional facts with numbers the abstract doesn't have are dropped
    if abstract:
        for key in ("key_result", "check_answer"):
            if notes[key] and _new_numbers(notes[key], abstract):
                notes[key] = None

    # The other reading levels may not add facts: every number in them must be in the abstract
    source_text = (abstract or "") + " " + (notes["tldr"] or "")
    for key in ("tldr_simple", "tldr_expert"):
        text = _sentence(data.get(key), LIMITS[key])
        notes[key] = text if text and _numbers_known(text, source_text) else None
    notes["terms"] = _terms(data.get("terms"), source_text)
    # The question is only useful with its answer, so keep both or neither
    if not (notes["check_question"] and notes["check_answer"]):
        notes["check_question"] = notes["check_answer"] = None
    ideas = data.get("build_ideas")
    ideas = ideas if isinstance(ideas, list) else []
    notes["build_ideas"] = [i for i in (_sentence(x, LIMITS["build_idea"]) for x in ideas) if i][:3]
    if len(notes["build_ideas"]) < 2:
        problems.append(f"build_ideas: need 2 or 3 ideas of at most {LIMITS['build_idea']} words each, "
                        f"{len(notes['build_ideas'])} usable")
    return (None if problems else notes), problems


def parse_notes(raw: str, abstract: str = "") -> Optional[dict]:
    """
    Turn the model's reply into clean notes, or None if it is unusable.
    Required: tldr, whats_new, why_it_matters, 2+ build ideas, a known difficulty.
    Optional: key_result, difficulty_reason and the check question with its answer (dropped when they fail checks).
    """
    data = _load_json(raw)
    return check_notes(data, abstract)[0] if data is not None else None


MAX_REPAIRS = 2      # rounds of "fix just these fields" per paper
REPAIRABLE = 3       # a draft with more failing required fields goes to the next model instead

REPAIR_PROMPT = """Your reading notes for this paper failed some checks. Fix only the fields listed.
Problems:
{problems}
Return one JSON object with exactly these keys, fixed: {keys}.
Follow the same rules as before: plain language, facts only from the abstract, and keep within the word limits."""

GROUND_PROMPT = """You check reading notes about an AI paper against its abstract. Be strict.
A field is unsupported if it states a fact, number, name, dataset or comparison that the abstract does not state or clearly imply.
Build ideas and difficulty are opinions, so never flag them.
Return one JSON object: {"unsupported": ["field_name", ...], "why": "one short sentence"}. Use an empty list when everything is supported."""

GROUNDED_FIELDS = ("tldr", "whats_new", "key_result", "why_it_matters", "check_answer", "tldr_simple", "tldr_expert")


def _call(model: str, system: str, user: str, max_tokens: int) -> Optional[str]:
    """One JSON-mode Groq call. Returns the raw reply, or None when it was cut off."""
    client = gs._get_client()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
        temperature=0.2,
        **gs.call_options(model, max_tokens),
    )
    choice = response.choices[0]
    if choice.finish_reason == "length":
        return None
    return choice.message.content


def _paper_input(title: str, abstract: str) -> str:
    return f"Title: {title}\n\nAbstract: {gs._truncate_abstract(abstract, 2500)}"


def _ask(model: str, title: str, abstract: str) -> Optional[str]:
    """The first draft of the notes. Returns the raw reply or None."""
    return _call(model, SYSTEM_PROMPT, _paper_input(title, abstract), 1100)


def _failing_keys(problems: list[str]) -> list[str]:
    return list(dict.fromkeys(p.split(":", 1)[0] for p in problems if p.split(":", 1)[0] in REQUIRED))


# ---------------------------------------------------------------------------
# The Curator as a small LangGraph graph, one run per paper:
#   draft -> validate -> ground -> done
#              |   ^         |
#              v   |         v
#             repair <-------+    (at most MAX_REPAIRS rounds; then the next model, or give up)
# ---------------------------------------------------------------------------

class CuratorState(TypedDict, total=False):
    paper: dict
    models: list          # models left to try, current one first
    data: Optional[dict]  # the model's JSON so far, with repairs merged in
    notes: Optional[dict]
    problems: list
    repairs: int          # repair rounds used on the current model
    total_repairs: int
    unsupported: list     # fields the grounding check flagged
    grounded: bool
    source: str
    done: bool


def _draft(state: CuratorState) -> dict:
    paper = state["paper"]
    for i, model in enumerate(state["models"]):
        try:
            raw = _ask(model, paper.get("title", ""), paper.get("abstract", ""))
        except Exception as exc:
            error_str = str(exc)
            if gs._is_auth_error(error_str):
                gs._auth_failed = True
                print("  [curator] Auth error; stopping.")
                return {"models": [], "data": None, "done": True}
            print(f"  [curator] {model} failed: {error_str[:120]}")
            time.sleep(1)
            continue
        data = _load_json(raw)
        if data is not None:
            return {"models": state["models"][i:], "data": data, "repairs": 0}
        print(f"  [curator] {model} returned no usable JSON")
        time.sleep(0.5)
    return {"models": [], "data": None, "done": True}


def _validate(state: CuratorState) -> dict:
    notes, problems = check_notes(state.get("data"), state["paper"].get("abstract", ""))
    if problems:
        print(f"  [curator] {state['models'][0]}: {'; '.join(problems)}")
    # A grounding flag on a required field counts as a problem too
    flagged = [k for k in state.get("unsupported") or [] if k in REQUIRED]
    if notes and flagged:
        problems = [f"{k}: states something the abstract doesn't support" for k in flagged]
        notes = None
    return {"notes": notes, "problems": problems}


def _repair(state: CuratorState) -> dict:
    paper, model = state["paper"], state["models"][0]
    keys = _failing_keys(state["problems"])
    user = (_paper_input(paper.get("title", ""), paper.get("abstract", "")) + "\n\nYour notes so far:\n"
            + json.dumps({k: v for k, v in (state.get("data") or {}).items()}, ensure_ascii=False)
            + "\n\n" + REPAIR_PROMPT.format(problems="\n".join(f"- {p}" for p in state["problems"]),
                                            keys=", ".join(keys)))
    fixed = None
    try:
        fixed = _load_json(_call(model, SYSTEM_PROMPT, user, 700))
    except Exception as exc:
        print(f"  [curator] repair with {model} failed: {str(exc)[:120]}")
    data = dict(state.get("data") or {})
    if fixed:
        data.update({k: fixed[k] for k in keys if k in fixed})
    print(f"  [curator] Repair {state.get('repairs', 0) + 1} asked {model} to fix: {', '.join(keys)}")
    return {"data": data, "repairs": state.get("repairs", 0) + 1,
            "total_repairs": state.get("total_repairs", 0) + 1, "unsupported": [], "grounded": False}


def _next_model(state: CuratorState) -> dict:
    rest = state["models"][1:]
    if rest:
        print(f"  [curator] {state['models'][0]} couldn't get the notes right; trying {rest[0]}")
    return {"models": rest, "data": None, "notes": None, "repairs": 0, "unsupported": [], "grounded": False}


def _ground(state: CuratorState) -> dict:
    """
    A second, smaller model checks each fact in the notes against the abstract.
    Flagged optional fields are dropped; a flagged required field goes back to repair.
    If the check itself fails, the notes stand (they already passed the number checks).
    """
    notes, paper = dict(state["notes"]), state["paper"]
    checker = (gs._active_models or state["models"])[-1]
    shown = {k: notes[k] for k in GROUNDED_FIELDS if notes.get(k)}
    unsupported = []
    try:
        raw = _call(checker, GROUND_PROMPT,
                    f"Abstract: {gs._truncate_abstract(paper.get('abstract', ''), 2500)}\n\n"
                    f"Notes:\n{json.dumps(shown, ensure_ascii=False)}", 300)
        verdict = _load_json(raw) or {}
        unsupported = [k for k in verdict.get("unsupported") or [] if k in shown]
        if unsupported:
            print(f"  [curator] Ground check ({checker}) flagged {', '.join(unsupported)}: "
                  f"{str(verdict.get('why') or '')[:120]}")
    except Exception as exc:
        print(f"  [curator] Ground check skipped: {str(exc)[:120]}")
        return {"grounded": False}
    for k in unsupported:
        if k not in REQUIRED:
            notes[k] = None
            if k == "check_answer":
                notes["check_question"] = None
    return {"notes": notes, "unsupported": unsupported, "grounded": True}


def _after_draft(state: CuratorState) -> str:
    return END if state.get("done") or state.get("data") is None else "validate"


def _after_validate(state: CuratorState) -> str:
    if state.get("notes"):
        return "ground" if not state.get("grounded") else "finish"
    if state.get("repairs", 0) < MAX_REPAIRS and 0 < len(_failing_keys(state["problems"])) <= REPAIRABLE:
        return "repair"
    return "next_model"


def _after_ground(state: CuratorState) -> str:
    flagged = [k for k in state.get("unsupported") or [] if k in REQUIRED]
    if flagged and state.get("repairs", 0) < MAX_REPAIRS:
        return "validate"   # turns the flags into problems, then repair
    if flagged:
        print(f"  [curator] Keeping the notes: no repairs left for {', '.join(flagged)}")
    return "finish"


def _finish(state: CuratorState) -> dict:
    return {"source": f"groq:{state['models'][0]}", "done": True}


def _after_next_model(state: CuratorState) -> str:
    return "draft" if state.get("models") else END


_graph = None


def curator_graph():
    """The compiled Curator graph, built once."""
    global _graph
    if _graph is None:
        g = StateGraph(CuratorState)
        for name, fn in [("draft", _draft), ("validate", _validate), ("repair", _repair),
                         ("next_model", _next_model), ("ground", _ground), ("finish", _finish)]:
            g.add_node(name, fn)
        g.add_edge(START, "draft")
        g.add_conditional_edges("draft", _after_draft, ["validate", END])
        g.add_conditional_edges("validate", _after_validate, ["ground", "finish", "repair", "next_model"])
        g.add_edge("repair", "validate")
        g.add_conditional_edges("ground", _after_ground, ["validate", "finish"])
        g.add_conditional_edges("next_model", _after_next_model, ["draft", END])
        g.add_edge("finish", END)
        _graph = g.compile()
    return _graph


def curate_with_log(paper: dict) -> tuple[Optional[dict], str, dict]:
    """(notes, source, log). The log says how many repairs it took and what was flagged."""
    log = {"repairs": 0, "grounded": False, "flagged": []}
    if gs._auth_failed or not gs._get_api_key():
        return None, "none", log
    if gs._active_models is None:
        try:
            gs._active_models = gs._resolve_active_models()
        except Exception as exc:
            print(f"  [curator] Groq unavailable: {str(exc)[:120]}")
            return None, "none", log
    if not gs._active_models:
        return None, "none", log
    state = curator_graph().invoke(
        {"paper": paper, "models": list(gs._active_models), "repairs": 0, "total_repairs": 0},
        config={"run_name": f"curator-{paper.get('id', '')}", "recursion_limit": 40},
    )
    log = {"repairs": state.get("total_repairs", 0), "grounded": bool(state.get("grounded")),
           "flagged": list(state.get("unsupported") or [])}
    if state.get("notes") and state.get("source"):
        return state["notes"], state["source"], log
    return None, "none", log



def curate_papers(papers: list[dict]) -> list[dict]:
    """
    Add 'curator' (notes or None) and 'code_url' to each paper.
    When the notes include why_it_matters, it also fills the paper's
    'why_it_matters' so groq_summarizer can skip that paper.
    """
    print("\n[curator] Writing reading notes for the top picks...")
    done = repaired = 0
    for paper in papers:
        paper["code_url"] = find_code_url(paper)
        notes, source, log = curate_with_log(paper)
        paper["curator"] = notes
        paper["curator_log"] = log
        if notes:
            done += 1
            repaired += bool(log["repairs"])
            paper["curator_source"] = source
            paper["why_it_matters"] = notes["why_it_matters"]
            paper["summary_source"] = source
            print(f"  [curator] Notes for {paper.get('id')} from {source}")
    print(f"[curator] {done}/{len(papers)} papers got notes ({repaired} after a repair).")
    return papers
