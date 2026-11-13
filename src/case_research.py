"""
case_research.py
"Research behind this": for each case study, the paper on this site closest to what the company
built, found at site-build time with no LLM call. BM25 over each paper's title (counted twice),
abstract and topics, queried with the case's title, problem, solution, tags and techniques; tag and
technique words count most. A match must clear a score threshold and share at least one technical
term (TECH_TERMS) and two distinctive words with the case, because a wrong paper is worse than none.

Words go through the same steps as the Case studies search in the browser (assets/case-finder.js):
lowercase, punctuation and stopwords out, light stemming, a small synonym map. STOP, GROUPS and
stem() here mirror that file; tests/test_case_research.py checks they stay the same.

A few well-known papers stand behind whole techniques (FOUNDATIONAL); one is offered only when no
paper matches and that paper has a page on this site. No paper pages are created for it.
"""
import math
import re

STOP = set((
    "a an and are as at be been but by can could do does for from get has have how i if in into is it its just "
    "like make my need of on or our over so some than that the their them then there these they this those to "
    "up us use used using via want was way we what when where which who why will with without you your "
    "e g eg based base build building built new one ones all any").split())

GROUPS = [
    ["chatbot", "bot", "assistant", "copilot", "chat", "conversational"],
    ["rag", "retrieval", "retrieve", "knowledge", "grounded", "grounding"],
    ["eval", "evals", "evaluation", "evaluate", "testing", "test", "benchmark", "judge"],
    ["llm", "model", "gpt", "genai"],
    ["agent", "agentic"],
    ["cost", "cheap", "cheaper", "latency", "speed", "fast", "faster", "cache", "caching", "efficient", "efficiency"],
    ["support", "helpdesk", "ticket"],
    ["handoff", "escalation", "escalate", "human"],
    ["policy", "compliance", "guideline"],
    ["access", "permission", "rbac", "role", "authorization", "entitlement"],
    ["hr", "employee", "workforce"],
    ["code", "coding", "developer", "programming"],
    ["ci", "cicd", "pipeline"],
    ["recommend", "recommendation", "recommender", "personalization", "personalisation", "personalize", "personalise"],
    ["fraud", "risk", "abuse", "scam"],
    ["document", "doc", "docs", "pdf"],
    ["search", "query", "lookup"],
    ["guardrail", "safety", "moderation", "jailbreak", "injection"],
    ["finetune", "finetuning", "lora", "tuning"],
]


