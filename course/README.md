# Build an AI Agent from Scratch — exercises

Hands-on exercises for the course. Each one is a Python file with a function to write and a set of tests that grade it.

**Everything runs offline.** The tests use a scripted fake model instead of the real Claude API, so you need no API key, there's no cost, and the results are the same on every run. The fake model can also produce situations a real model rarely shows on demand, like a refusal or a tool call cut off halfway, so you can test that your code handles them.

## Setup

You need Python 3.10 or newer.

```bash
git clone <this repo>
cd <this repo>
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install pytest
pytest course                      # every test fails at first -- that's expected
```

## How to work through an exercise

1. Open the exercise file, e.g. `course/section03_tool_use/ex1_tool_result.py`. The comment at the top explains the task.
2. Replace the `raise NotImplementedError(...)` line with your code.
3. Run that section's tests:

   ```bash
   pytest course/section03_tool_use            # the whole section
   pytest course/section03_tool_use -k Ex1     # just exercise 3.1
   ```

4. When every test for the exercise passes, move to the next one.

Exercises build on each other inside a section. For example, 4.4 (the agent loop) imports your own 4.1–4.3, so get those passing first.

## Sections

| Section | Exercises | You build |
|---|---|---|
| [3. Tool use](section03_tool_use/) | 3.1–3.4 | Tool result blocks, strict schemas, a tool registry, result batching |
| [4. The agent loop](section04_agent_loop/) | 4.1–4.4 | Reading responses, handling every `stop_reason`, running tools, the loop itself |
| [5. Building tools safely](section05_safe_tools/) | 5.1–5.4 | Path confinement, timeout limits, output truncation, a safe `read_file` |
| [6. Permissions](section06_permissions/) | 6.1–6.4 | The permission table, a console approver, the policy, gated tool dispatch |

`common/` holds the fake model and a few small shared types. You don't need to edit it, but reading `common/fakes.py` shows exactly what the tests feed your code.

## Stuck?

- Read the failing test: its name and its `assert` usually say what's expected.
- Run one test with full output: `pytest course/section04_agent_loop -k truncated -vv`.
- Each exercise names the lecture that covers it. Re-watch that lecture.

---

## For instructors

Reference solutions live in `solutions/`, mirroring the section folders. **Remove `solutions/` (or move it to a private branch) before giving this folder to students.**

The student files are generated from the solutions. Each solution marks the student's part with `# BEGIN SOLUTION` / `# END SOLUTION`. Edit the solution, never the stub, then regenerate:

```bash
python course/make_stubs.py              # rewrite the stubs
python course/make_stubs.py --check      # CI: fail if a stub is out of date
COURSE_SOLUTIONS=1 pytest course         # the same tests, run against the solutions
```

Every test should fail on a blank stub and pass on the solution. A test that passes on a blank stub gives students credit for nothing.
