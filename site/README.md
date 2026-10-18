# The sheet page

The free curriculum page for students: a week-by-week path with progress checkboxes and links to the graded exercises in `course/`. Plain HTML, CSS and JavaScript, with no build step and no dependencies.

| File | What it is |
|---|---|
| `index.html` | The page |
| `curriculum.js` | **The content.** Edit this to add weeks, items, or mark an item `available` |
| `app.js` | Rendering, filters, progress, theme |
| `styles.css` | Light and dark themes, phone layout |
| `check.cjs` | Browser checks in headless Chromium |

## Preview locally

```bash
python -m http.server --directory site 8000   # then open http://localhost:8000
```

## Test

```bash
npm install playwright        # once
node site/check.cjs           # 44 checks; screenshots go to site/screenshots/
```

The checks cover what a student does: ticking items, reloading, filtering, resetting, switching theme, using a 375 px phone, using a browser that blocks storage, and using only the keyboard.

## Publishing an exercise

When a new exercise lands in `course/`, set its item's `status` to `"available"` and give it a `path` (its section folder). Never change or reuse an item's `id`: ids are how each student's browser remembers what they've finished.

## Deploy

Any static host works. Point it at the `site/` folder:

- **Vercel or Netlify:** set the root directory to `site`, with no build command.
- **GitHub Pages:** publish `site/` with a GitHub Actions Pages workflow. Branch-based Pages can only serve the repo root or `docs/`.

Exercise links use `REPO_TREE` in `curriculum.js`, which points at the `main` branch. They work once the course is merged to `main`.
