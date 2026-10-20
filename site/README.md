# The site: curriculum sheet and workspace

Two pages for students, in plain HTML, CSS and JavaScript:

- **The sheet** (`index.html`): the week-by-week path, with progress checkboxes.
- **The workspace** (`workspace.html`): each student's own space. It has a dashboard (what's done, what's next, a practice streak) and an exercise view where they edit the exercise file and run its real tests in the browser, with nothing to install.

The workspace runs the course's pytest suites with [Pyodide](https://pyodide.org) (Python compiled to WebAssembly) in a background worker. A run that takes longer than 30 seconds is stopped, so an infinite loop can't freeze the page. Python downloads (about 10 MB) only when a student first presses **Run tests**.

Work is saved in the student's browser. To let students sign in and keep their work on every device, connect a Supabase project: see [`../supabase/README.md`](../supabase/README.md).

| File | What it is |
|---|---|
| `curriculum.js` | **The content.** Edit this to add weeks, items, or mark an item `available` |
| `config.js` | Supabase project URL and anon key. Empty means browser-only |
| `index.html`, `app.js`, `styles.css` | The sheet |
| `workspace.html`, `workspace.js`, `workspace.css` | The workspace: sidebar, dashboard, exercise view |
| `store.js` | Where work is saved: the browser, or the student's account |
| `runner.js`, `runner-worker.js` | Runs an exercise's tests in Pyodide, with a time limit |
| `tokens.css`, `theme.js` | Colors for both themes, and the theme switch, shared by both pages |
| `social.png` | The image shown when the link is shared (1200×630) |
| `build.py` | Assembles what gets published (see below) |
| `fetch_wheels.py` | Downloads the pytest wheels the workspace runs, checked by sha256 |
| `check.cjs`, `check-workspace.cjs`, `check-server.cjs` | Browser checks in headless Chromium |
| `social-card.cjs` | Regenerates `social.png` |

## Preview locally

The workspace needs the course files next to it, so preview a build:

```bash
python site/build.py _site
python -m http.server --directory _site 8000   # then open http://localhost:8000
```

## Test

```bash
npm install playwright pyodide@0.26.4 codemirror@5.65.16   # once
python site/build.py _site
node site/check.cjs _site             # the sheet: 67 checks
node site/check-workspace.cjs _site   # the workspace: 70 checks, about two minutes
```

Without an argument, both scripts check `site/` and `course/` directly. With Pyodide and CodeMirror installed from npm, the checks serve them locally instead of from the CDNs.

**The sheet checks** cover: ticking items, reloading, filtering, resetting, switching theme, a 375 px phone, browsers that block storage or JavaScript, and keyboard-only use. They also measure text contrast in both themes against WCAG AA.

**The workspace checks** cover:
- **Every exercise:** each of the 16 opens with its stub, brief and tests.
- **Grading:** a blank stub fails and a correct solution passes. A syntax error is reported instead of crashing, and an infinite loop is stopped at the time limit.
- **Chained exercises:** later exercises run on the student's own earlier code.
- **Saving:** drafts survive a reload, and two open tabs don't overwrite each other.
- **Reset:** it asks first, and restores the original code.
- **The rest of the page:** the dashboard and sheet agree on progress, the phone drawer works, the editor falls back when the CDN is unreachable, and the solutions are never served.
- **Accounts:** the full sign-in flow, against a fake Supabase that enforces the same row-level security as the real schema. That means moving browser work into the account, never overwriting a newer draft, reporting failed saves, and clearing the browser on sign-out.

## Publishing an exercise

When a new exercise lands in `course/`, set its item's `status` to `"available"` and give it a `path`: the exercise file relative to `course/`, such as `section03_tool_use/ex1_tool_result.py`. The workspace finds its test file and test class from that path. Never change or reuse an item's `id`: ids are how progress is remembered, in browsers and in accounts.

## Deploy

`.github/workflows/pages.yml` runs on every push that touches `site/` or `course/`:
1. **Build:** it builds `_site` with `build.py`.
2. **Check:** it runs both check suites against that build.
3. **Deploy:** on the repository's default branch, it publishes that exact build to GitHub Pages.

A failing check blocks the deploy. Pull requests and other branches run the checks without deploying. Every run keeps its screenshots as a downloadable artifact.

`build.py` publishes the pages, the course stubs and tests, and the pytest wheels. It never publishes the reference solutions, and it fails the build if any would slip in.

The link-preview tags use absolute URLs for `https://abhishekbarot.github.io/agent_harness/`. If the site moves, update `og:url` and `og:image` in both pages, and the redirect URLs in Supabase.

**One-time setup:** in the repository's **Settings → Pages → Build and deployment**, set **Source** to **GitHub Actions**. You can also run the workflow by hand from the **Actions** tab.
