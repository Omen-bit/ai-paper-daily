// LangGraph for the edge functions. Its dependencies are pinned here so every
// deploy bundles the same, tested versions instead of whatever npm has newest.
// Load it with a dynamic import, so a function that runs without LangGraph
// doesn't pay to load it.
import "npm:@langchain/core@1.3.0/runnables";
import "npm:zod@4.6.7";
import "npm:@langchain/langgraph-sdk@1.12.5";
import "npm:@langchain/langgraph-checkpoint@1.2.0";
export * from "npm:@langchain/langgraph@1.5.1/web";
