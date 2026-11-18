"""
tests/test_scope.py
scope.overreach: a summary may not claim more than the paper tested.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import scope

ABSTRACT = ("We evaluate Mobile AI Factory on ten tasks and four Android phones. "
            "Its search comes within 0.03 of exhaustively training all 27 model variants. "
            "Our encoder handles every modality.")


def test_widening_words_the_abstract_lacks_are_found():
    assert scope.overreach("A tuned model on any phone without manual tuning.", ABSTRACT) == ["any phone"]
    assert scope.overreach("Works on all devices, universally.", ABSTRACT) == ["all devices", "universally"]
    assert scope.overreach("It helps regardless of hardware.", ABSTRACT) == ["regardless of"]


def test_words_the_abstract_uses_or_that_narrow_are_fine():
    assert scope.overreach("It handles every modality with one encoder.", ABSTRACT) == []
    assert scope.overreach("Tested on four Android phones and ten tasks.", ABSTRACT) == []
    assert scope.overreach("It works without any manual tuning.", ABSTRACT) == []
    assert scope.overreach("It nearly matches training all 27 model variants.", ABSTRACT) == []
    assert scope.overreach("Use it any time you fine-tune.", ABSTRACT) == []
    assert scope.overreach("", ABSTRACT) == []


def test_the_problem_tells_the_model_what_to_do():
    text = scope.problem("why_it_matters", ["any phone"])
    assert text.startswith('why_it_matters: says "any phone"') and "devices, datasets, tasks or model sizes" in text
