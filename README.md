# agent_harness

An agent is a model in a loop with tools. **The harness is everything around that loop** — and that surrounding code is where almost all of the engineering actually lives.

This is a small, readable, production-leaning harness built directly on the Claude Messages API. It exists to make the moving parts explicit: not a framework to depend on, but a reference implementation you can read end to end in an afternoon.

```
┌──────────────────────────────────────────────────────────────┐
│                         the harness                          │
│                                                              │
│   prompt ──▶ ┌────────────────────────────────────────┐      │
│              │           the agent loop               │      │
│              │                                        │      │
│              │   build request ──▶ model ──▶ stop?    │      │
│              │         ▲                       │      │      │
│              │         │                       ▼      │      │
│              │   tool results  ◀── execute ◀── gate   │      │
│              └────────────────────────────────────────┘      │
│                                                              │
│   tools   permissions   context mgmt   budgets   evals       │
│   ─────   ───────────   ────────────   ───────   ─────       │
│   what     what may      what the       when to   did the    │
│   it can   actually      model still    stop      change     │
│   do       run           remembers                help       │
└──────────────────────────────────────────────────────────────┘
```

---

## Quick start

```bash
pip install -e ".[dev]"

# See the whole thing run with no API key and no network:
python examples/offline_demo.py

# Against the real API (credentials below):
agent-harness "read the README and tell me what this project does"
agent-harness --permission-mode auto --workspace ./sandbox "add a CHANGELOG"
```

Credentials resolve in the SDK's own order — `ANTHROPIC_API_KEY`, then `ANTHROPIC_AUTH_TOKEN`, then an `ant auth login` profile. If you've run `ant auth login`, you don't need to set anything.

---

## The anatomy of an agent

*AI Agents in Action* (Micheal Lanham, Manning) breaks an agent into five components around the model. Anthropic's ["Building effective agents"](https://www.anthropic.com/engineering/building-effective-agents) describes the same thing from the API side: an *augmented LLM* (a model plus retrieval, tools and memory) running in a loop, getting "ground truth" from its environment at each step. Here is where each component lives in this harness:

| Component (book) | What it is | In this harness |
|---|---|---|
| **Profile / persona** | Who the agent is: role, standards, boundaries | `profiles.py`, `--profile` (§7) |
| **Actions / tools** | What it can do to the world | `tools/`, the permission gate (§2, §3) |
| **Knowledge / memory** | What it knows, within a run and across runs | context strategies (§4), the memory tool (§9) |
| **Reasoning / evaluation** | Thinking through a step, judging the result | adaptive thinking, `--effort`, evals (§6) |
| **Planning / feedback** | Breaking a task into steps and adjusting as results come in | `update_plan` (§8), tool results fed back into the loop (§1) |

The book also describes a ladder of how much autonomy you hand over: calling the model directly, an assistant that acts for you with approval, and an autonomous agent that decides and acts on its own. Here that ladder is the `--permission-mode` setting: `deny` and `readonly` sit at the bottom, `ask` keeps a human approving every write, and `auto` is fully autonomous. Anthropic's advice matches the book's: **start at the simplest level that works.** Choose an agent only when the task is open-ended, the outcome is worth the cost, and mistakes can be caught and undone.

---

## The concepts

### 1. The loop

`loop.py` is a **manual** loop rather than the SDK's `tool_runner` helper. The helper is the right default in real applications; here the loop is the subject, and every branch in it is a decision a harness has to make somewhere.

It comes down to reading `stop_reason` correctly:

| `stop_reason` | What it means | What the harness does |
|---|---|---|
| `end_turn` | The model is done | Stop, return the text |
| `tool_use` | It wants tools run | Gate, execute, append results, loop |
| `max_tokens` | The response was cut off | **If a tool call was cut off, refuse to run it** — a truncated input still parses as a plausible object |
| `refusal` | Declined on safety grounds | Raise with the category from `stop_details` |
| `pause_turn` | A server-side tool hit its limit | Append the turn and re-send to resume (bounded) |

The two that are easy to get wrong are the last three. `max_tokens` with a `tool_use` block present is the dangerous one: the arguments look complete and are not, so executing them acts on a call the model never finished writing.

### 2. Tools

Each capability is a **dedicated, typed tool** rather than a single `bash` escape hatch.

That choice is what makes the rest of the harness possible. Bash gives the model enormous breadth, but it hands the harness an opaque string — the same shape for `grep` and for `git push`. A typed tool gives the harness an action-specific hook it can gate, audit, render, and schedule:

| Tool | Risk | Parallel-safe |
|---|---|---|
| `read_file`, `list_dir`, `search_files` | read-only | yes |
| `write_file` | write | no |
| `run_command` | dangerous | no |

