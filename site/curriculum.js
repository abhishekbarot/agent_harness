// The curriculum sheet. Edit this file to add weeks or items; the page renders
// from it. Item ids are stored in each visitor's browser to remember progress,
// so never reuse or renumber an id once it's published.
//
// type:   "read" | "exercise" | "capstone"
// level:  "easy" | "medium" | "hard"
// status: "available" | "soon"
// path:   for exercises, the folder under REPO_TREE

// "HEAD" is GitHub's name for the default branch, so links follow it even if
// the branch is renamed.
window.REPO_TREE = "https://github.com/abhishekbarot/agent_harness/tree/HEAD/course";

window.CURRICULUM = [
  {
    week: 0,
    title: "Foundations",
    summary: "The Python, git and LLM basics the rest of the course assumes.",
    items: [
      { id: "w0-python", title: "Python you'll actually use: dataclasses, typing, JSON", type: "read", level: "easy", status: "soon" },
      { id: "w0-tooling", title: "Virtual environments, pytest and git", type: "read", level: "easy", status: "soon" },
      { id: "w0-llm", title: "How LLMs work: tokens, next-token prediction, context windows", type: "read", level: "easy", status: "soon" },
    ],
  },
  {
    week: 1,
    title: "Your first API call",
    summary: "Messages, system prompts, structured output and what each call costs.",
    items: [
      { id: "w1-messages", title: "Anatomy of a request and a response", type: "read", level: "easy", status: "soon" },
      { id: "w1-thinking", title: "Thinking and effort: trading cost for quality", type: "read", level: "easy", status: "soon" },
      { id: "w1-extract", title: "Checkpoint: a CLI that pulls data out of text", type: "capstone", level: "medium", status: "soon" },
    ],
  },
  {
    week: 2,
    title: "Tool use",
    summary: "How the model asks your code to act, and how your code answers.",
    items: [
      { id: "ex-3-1", title: "3.1 Turn a tool result into an API block", type: "exercise", level: "easy", status: "available", path: "section03_tool_use" },
      { id: "ex-3-2", title: "3.2 Validate a tool schema for strict mode", type: "exercise", level: "medium", status: "available", path: "section03_tool_use" },
      { id: "ex-3-3", title: "3.3 A tool registry with a stable order", type: "exercise", level: "easy", status: "available", path: "section03_tool_use" },
      { id: "ex-3-4", title: "3.4 Send every result back in one message", type: "exercise", level: "medium", status: "available", path: "section03_tool_use" },
    ],
  },
  {
    week: 3,
    title: "The agent loop",
    summary: "Read why the model stopped, run tools, and loop until it's done.",
    items: [
      { id: "ex-4-1", title: "4.1 Pull the answer text out of a response", type: "exercise", level: "easy", status: "available", path: "section04_agent_loop" },
      { id: "ex-4-2", title: "4.2 Map every stop_reason to the next move", type: "exercise", level: "medium", status: "available", path: "section04_agent_loop" },
      { id: "ex-4-3", title: "4.3 Run tools without letting one failure stop the run", type: "exercise", level: "medium", status: "available", path: "section04_agent_loop" },
      { id: "ex-4-4", title: "4.4 The full agent loop", type: "exercise", level: "hard", status: "available", path: "section04_agent_loop" },
      { id: "cap-1", title: "Capstone 1: a minimal agent", type: "capstone", level: "hard", status: "soon" },
    ],
  },
  {
    week: 4,
    title: "Tool safety and permissions",
    summary: "Treat model output as untrusted, and gate what actually runs.",
    items: [
      { id: "ex-5-1", title: "5.1 Keep every path inside the workspace", type: "exercise", level: "medium", status: "available", path: "section05_safe_tools" },
      { id: "ex-5-2", title: "5.2 Validate and cap a model-chosen timeout", type: "exercise", level: "easy", status: "available", path: "section05_safe_tools" },
      { id: "ex-5-3", title: "5.3 Truncate long output, with a marker", type: "exercise", level: "easy", status: "available", path: "section05_safe_tools" },
      { id: "ex-5-4", title: "5.4 A safe read_file tool", type: "exercise", level: "medium", status: "available", path: "section05_safe_tools" },
      { id: "ex-6-1", title: "6.1 The permission table", type: "exercise", level: "easy", status: "available", path: "section06_permissions" },
      { id: "ex-6-2", title: "6.2 Ask a person, deny without a terminal", type: "exercise", level: "medium", status: "available", path: "section06_permissions" },
      { id: "ex-6-3", title: "6.3 The permission policy", type: "exercise", level: "hard", status: "available", path: "section06_permissions" },
      { id: "ex-6-4", title: "6.4 Check every call, then run the approved ones", type: "exercise", level: "medium", status: "available", path: "section06_permissions" },
    ],
  },
  {
    week: 5,
    title: "Context, caching and cost",
    summary: "Keep the prompt cache warm and the bill predictable.",
    items: [
      { id: "w5-caching", title: "Prompt caching is a prefix match", type: "read", level: "medium", status: "soon" },
      { id: "w5-context", title: "Context editing vs. compaction", type: "read", level: "medium", status: "soon" },
      { id: "w5-budget", title: "Exercise: cost budgets", type: "exercise", level: "medium", status: "soon" },
    ],
  },
  {
    week: 6,
    title: "Evals",
    summary: "Grade outcomes, not wording, so you can tell whether a change helped.",
    items: [
      { id: "w6-graders", title: "Exercise: write outcome graders", type: "exercise", level: "medium", status: "soon" },
      { id: "cap-2", title: "Capstone 2: an agent with an eval suite", type: "capstone", level: "hard", status: "soon" },
    ],
  },
  {
    week: 7,
    title: "Memory and RAG",
    summary: "Memory that lasts between runs, and retrieval over your own documents.",
    items: [
      { id: "w7-memory", title: "Cross-run memory with Claude's memory tool", type: "read", level: "medium", status: "soon" },
      { id: "w7-rag", title: "Embeddings, chunking and retrieval", type: "read", level: "medium", status: "soon" },
      { id: "cap-3", title: "Capstone 3: RAG over your college notes", type: "capstone", level: "hard", status: "soon" },
    ],
  },
  {
    week: 8,
    title: "Workflows, planning and multi-agent",
    summary: "When a fixed workflow beats an agent, and how agents split up work.",
    items: [
      { id: "w8-workflows", title: "Chaining, routing, parallelization, orchestrator-workers", type: "read", level: "medium", status: "soon" },
      { id: "w8-plan", title: "Exercise: a visible plan tool", type: "exercise", level: "medium", status: "soon" },
    ],
  },
  {
    week: 9,
    title: "Security",
    summary: "Prompt injection, data exfiltration, and why prompts are not a sandbox.",
    items: [
      { id: "w9-injection", title: "Prompt injection, with live examples", type: "read", level: "hard", status: "soon" },
    ],
  },
  {
    week: 10,
    title: "Interview prep and portfolio",
    summary: "Agent-engineering interview questions, and a project worth putting on your resume.",
    items: [
      { id: "w10-interview", title: "The interview sheet", type: "read", level: "medium", status: "soon" },
      { id: "cap-4", title: "Capstone 4: a portfolio agent of your choice", type: "capstone", level: "hard", status: "soon" },
    ],
  },
];
