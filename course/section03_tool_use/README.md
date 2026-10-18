# Section 3 — Tool use

The model can't do anything by itself. It asks *your code* to run a tool, and your code sends the result back. These exercises cover that exchange.

| # | File | Lecture | What you write |
|---|---|---|---|
| 3.1 | `ex1_tool_result.py` | 3.3 | Turn a tool's result into a `tool_result` block |
| 3.2 | `ex2_strict_schema.py` | 3.2 | Validate a tool schema for strict mode |
| 3.3 | `ex3_registry.py` | 3.6 | A registry with unique names and a fixed order |
| 3.4 | `ex4_batch_results.py` | 3.4 | Send every result back in one message, in order |

```bash
pytest course/section03_tool_use
```

**Key ideas**
- A failed tool still produces a result, marked `is_error`. The model reads the error and tries something else.
- Every `tool_use` gets exactly one `tool_result`. A missing one makes the API reject the next request.
- Results from one turn go back in one message. Splitting them teaches the model to stop making parallel calls.
