"""
scripts/run_evals.py
Fixed test sets for Project Scout and Ask this paper, run against the live
Supabase functions, so a prompt or model change can be measured before and
after instead of judged by eye.

  python scripts/run_evals.py scout            # 26 project descriptions
  python scripts/run_evals.py ask              # 30 questions about 6 papers
  python scripts/run_evals.py all --limit 5    # a quick smoke run
  python scripts/run_evals.py all --langsmith  # also log the run as a LangSmith experiment

Scout, per case: is an expected paper in the top 10 (hit@10), how high is the
first one (MRR), is it marked a strong fit, and how many of the project's needs
came back "missing".

Ask, per case: was the answer backed by a quote from the paper, and is it right.
Correctness is graded by an LLM on Groq against the reference answer. For a
question the paper can't answer, right means saying so.

Needs, from .env or the environment:
  SYNC_SECRET      skips the per-IP hourly limits (10 Scouts, 30 questions);
                   without it the script waits between calls and may still stop
  GROQ_API_KEY     grades Ask answers; without it only quote checks run
  LANGSMITH_API_KEY  only for --langsmith
Results are written to evals/results/<date>-<suite>.json.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from typing import Callable, Optional

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))

EVALS_DIR = os.path.join(ROOT, "evals")
RESULTS_DIR = os.path.join(EVALS_DIR, "results")
DEFAULT_URL = "https://nmelkepelhwyhlfdznpf.supabase.co"
ID = re.compile(r"^\d{4}\.\d{4,5}$")
TOP_K = 10
TIMEOUT = 90
# Without the secret: stay under the hourly limits (10 Scouts, 30 questions an hour)
PACE_SECONDS = {"scout": 360, "ask": 120}
DATASETS = {"scout": "ai-paper-daily-scout", "ask": "ai-paper-daily-ask"}
NOT_STATED = re.compile(r"\b(doesn'?t|does not|isn'?t|is not|not)\b.{0,40}\b(say|said|state|stated|mention|mentioned|"
                        r"report|reported|specif|cover|covered|discuss|include)", re.I)


def load_env() -> None:
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_cases(suite: str) -> list:
    with open(os.path.join(EVALS_DIR, f"{suite}_cases.json"), encoding="utf-8") as f:
        return json.load(f)["cases"]


# ---------- Scout ----------

def score_scout(case: dict, reply: dict) -> dict:
    """Scores one Scout reply against the papers that should be found."""
    plan = reply.get("plan") or []
    ids = [p.get("id") for p in plan][:TOP_K]
    expected = set(case["expected"])
    ranks = [i + 1 for i, pid in enumerate(ids) if pid in expected]
    strong = {p.get("id") for p in plan[:TOP_K] if p.get("fit") == "strong"}
    coverage = reply.get("coverage") or []
    return {
        "hit": bool(ranks),
        "rr": 1 / ranks[0] if ranks else 0.0,
        "first_rank": ranks[0] if ranks else None,
        "found": sorted(expected & set(ids)),
        "strong_hit": bool(expected & strong),
        "needs": len(coverage),
        "missing": sum(1 for c in coverage if c.get("status") == "missing"),
        "mode": reply.get("mode"),
    }


def summarize_scout(rows: list) -> dict:
    done = [r for r in rows if "error" not in r]
    n = len(done) or 1
    needs = sum(r["needs"] for r in done) or 1
    return {
        "cases": len(rows), "errors": len(rows) - len(done),
        "hit@10": round(sum(r["hit"] for r in done) / n, 3),
        "mrr": round(sum(r["rr"] for r in done) / n, 3),
        "strong_hit": round(sum(r["strong_hit"] for r in done) / n, 3),
        "missing_needs": round(sum(r["missing"] for r in done) / needs, 3),
        "ai_mode": round(sum(r["mode"] == "ai" for r in done) / n, 3),
    }


# ---------- Ask ----------

def says_not_stated(answer: str) -> bool:
    return bool(NOT_STATED.search(answer or ""))


def score_ask(case: dict, reply: dict, grade: Optional[Callable[[dict, str], Optional[bool]]] = None) -> dict:
    """Scores one Ask reply. grade(case, answer) -> True/False/None is the LLM grader."""
    answer = reply.get("answer") or ""
    declined = reply.get("answerable") is False or says_not_stated(answer)
    if not case["answerable"]:
        correct = declined  # the right reply is "the paper doesn't say"
    elif declined:
        correct = False
    else:
        correct = grade(case, answer) if grade else None
    return {
        "correct": correct,
        "quoted": bool(reply.get("quote")) and not declined,
        "declined": declined,
        "mode": reply.get("mode"),
        "answer": answer[:400],
    }


def summarize_ask(rows: list) -> dict:
    done = [r for r in rows if "error" not in r]
    graded = [r for r in done if r["correct"] is not None]
    answerable = [r for r in done if r["answerable"]]
    unanswerable = [r for r in done if not r["answerable"]]
    rate = lambda rs, key: round(sum(bool(r[key]) for r in rs) / len(rs), 3) if rs else None
    return {
        "cases": len(rows), "errors": len(rows) - len(done), "graded": len(graded),
        "correct": rate(graded, "correct"),
        "quoted": rate([r for r in answerable if not r["declined"]], "quoted"),
        "declines_when_it_should": rate(unanswerable, "declined"),
        "declines_when_it_shouldnt": rate(answerable, "declined"),
        "full_text_mode": rate([dict(r, full=r["mode"] == "full") for r in done], "full"),
    }


GRADE_PROMPT = """You grade answers to questions about a research paper.
Compare the answer with the reference. The answer is correct when it states the
same facts as the reference (numbers must match; extra correct detail is fine)
and adds nothing that contradicts it. Wording does not matter.
Reply in JSON: {"correct": true or false, "reason": "<one short sentence>"}"""


def make_grader():
    """An LLM grader on Groq, or None without a key."""
    if not (os.environ.get("GROQ_API_KEY") or "").strip():
        return None
    from pydantic import BaseModel
    from langchain_core.messages import HumanMessage, SystemMessage
    import judge

    class Grade(BaseModel):
        correct: bool
        reason: str = ""

    llm = judge.make_llm(Grade)

    def grade(case: dict, answer: str) -> Optional[bool]:
        text = f"Question: {case['question']}\nReference: {case['reference']}\nAnswer: {answer}"
        try:
            return bool(llm.invoke([SystemMessage(GRADE_PROMPT), HumanMessage(text)]).correct)
        except Exception as exc:
            print(f"  [grade] failed for {case['id']}: {exc}")
            return None
    return grade


# ---------- Running ----------

def call(base_url: str, fn: str, body: dict, secret: str, session=None) -> dict:
    import requests
    session = session or requests
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["x-sync-secret"] = secret
    r = session.post(f"{base_url}/functions/v1/{fn}", json=body, headers=headers, timeout=TIMEOUT)
    data = r.json() if r.content else {}
    if r.status_code >= 300:
        raise RuntimeError(f"{r.status_code}: {data.get('error') or r.text[:200]}")
    return data


def run_suite(suite: str, cases: list, base_url: str, secret: str, grade=None,
              session=None, sleep=time.sleep) -> list:
    rows = []
    for i, case in enumerate(cases):
        if i and not secret:
            sleep(PACE_SECONDS[suite])
        started = time.time()
        try:
            if suite == "scout":
                reply = call(base_url, "scout", {"description": case["description"]}, secret, session)
                row = {"id": case["id"], **score_scout(case, reply)}
            else:
                reply = call(base_url, "ask", {"id": case["paper"], "question": case["question"]}, secret, session)
                row = {"id": case["id"], "answerable": case["answerable"], **score_ask(case, reply, grade)}
        except Exception as exc:
            row = {"id": case["id"], "error": str(exc)}
            if suite == "ask":
                row["answerable"] = case["answerable"]
        row["seconds"] = round(time.time() - started, 1)
        print(f"  {suite} {i + 1}/{len(cases)} {case['id']}: {short(row)}")
        rows.append(row)
    return rows


def short(row: dict) -> str:
    if "error" in row:
        return f"error {row['error']}"
    if "hit" in row:
        return f"{'hit at ' + str(row['first_rank']) if row['hit'] else 'miss'}, {row['missing']}/{row['needs']} needs missing"
    return {True: "correct", False: "wrong", None: "not graded"}[row["correct"]] + (", quoted" if row["quoted"] else "")


def save(suite: str, rows: list, summary: dict, date: str) -> str:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, f"{date}-{suite}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"suite": suite, "date": date, "summary": summary, "cases": rows}, f, indent=1)
    return path


def to_langsmith(suite: str, cases: list, rows: list) -> None:
    """Logs the run as an experiment on a LangSmith dataset, so runs can be compared side by side."""
    from langsmith import Client
    client = Client()
    name = DATASETS[suite]
    if not client.has_dataset(dataset_name=name):
        ds = client.create_dataset(name, description=f"AI Papers Daily {suite} eval cases")
        client.create_examples(dataset_id=ds.id, examples=[
            {"inputs": {k: v for k, v in c.items() if k in ("id", "description", "paper", "question")},
             "outputs": {k: v for k, v in c.items() if k in ("expected", "reference", "answerable")}}
            for c in cases])
    by_id = {r["id"]: r for r in rows}
    metrics = ["hit", "rr", "strong_hit"] if suite == "scout" else ["correct", "quoted", "declined"]

    def replay(inputs: dict) -> dict:
        return by_id.get(inputs["id"], {"error": "not run"})

    def evaluator(run, example) -> list:
        out = run.outputs or {}
        return [{"key": m, "score": None if out.get(m) is None else float(out[m])} for m in metrics]

    ran = {c["id"] for c in cases}
    client.evaluate(replay, data=(e for e in client.list_examples(dataset_name=name) if e.inputs.get("id") in ran),
                    evaluators=[evaluator], experiment_prefix=f"{suite}-{dt.date.today().isoformat()}",
                    max_concurrency=1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run the Scout and Ask eval sets against the live functions.")
    ap.add_argument("suite", choices=["scout", "ask", "all"])
    ap.add_argument("--limit", type=int, default=0, help="run only the first N cases of each suite")
    ap.add_argument("--langsmith", action="store_true", help="log the run as a LangSmith experiment")
    args = ap.parse_args(argv)
    load_env()
    base_url = (os.environ.get("SUPABASE_URL") or DEFAULT_URL).strip().rstrip("/")
    secret = (os.environ.get("SYNC_SECRET") or "").strip()
    if not secret:
        print("No SYNC_SECRET: pacing calls to stay under the hourly limits (slow).")
    date = dt.date.today().isoformat()
    for suite in (["scout", "ask"] if args.suite == "all" else [args.suite]):
        cases = load_cases(suite)[: args.limit or None]
        grade = make_grader() if suite == "ask" else None
        if suite == "ask" and not grade:
            print("No GROQ_API_KEY: Ask answers won't be graded for correctness.")
        print(f"\nRunning {len(cases)} {suite} cases against {base_url}")
        rows = run_suite(suite, cases, base_url, secret, grade)
        summary = summarize_scout(rows) if suite == "scout" else summarize_ask(rows)
        print(f"\n{suite} summary:")
        for k, v in summary.items():
            print(f"  {k:28} {v}")
        print(f"  saved to {os.path.relpath(save(suite, rows, summary, date), ROOT)}")
        if args.langsmith:
            to_langsmith(suite, cases, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
