// Project Scout's agent loop as a LangGraph StateGraph. The steps and the routing
// live in scout_agent.ts; this file only wires them together, so the graph and
// the hand-run loop (runScoutLoop) always do the same thing.
//
// The LangGraph module is passed in rather than imported here: the edge function
// loads it from npm, and the tests load the copy Node installed.
import { afterRank, type ScoutDeps, type ScoutState, startAt, STEPS } from "./scout_agent.ts";

export const NODES = ["plan_needs", "retrieve", "fuse", "rank", "expand_search", "respond"];

// deno-lint-ignore no-explicit-any
type LangGraph = any;

/** Every field is replaced by the step that returns it. */
function stateSchema(lg: LangGraph, initial: ScoutState) {
  const fields: Record<string, unknown> = {};
  for (const key of Object.keys(initial)) {
    fields[key] = lg.Annotation({ reducer: (_old: unknown, next: unknown) => next, default: () => undefined });
  }
  return lg.Annotation.Root(fields);
}

export function buildScoutGraph(lg: LangGraph, deps: ScoutDeps, initial: ScoutState) {
  const g = new lg.StateGraph(stateSchema(lg, initial));
  for (const name of NODES) g.addNode(name, (s: ScoutState) => STEPS[name](s, deps));
  g.addConditionalEdges(lg.START, startAt, ["plan_needs", "retrieve"]);
  g.addEdge("plan_needs", "retrieve");
  g.addEdge("retrieve", "fuse");
  g.addEdge("fuse", "rank");
  g.addConditionalEdges("rank", afterRank, ["expand_search", "respond"]);
  g.addEdge("expand_search", "fuse");
  g.addEdge("respond", lg.END);
  return g.compile();
}

/** One Scout run on the graph. */
export async function runScoutGraph(lg: LangGraph, state: ScoutState, deps: ScoutDeps): Promise<ScoutState> {
  const graph = buildScoutGraph(lg, deps, state);
  return await graph.invoke(state, { recursionLimit: 20, runName: "project-scout" }) as ScoutState;
}