`run_command` still exists — you want the breadth — but it sits at the highest risk tier where the policy guards it hardest.

**Tool input is model output, so it is untrusted.** Every path argument is resolved and confined to the workspace root before anything touches disk; a model-supplied command timeout is validated and capped, so one call can't outlive the run's own ceilings. Resolving first is what catches `../`, absolute paths, *and* symlinks pointing outside the workspace. A JSON Schema says `path` is a string; it does not say the path stays inside your project.

### 3. Permissions

`permissions.py` decides whether a proposed call actually runs.

| Mode | Read-only | Write | Shell |
|---|---|---|---|
| `auto` | run | run | run |
| `ask` | run | ask | ask |
| `readonly` | run | deny | deny |
| `deny` | deny | deny | deny |

Optional tool arguments are expressed as **required-but-nullable** (`{"type": ["string", "null"]}`) rather than left out of `required`, which is what strict tool use wants. `Tool.validate_schema` enforces that when a tool is registered, so the mistake surfaces at startup instead of as a 400 on your first live request.

Two properties matter more than the table:

- **A denial is not an error.** It becomes a normal `tool_result` marked `is_error`, so the model reads "the user declined this" and proposes something else. The run continues. (The demo shows this: the model asks to `rm -rf .`, gets refused, and adapts.)
- **No TTY means deny, not hang.** An unattended run must never block forever on a prompt nobody will answer.

### 4. Context management

Long runs fill the window with stale tool results. Two server-side strategies, selected by `--context-strategy`:

- `clear_tool_uses` *(default)* — drops old tool results outright. Predictable and cheap.
- `compact` — summarizes earlier context as the window fills. Better for very long runs.
- `none` — plain, non-beta endpoint.

**The transcript itself is strictly append-only.** Turns are added, never edited or removed. This is a correctness requirement, not a style preference: thinking blocks are bound to the history that produced them, and rewriting an earlier turn invalidates them. Trimming is the server's job, via the strategy above. There's a test that asserts every request's history is a prefix of the next one.

### 5. Budgets and observability

Open-ended loops need ceilings. `--max-turns` bounds iterations; `--max-cost` aborts once estimated spend crosses a threshold. When a run does fail, the raised error carries a `partial` result, so `--transcript-dir` still captures it — the runs most worth reading back are the ones that didn't finish. Token counts accumulate per turn and are priced from a rate table.

Watch `cache_hit_rate` in the run summary. **If it sits at zero across a multi-turn run, something in your request prefix is changing every call** — a timestamp in the system prompt, a reordered tool list, an unsorted `json.dumps`. Caching is a prefix match, so one varying byte invalidates everything after it. That's why `Config` is frozen and the tool registry preserves registration order, and why there are tests asserting the system prompt and tool schemas are byte-identical on every turn.

Logs are structured — `--log-format json` emits one object per line with the `extra` fields promoted to top level.

### 6. Evals

A harness without evals is a harness you change by vibes.

Cases live in `evals/cases.json`. Each one sets up a throwaway workspace, runs the agent, and grades the **outcome** — files on disk, tools actually called, text produced — rather than matching the model's wording.

```bash
python evals/run_eval.py                      # everything
python evals/run_eval.py --tag safety         # one slice
python evals/run_eval.py --json report.json   # machine-readable
```

Graders: `completed`, `tool_called`, `tool_not_called`, `max_tool_calls`, `no_denied`, `no_tool_errors`, `text_matches`, `file_exists`, `file_contains`, `file_unchanged`, `plan_completed`.

Two are worth calling out. `max_tool_calls` catches flailing — a run that gets the right answer after fifteen redundant reads is a regression. `file_unchanged` catches collateral damage — the agent editing something it was never asked to touch.

> Eval runs make real API calls and cost real money. Per-case and total cost is printed at the end of every run.

### 7. Profile

The profile is the agent's persona: its role, its standards, what it should and shouldn't do. It sits at the top of the system prompt. Changing the profile changes how the agent behaves without touching the loop or the tools.

```bash
agent-harness --profile reviewer --permission-mode readonly "review src/agent_harness/loop.py"
agent-harness --profile ./profiles/release-manager.md "prepare the 0.2.0 release notes"
```

The built-in profiles are `engineer` (the default), `reviewer` and `explainer`. Any other value is read as the path to a text or Markdown file. A profile describes behavior, not permissions. The `reviewer` profile tells the model not to edit files, but `--permission-mode readonly` is what actually stops it. If a boundary matters, enforce it in the harness. Don't rely on the prompt alone.

The profile is resolved once at startup. A bad profile fails before any API client is built, and the result becomes part of the cached prefix.

