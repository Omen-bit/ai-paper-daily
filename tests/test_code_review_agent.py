"""
tests/test_code_review_agent.py
The code review agent, end to end on a throwaway git repo with a planted bug.
A fake model stands in for Groq and a fake list stands in for GitHub issues.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from langchain_core.runnables import RunnableLambda

import code_review_agent as agent
from code_review_agent import Finding, Review

GOOD = '''def average(xs):
    """The mean of xs, or 0 for an empty list."""
    if not xs:
        return 0
    return sum(xs) / len(xs)
'''
PLANTED = GOOD.replace("return sum(xs) / len(xs)", "return sum(xs) / (len(xs) - 1)")


def _git(cwd, *args, date=None):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    if date:
        env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=env)


def repo_with_planted_bug(tmp_path):
    """An old commit with a working file, then today's commit that plants a bug in it."""
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "stats.py").write_text(GOOD)
    (root / "README.md").write_text("x\n")
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "first", date="2020-01-01T00:00:00")
    (root / "src" / "stats.py").write_text(PLANTED)
    (root / "README.md").write_text("y\n")
    _git(root, "commit", "-qam", "Tweak the average")
    return str(root)


def fake_model(findings_by_file):
    calls = []

    def answer(messages):
        text = messages[-1].content
        path = text.split("\n", 1)[0].removeprefix("File: ")
        calls.append(text)
        return Review(findings=[Finding(**f) for f in findings_by_file.get(path, [])])
    return RunnableLambda(answer), calls


def deps_for(root, llm=None, issues=(), checks=(), created=None):
    def read_file(path):
        full = os.path.join(root, path)
        return open(full).read().splitlines() if os.path.isfile(full) else None

    return {
        "changed_files": lambda days: agent.changed_files(days, cwd=root),
        "diff": lambda base, path: agent.git("diff", "-U12", base, "HEAD", "--", path, cwd=root),
        "checks": lambda files: list(checks),
        "run": lambda cmd: cmd,  # checks below are (name, (code, output)) pairs
        "llm": llm,
        "read_file": read_file,
        "issues": lambda: list(issues),
        "create_issue": (lambda t, b: created.append((t, b)) or f"https://github.com/o/r/issues/{len(created)}")
        if created is not None else None,
        "repo": "o/r", "sha": "abc123",
    }


REAL = {"file": "src/stats.py", "line": 5, "code": "return sum(xs) / (len(xs) - 1)",
        "title": "Average divides by one less than the count",
        "reason": "len(xs) - 1 makes every mean too large and divides by zero for one item.",
        "fix": "Divide by len(xs).", "severity": "high"}
MADE_UP = {"file": "src/stats.py", "line": 40, "code": "cache.clear()", "title": "Cache cleared too early",
           "reason": "x", "fix": "y", "severity": "high"}


def test_collect_sees_only_recent_commits_and_numbers_new_lines(tmp_path):
    root = repo_with_planted_bug(tmp_path)
    base, files, commits = agent.changed_files(7, cwd=root)
    assert files == ["src/stats.py"] and commits == ["Tweak the average"]  # README isn't source
    assert base == agent.git("rev-parse", "HEAD~1", cwd=root).strip()
    diff = agent.numbered_diff(agent.git("diff", "-U12", base, "HEAD", "--", "src/stats.py", cwd=root))
    assert "    5 + |    return sum(xs) / (len(xs) - 1)" in diff
    assert "     - |    return sum(xs) / len(xs)" in diff


def test_a_dry_run_finds_the_planted_bug_and_drops_a_made_up_one(tmp_path):
    root = repo_with_planted_bug(tmp_path)
    llm, calls = fake_model({"src/stats.py": [REAL, MADE_UP]})
    state = agent.run_review(7, deps_for(root, llm=llm))
    assert len(calls) == 1 and "5 + |" in calls[0]
    assert [f["title"] for f in state["verified"]] == [REAL["title"]]
    assert state["filed"] == ["[agent] " + REAL["title"]]  # printed, not filed


def test_a_real_run_files_once_and_never_again(tmp_path):
    root = repo_with_planted_bug(tmp_path)
    llm, _ = fake_model({"src/stats.py": [REAL]})
    created = []
    first = agent.run_review(7, deps_for(root, llm=llm, created=created))
    assert first["filed"] == ["https://github.com/o/r/issues/1"]
    title, body = created[0]
    assert "agent-fingerprint: " in body and "https://github.com/o/r/blob/abc123/src/stats.py#L5" in body
    # Next week the same bug (even on a moved line, and with the issue closed) isn't filed again
    again = agent.run_review(7, deps_for(root, llm=llm, created=created,
                                            issues=[{"title": title, "body": body, "state": "closed"}]))
    assert again["filed"] == [] and len(created) == 1


def test_failing_checks_rank_first_and_are_capped(tmp_path):
    root = repo_with_planted_bug(tmp_path)
    pytest_out = "\n".join(f"FAILED tests/test_x.py::test_{i} - AssertionError: boom {i}" for i in range(4))
    llm, _ = fake_model({"src/stats.py": [REAL]})
    state = agent.run_review(7, deps_for(root, llm=llm, checks=[("pytest", (1, pytest_out))]))
    assert len(state["verified"]) == 5 and state["verified"][0]["severity"] == "check"
    assert len(state["filed"]) == agent.MAX_ISSUES


def test_nothing_changed_stops_early(tmp_path):
    root = repo_with_planted_bug(tmp_path)
    empty = dict(deps_for(root), changed_files=lambda days: ("", [], []))
    state = agent.run_review(7, empty)
    assert state["status"] == "nothing_to_review" and "filed" not in state


def test_without_a_model_only_checks_are_reported(tmp_path):
    root = repo_with_planted_bug(tmp_path)
    state = agent.run_review(7, deps_for(root, checks=[("ruff", (1, "src/stats.py:3:5: F821 Undefined name `y`"))]))
    assert [f["title"] for f in state["verified"]] == ["F821: Undefined name `y`"]


def test_an_unreadable_issue_list_files_nothing(tmp_path):
    root = repo_with_planted_bug(tmp_path)
    llm, _ = fake_model({"src/stats.py": [REAL]})
    d = deps_for(root, llm=llm, created=[])

    def boom():
        raise RuntimeError("403")
    d["issues"] = boom
    assert agent.run_review(7, d)["filed"] == []


def test_check_output_parsing():
    assert agent.check_findings("pytest", 0, "10 passed") == []
    got = agent.check_findings("function tests", 1, "ok 1 - a\nnot ok 2 - scout ranks papers\n")
    assert got[0]["title"] == "Function test fails: scout ranks papers"
    assert agent.check_findings("pytest", 2, "ImportError while loading conftest")[0]["title"] == "pytest failed"


def test_similar_titles_on_the_same_file_count_as_duplicates():
    f = dict(REAL, code="something else entirely")
    issue = {"title": "[agent] Average divides by one less than the count", "body": "`src/stats.py` line 9"}
    assert agent.is_duplicate(f, [issue])
    assert not agent.is_duplicate(dict(f, file="src/other.py"), [issue])


def test_the_graph_has_the_documented_steps(tmp_path):
    nodes = set(agent.build_graph(deps_for(str(tmp_path))).get_graph().nodes)
    assert {"collect", "review", "verify", "dedupe", "file"} <= nodes
