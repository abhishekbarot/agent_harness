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

## The six concepts

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

Graders: `completed`, `tool_called`, `tool_not_called`, `max_tool_calls`, `no_denied`, `no_tool_errors`, `text_matches`, `file_exists`, `file_contains`, `file_unchanged`.

Two are worth calling out. `max_tool_calls` catches flailing — a run that gets the right answer after fifteen redundant reads is a regression. `file_unchanged` catches collateral damage — the agent editing something it was never asked to touch.

> Eval runs make real API calls and cost real money. Per-case and total cost is printed at the end of every run.

---

## Layout

```
src/agent_harness/
  loop.py            the agent loop, stop_reason handling, tool dispatch
  model.py           Messages API backend, request shape, system prompt
  tools/base.py      Tool protocol, risk tiers, registry
  tools/builtin.py   filesystem + shell tools, path confinement
  permissions.py     the permission gate and approvers
  config.py          frozen configuration
  usage.py           token accounting and cost
  evals.py           eval cases, graders, report
  session.py         transcript persistence
  cli.py             command line entry point
evals/cases.json     the eval suite
examples/            offline demo, no API key needed
tests/               163 tests, no network
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

Thinking is adaptive — the model decides depth per turn and interleaves reasoning between tool calls. There's no token budget to tune; depth is controlled through `--effort`.

## What this deliberately isn't

- **Not a sandbox.** The command denylist is a backstop against catastrophic typos, not a security boundary. Real isolation needs a container. Point it at a scratch directory or a VM before you turn on `--permission-mode auto`.
- **Not a framework.** No plugin system, no config DSL. Subclass `Tool`, pass it in.
- **Not the SDK's `tool_runner`.** That helper is the right default for real applications — it handles the loop for you, with per-turn hooks for approval and logging. This is the loop written out so you can see what it does.

## License

MIT