### 8. Planning

Adaptive thinking already lets the model plan privately, one turn at a time. What it doesn't give the harness is a plan the harness can *see*. `update_plan` provides one. The model sends the complete plan each time it changes, marking each step `pending`, `in_progress` or `completed`. The harness keeps the latest version on `RunResult.plan` and prints progress in the run summary (`plan 3/4`).

It closes the feedback loop the book describes. The `plan_completed` eval grader fails a run whose agent stopped with steps still open. That catches an agent that *says* it's done when its own plan shows it isn't.

The plan lives in tool results inside the transcript, never in the system prompt. Rewriting the system prompt on every update would invalidate the prompt cache on every request. The tool is read-only (it touches nothing outside the run), so it never needs approval. Turn it off with `--no-plan`.

### 9. Memory

Context strategies (§4) manage what the model remembers *within* a run. Memory covers what survives *between* runs.

```bash
agent-harness --memory-dir ~/.agent-memory/myproject "pick up where we left off"
```

This is Claude's own [memory tool](https://docs.claude.com/en/docs/agents-and-tools/tool-use/memory-tool) (`memory_20250818`). The request declares only its type and name, and the model already knows the commands: `view`, `create`, `str_replace`, `insert`, `delete`, `rename`. The model works with files under a virtual `/memories` directory, and `tools/memory.py` maps that onto `--memory-dir`. The same confinement rules apply as for every other tool. A memory path is model output, so `..`, paths outside `/memories` and symlinks that lead out of the store are all rejected. Individual files are capped in size, because memory is read back into the context window.

Memory is per call, not per tool, when it comes to risk. `view` is read-only and every other command is a write, so `readonly` mode lets the agent read its notes but not change them. (`Tool.risk_for` is the hook that makes this work for any tool whose calls fall into different tiers.)

Memory is off unless you set `--memory-dir`. Keep it outside the workspace if the agent shouldn't be able to reach its own notes through `write_file`, and don't let it store secrets there.

### Tool hints in the system prompt

Each tool can carry a one-line `prompt_hint`, added to the system prompt's guidelines when that tool is registered. That's how the plan and memory guidance reaches the model only when those tools are switched on. The hints are fixed strings, rendered in registry order, so the prefix stays byte-stable across turns.

---

## Layout

```
src/agent_harness/
  loop.py            the agent loop, stop_reason handling, tool dispatch
  model.py           Messages API backend, request shape, system prompt
  tools/base.py      Tool protocol, risk tiers, registry
  tools/builtin.py   filesystem + shell tools, path confinement
  tools/planning.py  update_plan: the model's plan, visible to the harness
  tools/memory.py    backend for Claude's memory tool, confined to --memory-dir
  profiles.py        built-in and file-based agent profiles
  permissions.py     the permission gate and approvers
  config.py          frozen configuration
  usage.py           token accounting and cost
  evals.py           eval cases, graders, report
  session.py         transcript persistence
  cli.py             command line entry point
evals/cases.json     the eval suite
course/              graded course exercises built from this harness (offline)
examples/            offline demo, no API key needed
tests/               210 tests, no network
```

## Development

```bash
pytest          # full suite, offline
ruff check .    # lint
mypy            # types
```

**The whole harness is testable without an API key.** The loop depends on a `ModelBackend` protocol, never on `anthropic` directly, so a scripted backend can replay any transcript — including the paths you can't reliably provoke from a live model: refusals, truncated tool calls, runaway `pause_turn`, budget overruns.

## Configuration

Every flag has an `AGENT_*` environment variable (see `.env.example`). Precedence is explicit flag → environment → default.

| Setting | Default |
|---|---|
| `--model` | `claude-opus-5` |
| `--effort` | `high` |
| `--max-turns` | `25` |
| `--permission-mode` | `ask` |
| `--context-strategy` | `clear_tool_uses` |
| `--profile` | `engineer` |
| `--memory-dir` | unset (memory off) |
| `--no-plan` | planning on |

Thinking is adaptive — the model decides depth per turn and interleaves reasoning between tool calls. There's no token budget to tune; depth is controlled through `--effort`.

## What this deliberately isn't

- **Not a sandbox.** The command denylist is a backstop against catastrophic typos, not a security boundary. Real isolation needs a container. Point it at a scratch directory or a VM before you turn on `--permission-mode auto`.
- **Not a framework.** No plugin system, no config DSL. Subclass `Tool`, pass it in.
- **Not the SDK's `tool_runner`.** That helper is the right default for real applications — it handles the loop for you, with per-turn hooks for approval and logging. This is the loop written out so you can see what it does.

## License

MIT
