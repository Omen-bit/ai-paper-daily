"""
scope.py
Catches a summary that claims more than the paper tested.

A paper that tested four Android phones must not be summed up as working "on any
phone". The prompts ask the model to name what was tested; this module is the
check in code behind that rule. It looks for widening words ("any phone",
"every language", "all devices", "universally", "regardless of") that the
abstract itself doesn't use, so a model can be asked to fix the sentence.

No model call: plain text matching, so it is cheap to run on every note.
"""
import re

# "any"/"every" widen almost whatever follows them in a summary
_ANY = re.compile(r"\b(any|every)\s+([a-z][a-z\-]+)", re.IGNORECASE)
# "all" is common in plain writing ("all its stars"), so only flag it before a
# word that names what a paper is tested on
_SCOPE_NOUNS = (
    "phones?|smartphones?|devices?|hardware|gpus?|cpus?|chips?|platforms?|robots?|"
    "models?|llms?|architectures?|sizes?|scales?|languages?|tasks?|domains?|datasets?|"
    "benchmarks?|settings?|environments?|users?|apps?|applications?|images?|videos?|"
    "modalities|languages|codebases?|problems?|cases?"
)
_ALL = re.compile(rf"\ball\s+(?:kinds\s+of\s+|types\s+of\s+|sorts\s+of\s+)?({_SCOPE_NOUNS})\b", re.IGNORECASE)
_ALWAYS = re.compile(r"\b(universal(?:ly)?|regardless of|no matter (?:what|which)|out of the box on|works everywhere)\b", re.IGNORECASE)

# "any" phrases that don't widen a result
_HARMLESS = {"any time", "any longer", "any more", "any of", "any other", "every time", "every step",
             "every day", "every paper", "every token", "every layer", "every query", "every round"}

_NEGATIONS = {"without", "no", "not", "never", "nor", "hardly", "rarely"}


def _in_source(phrase: str, source: str) -> bool:
    return phrase.lower() in " ".join(source.lower().split())


def overreach(text: str, abstract: str = "") -> list[str]:
    """
    The widening phrases in text that the abstract doesn't use, in order, e.g. ["any phone"].
    Empty when the sentence stays within what the paper states.
    """
    if not text:
        return []
    found = []
    for m in _ANY.finditer(text):
        phrase = f"{m.group(1)} {m.group(2)}".lower()
        before = text[:m.start()].split()[-1:]
        # "without any tuning" and "not every case" narrow, they don't widen
        if phrase in _HARMLESS or (before and before[0].lower().strip(",") in _NEGATIONS):
            continue
        found.append(phrase)
    found += [m.group(0).lower() for m in _ALL.finditer(text)]
    found += [m.group(0).lower() for m in _ALWAYS.finditer(text)]
    out = []
    for phrase in found:
        if not _in_source(phrase, abstract) and phrase not in out:
            out.append(phrase)
    return out


def problem(field: str, phrases: list[str]) -> str:
    """A repair instruction a model can act on."""
    quoted = ", ".join(f'"{p}"' for p in phrases)
    return (f"{field}: says {quoted}, which claims more than the paper tested. "
            "Name what it was actually tested on instead (the devices, datasets, tasks or model sizes in the abstract)")


PROMPT_RULE = (
    "Say what the paper actually tested. When the abstract names the devices, datasets, tasks, "
    "languages or model sizes it was tested on, keep every claim within them and name them where it helps "
    "(for example \"on four Android phones\", never \"on any phone\"). Do not widen a result with words "
    "such as any, every, all, always or universal unless the abstract itself says so."
)
