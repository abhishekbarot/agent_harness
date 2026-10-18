# Section 6 — Permissions

The model proposes a tool call; the harness decides whether it runs. This gate is what makes an agent safe to point at a real project.

| # | File | Lecture | What you write |
|---|---|---|---|
| 6.1 | `ex1_decide.py` | 6.1–6.2 | The mode × risk table: allow, ask, or deny |
| 6.2 | `ex2_console_approver.py` | 6.4 | Ask a person, and deny when there's no terminal |
| 6.3 | `ex3_policy.py` | 6.2, 6.4, 6.5 | The policy: modes, remembered answers, per-call risk |
| 6.4 | `ex4_gated_dispatch.py` | 6.3 | Check every call, then run the approved ones |

```bash
pytest course/section06_permissions
```

**Key ideas**
- Risk belongs to the *call*, not just the tool. Reading memory is harmless; deleting it is not.
- An unknown mode is an error, never a quiet default. A typo in a config file must not turn into `auto`.
- No terminal means deny. An unattended run must never wait forever for an answer nobody will type.
- A denial is not a crash. It goes back to the model as an error result, so the model can adapt.
- Check every call before running any. A person answering prompts shouldn't see a tool run between questions.
