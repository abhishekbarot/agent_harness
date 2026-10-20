# Section 5 — Building tools safely

Tool arguments are written by the model, so treat them like input from a stranger. These exercises build the defenses every real tool needs.

| # | File | Lecture | What you write |
|---|---|---|---|
| 5.1 | `ex1_resolve_within.py` | 5.4 | Keep every path inside the workspace |
| 5.2 | `ex2_clamp_timeout.py` | 5.6 | Validate and cap a timeout the model chose |
| 5.3 | `ex3_truncate.py` | 5.5 | Cut long output, with a marker the model can see |
| 5.4 | `ex4_read_file.py` | 5.1 | A safe `read_file` tool, built from 5.1 and 5.3 |

```bash
pytest course/section05_safe_tools
```

**Key ideas**
- A JSON Schema can say a `path` is a string. It can't say the path stays inside your project. Check it yourself.
- Resolve paths before checking them. That one step catches `../`, absolute paths, and symlinks that point outside.
- Watch for `True` in Python: it counts as an `int`, so `timeout=True` would quietly mean one second.
- Everything a tool returns fills the context window and costs money on every later turn. Cap it.