def stem(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 5 and w.endswith("ing"):
        w = w[:-3]
        return w[:-1] if len(w) > 1 and w[-1] == w[-2] else w
    if len(w) > 4 and w.endswith("ed"):
        w = w[:-2]
        return w[:-1] if len(w) > 1 and w[-1] == w[-2] else w
    if len(w) > 4 and re.search(r"(s|x|ch|sh)es$", w):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


SYN = {stem(w): stem(g[0]) for g in GROUPS for w in g}


def key(word: str) -> str:
    s = stem(word)
    return SYN.get(s, s)


def tokens(text: str) -> list[str]:
    """The words of a text as search keys, stopwords left out, repeats kept (for word counts)."""
    out = []
    for w in re.split(r"[^a-z0-9]+", str(text or "").lower().replace("&", " and ")):
        if not w or w in STOP or (len(w) < 2 and not w.isdigit()):
            continue
        out.append(key(w))
    return out


# A case and a paper must share at least one of these, and it must be in the case's own title, tags
# or techniques: named techniques, not general words ("agent", "tool", "plan", "search" are too broad)
TECH_TERMS = {key(w) for w in (
    "rag rerank reranking reranker embedding embeddings chunking bm25 colbert "
    "multiagent hallucination guardrail jailbreak injection red-teaming "
    "finetune lora rlhf dpo grpo reward distillation quantization quantize gptq awq "
    "speculative decoding decode kv prefill disaggregation disaggregated batching moe "
    "diffusion multimodal asr tts ocr segmentation "
    "recommendation two-tower tower ctr collaborative sequential gnn "
    "forecasting anomaly bandit uplift causal text-to-sql sql synthetic contrastive "
    "summarization translation"
).replace("-", " ").split()} - {"", "llm", "text", "to", "two", "tower"} | {"tower"}

# Words that pass the rarity test among papers but say nothing about what was built
GENERIC = {key(w) for w in (
    "call calling tool tools high low multi help helps run running need needs make makes key two three four "
    "real time global local large small best better richer complex simple new step steps action actions platform "
    "network design designing continuous continuously resource resources response responses automate automated "
    "user users team teams company product products customer customers billion million thousand percent "
    "meet report reports handle handles many request requests store let score scoring create creates build "
    "check engineer engineers lesson lessons start find layer layers value values keep pre re add web "
    "expert experts optimize optimized gpu gpus nvidia engine bring brings separate history content "
    "because read reads stay update updates mix stage stages several introduce introducing struggle type types"
).split()}

# Technique -> a well-known paper behind it (arXiv id), offered only when nothing else matches
# and only when that paper has a page on this site
FOUNDATIONAL = {
    "rag": "2005.11401",           # Lewis et al., Retrieval-Augmented Generation
    "fine-tuning": "2106.09685",   # LoRA
    "distillation": "1503.02531",  # Hinton et al., Distilling the Knowledge in a Neural Network
    "agents": "2210.03629",        # ReAct
    "prompt-engineering": "2201.11903",  # Chain-of-thought prompting
    "quantization": "2210.17323",  # GPTQ
    "evaluation-harness": "2306.05685",  # Judging LLM-as-a-judge
}

MIN_SCORE = 30.0     # BM25 score a match must reach (tuned on the site's papers and cases)
MIN_SHARED = 3       # distinctive words a case and its paper must share, one of them a TECH_TERM
MIN_IDF = 2.3        # only words in at most about a tenth of the papers count as distinctive
MIN_WEIGHT = 12.0    # the shared distinctive words' rarity (summed idf) a match needs
TITLE_WEIGHT = 2     # a paper's title words count this many times
K1, B = 1.2, 0.75


class PaperIndex:
    """BM25 over the papers that have a page on the site."""

    def __init__(self, papers: dict):
        self.papers = papers
        self.docs: dict[str, dict[str, int]] = {}
        self.lengths: dict[str, int] = {}
        df: dict[str, int] = {}
        for pid, rec in papers.items():
            words = tokens(rec.get("title", "")) * TITLE_WEIGHT + tokens(rec.get("abstract", "")[:2000])
            words += tokens(" ".join(c.replace("-", " ") for c in rec.get("categories") or []))
            counts: dict[str, int] = {}
            for w in words:
                counts[w] = counts.get(w, 0) + 1
            self.docs[pid] = counts
            self.lengths[pid] = len(words)
            for w in counts:
                df[w] = df.get(w, 0) + 1
        n = max(1, len(papers))
        self.avg = (sum(self.lengths.values()) / n) if papers else 1.0
        self.idf = {w: math.log(1 + (n - d + 0.5) / (d + 0.5)) for w, d in df.items()}
        self.postings: dict[str, list[str]] = {}
        for pid, counts in self.docs.items():
            for w in counts:
                self.postings.setdefault(w, []).append(pid)

    def score(self, query: dict[str, float]) -> list[tuple[str, float, list[str]]]:
        """(paper id, score, shared distinctive words), best first, for a weighted query."""
        scores: dict[str, float] = {}
        shared: dict[str, list[str]] = {}
        for w, qw in query.items():
            idf = self.idf.get(w)
            if not idf:
                continue
            for pid in self.postings.get(w, []):
                tf = self.docs[pid][w]
                norm = tf * (K1 + 1) / (tf + K1 * (1 - B + B * self.lengths[pid] / self.avg))
                scores[pid] = scores.get(pid, 0.0) + qw * idf * norm
                if idf >= MIN_IDF:
                    shared.setdefault(pid, []).append(w)
        return sorted(((pid, sc, shared.get(pid, [])) for pid, sc in scores.items()), key=lambda r: (-r[1], r[0]))


def case_query(post: dict, labels: dict[str, str] | None = None) -> dict[str, float]:
    """A case's words with their weight: tags and techniques 2.5, title 1.5, problem and solution 1."""
    labels = labels or {}
    query: dict[str, float] = {}
    tech = " ".join([t for t in post.get("tags") or [] if isinstance(t, str)]
                    + [labels.get(t, t).replace("-", " ") for t in post.get("techniques") or [] if isinstance(t, str)])
    for text, weight in ((tech, 2.5), (post.get("title", ""), 1.5), (post.get("issue", ""), 1.0),
                         (post.get("summary", ""), 1.0), (post.get("result", ""), 0.5)):
        for w in set(tokens(text)):
            query[w] = max(query.get(w, 0.0), weight)
    return query


def core_terms(post: dict, labels: dict[str, str] | None = None) -> set[str]:
    """The words that say what a case is about: its title, tags and techniques."""
    labels = labels or {}
    return set(tokens(" ".join([post.get("title", "")] + [t for t in post.get("tags") or [] if isinstance(t, str)]
                               + [labels.get(t, t).replace("-", " ") for t in post.get("techniques") or []
                                  if isinstance(t, str)])))


def match(post: dict, index: PaperIndex, k: int = 2, labels: dict[str, str] | None = None,
          min_score: float = MIN_SCORE) -> list[dict]:
    """Up to k papers behind a case: {id, title, url, score, shared}, best first; [] when none is good."""
    out = []
    core = core_terms(post, labels) & TECH_TERMS
    if not core:
        return out
    for pid, sc, shared in index.score(case_query(post, labels)):
        if sc < min_score or len(out) >= k:
            break
        distinct = {w for w in set(shared) - GENERIC if len(w) > 2 and not w.isdigit()}
        title_words = set(tokens(index.papers[pid].get("title", "")))
        if (len(distinct) < MIN_SHARED or not (distinct & core & title_words)
                or sum(index.idf[w] for w in distinct) < MIN_WEIGHT):
            continue
        out.append({"id": pid, "title": index.papers[pid].get("title", ""), "url": f"../paper/{pid}.html",
                    "score": round(sc, 2), "shared": sorted(distinct)[:6]})
    if not out:
        for t in post.get("techniques") or []:
            pid = FOUNDATIONAL.get(t)
            if pid and pid in index.papers:
                out.append({"id": pid, "title": index.papers[pid].get("title", ""), "url": f"../paper/{pid}.html",
                            "score": 0.0, "shared": [], "foundational": True})
                break
    return out


def related(posts: list[dict], papers: dict, k: int = 2, labels: dict[str, str] | None = None) -> dict[str, list[dict]]:
    """Every case's matches, by case url."""
    if not papers:
        return {}
    index = PaperIndex(papers)
    return {p["url"]: match(p, index, k, labels) for p in posts}
