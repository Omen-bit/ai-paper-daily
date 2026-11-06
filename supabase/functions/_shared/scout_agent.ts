// Project Scout as an agent: the steps of one search, and the loop that runs them.
// No network or Deno calls here: the LLM and the search come in as deps, so the
// whole loop can be tested with fakes (supabase/tests/scout_agent.test.ts).
//
//   plan_needs -> retrieve -> fuse -> rank -> respond
//                                       |
//        a need has no strong paper, round 1 only: expand_search -> fuse -> rank -> respond
//
// Needs the visitor checked or edited skip plan_needs and start at retrieve.
// The same steps run two ways: as a LangGraph StateGraph (scout_graph.ts), or by
// runScoutLoop below when LangGraph is switched off (SCOUT_ENGINE=loop).
import {
  type Candidate, coverageOf, type Coverage, fallbackRanking, fuseLists, type Gap, type Match,
  MAX_RESULTS, type Need, NEEDS_PROMPT, parseNeeds, parseRanking, RANK_PROMPT, rankInput, type Ranked,
  type Ranking, singleNeed,
} from "./scout.ts";

// The second round searches at most this many phrases, so a run stays inside the
// free plan's CPU time (each phrase is one embedding and one database search)
export const MAX_EXPANSIONS = 3;
// New papers from the second round sent to the ranker
export const MAX_NEW_CANDIDATES = 20;

export type ScoutDeps = {
  groq: (system: string, user: string, maxTokens: number) => Promise<string | null>;
  search: (text: string, withKeywords: boolean) => Promise<Match[]>;
  abstracts: (ids: string[]) => Promise<Map<string, string>>;
};

export type ScoutState = {
  description: string;
  summary: string;
  needs: Need[];
  edited: boolean;            // the visitor sent the needs
  planned: boolean;           // the needs came from the visitor or the planner, not the fallback
  lists: Match[][];           // every search result list so far
  queryNeeds: (string | null)[]; // the need each list was searched for (null: the whole description)
  candidates: Candidate[];    // round 1's fused candidates, or all of them after round 2
  fresh: Candidate[];         // round 2's new candidates, the only ones the second ranking reads
  ranking: Ranking | null;
  round: number;
  expanded: { need: string; query: string }[];
  mode: "ai" | "basic";
  coverage: Coverage[];
};

export function initialState(description: string, edited?: { summary: string; needs: Need[] } | null): ScoutState {
  return {
    description, summary: edited?.summary ?? "", needs: edited?.needs ?? [], edited: !!edited, planned: !!edited,
    lists: [], queryNeeds: [], candidates: [], fresh: [], ranking: null, round: 1, expanded: [], mode: "basic",
    coverage: [],
  };
}

type Step = (s: ScoutState, deps: ScoutDeps) => Promise<Partial<ScoutState>>;

/** Split the project into 2-4 needs. Without a usable reply the whole description is one need. */
export const planNeeds: Step = async (s, deps) => {
  const planned = parseNeeds(await deps.groq(NEEDS_PROMPT, s.description, 400));
  return { summary: planned?.summary ?? "", needs: planned?.needs ?? singleNeed(s.description), planned: !!planned };
};

/** One search per need, then the whole description by meaning when it was split.
 * One at a time: the free plan limits CPU per request. */
export const retrieve: Step = async (s, deps) => {
  const lists: Match[][] = [];
  const queryNeeds: (string | null)[] = [];
  for (const n of s.needs) {
    lists.push(await deps.search(n.query, true));
    queryNeeds.push(n.id);
  }
  if (s.planned) {
    lists.push(await deps.search(s.description.slice(0, 600), false));
    queryNeeds.push(null);
  }
  return { lists: [...s.lists, ...lists], queryNeeds: [...s.queryNeeds, ...queryNeeds] };
};

/** Merge every list into one candidate list. In round 2, the papers round 1 hadn't seen are kept apart. */
export const fuse: Step = async (s, deps) => {
  if (s.round === 1) {
    const candidates = fuseLists(s.lists, s.queryNeeds);
    await addAbstracts(candidates, deps);
    return { candidates };
  }
  const seen = new Set(s.candidates.map((c) => c.id));
  const all = fuseLists(s.lists, s.queryNeeds, Infinity);
  const fresh = all.filter((c) => !seen.has(c.id)).slice(0, MAX_NEW_CANDIDATES);
  await addAbstracts(fresh, deps);
  // Round 1's candidates keep their abstracts, and pick up any need round 2 found them for
  const byId = new Map(all.map((c) => [c.id, c]));
  const candidates = s.candidates.map((c) => ({ ...c, needs: byId.get(c.id)?.needs ?? c.needs }));
  return { candidates: [...candidates, ...fresh], fresh };
};

