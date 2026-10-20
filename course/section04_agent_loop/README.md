# Section 4 — The agent loop

An agent is a model in a loop with tools. This section builds the loop: send the conversation, read why the model stopped, run tools if it asked for them, and go again until it's done.

| # | File | Lecture | What you write |
|---|---|---|---|
| 4.1 | `ex1_text_of.py` | 4.3 | Pull the answer text out of a response |
| 4.2 | `ex2_next_action.py` | 4.2–4.6 | Map every `stop_reason` to the loop's next move |
| 4.3 | `ex3_dispatch_tools.py` | 4.3 | Run the requested tools without letting one failure stop the run |
| 4.4 | `ex4_run_agent.py` | 4.7–4.8 | The full loop, built from your 4.1–4.3 |

```bash
pytest course/section04_agent_loop
```

**Key ideas**
- `stop_reason` drives everything. Learn the table in 4.2.
- A tool call cut off by `max_tokens` must **never** run. Its arguments look complete and aren't.
- The conversation history is append-only. One test checks that every request's history starts with the previous request's history.
- Bound everything: turns, and resumes after a `pause_turn`.