async function addAbstracts(cands: Candidate[], deps: ScoutDeps): Promise<void> {
  if (!cands.length) return;
  const abstracts = await deps.abstracts(cands.map((c) => c.id));
  cands.forEach((c) => { c.abstract = abstracts.get(c.id) ?? ""; });
}

/** Score relevance. Round 2 scores only the new papers and adds them to round 1's. */
export const rank: Step = async (s, deps) => {
  const toRank = s.round === 1 ? s.candidates : s.fresh;
  if (!toRank.length) return {};
  const ranking = parseRanking(await deps.groq(RANK_PROMPT, rankInput(s.description, s.needs, toRank), 2400), toRank, s.needs);
  if (s.round === 1) return ranking ? { ranking, mode: "ai" } : {};
  if (!ranking || !s.ranking) return {}; // a failed second ranking keeps the first
  return { ranking: mergeRankings(s.ranking, ranking) };
};

/** Round 1 and round 2 papers, best first; a need keeps its gap only while it still has no strong paper. */
export function mergeRankings(first: Ranking, second: Ranking): Ranking {
  const papers: Ranked[] = [...first.papers, ...second.papers]
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0)).slice(0, MAX_RESULTS);
  const strong = new Set(papers.filter((p) => p.fit === "strong").flatMap((p) => p.needs));
  const gaps: Gap[] = first.gaps.filter((g) => !strong.has(g.need))
    .map((g) => second.gaps.find((x) => x.need === g.need) ?? g);
  return { papers, gaps };
}

/** True when round 1 left a need without a strong paper and gave phrases not yet searched. */
export function shouldExpand(s: ScoutState): boolean {
  return s.round === 1 && s.mode === "ai" && !!s.ranking && expansionQueries(s).length > 0;
}

/** The phrases to search in round 2: the ranker's suggestions, spread across the gaps, none already searched. */
export function expansionQueries(s: ScoutState): { need: string; query: string }[] {
  const done = new Set(s.needs.map((n) => n.query.toLowerCase()));
  const out: { need: string; query: string }[] = [];
  const gaps = s.ranking?.gaps ?? [];
  for (let i = 0; out.length < MAX_EXPANSIONS && i < 3; i++) {
    for (const g of gaps) {
      const q = g.try[i];
      if (!q || done.has(q.toLowerCase()) || out.length >= MAX_EXPANSIONS) continue;
      done.add(q.toLowerCase());
      out.push({ need: g.need, query: q });
    }
  }
  return out;
}

/** Search again for the needs round 1 couldn't cover well. */
export const expandSearch: Step = async (s, deps) => {
  const expanded = expansionQueries(s);
  const lists: Match[][] = [];
  for (const e of expanded) lists.push(await deps.search(e.query, true));
  return {
    lists: [...s.lists, ...lists], queryNeeds: [...s.queryNeeds, ...expanded.map((e) => e.need)],
    expanded, round: 2,
  };
};

/** The final ranking (or the fused order, unchecked, when the ranker failed) and each need's coverage. */
export const respond: Step = async (s) => {
  const ranking = s.ranking ?? fallbackRanking(s.candidates);
  return { ranking, coverage: coverageOf(s.needs, ranking.papers, s.candidates) };
};

export const STEPS: Record<string, Step> = {
  plan_needs: planNeeds, retrieve, fuse, rank, expand_search: expandSearch, respond,
};

/** Where to start, and where to go after rank. Shared by both engines so they can't drift. */
export const startAt = (s: ScoutState) => (s.edited ? "retrieve" : "plan_needs");
export const afterRank = (s: ScoutState) => (shouldExpand(s) ? "expand_search" : "respond");

/** The same graph, run by hand. */
export async function runScoutLoop(state: ScoutState, deps: ScoutDeps): Promise<ScoutState> {
  let s = { ...state };
  const apply = async (name: string) => { s = { ...s, ...(await STEPS[name](s, deps)) }; };
  if (startAt(s) === "plan_needs") await apply("plan_needs");
  await apply("retrieve");
  await apply("fuse");
  await apply("rank");
  if (afterRank(s) === "expand_search") {
    await apply("expand_search");
    await apply("fuse");
    await apply("rank");
  }
  await apply("respond");
  return s;
}
