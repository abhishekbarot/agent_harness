# The sheet page

The free curriculum page for students: a week-by-week path with progress checkboxes and links to the graded exercises in `course/`. Plain HTML, CSS and JavaScript, with no build step and no dependencies.

| File | What it is |
|---|---|
| `index.html` | The page |
| `curriculum.js` | **The content.** Edit this to add weeks, items, or mark an item `available` |
| `app.js` | Rendering, filters, progress, theme |
| `styles.css` | Light and dark themes, phone layout |
| `social.png` | The image shown when the link is shared (1200×630) |
| `check.cjs` | Browser checks in headless Chromium |
| `social-card.cjs` | Regenerates `social.png` |

## Preview locally

```bash
python -m http.server --directory site 8000   # then open http://localhost:8000
```

## Test

```bash
npm install playwright        # once
node site/check.cjs           # 66 checks; screenshots go to site/screenshots/
node site/social-card.cjs     # after changing the headline or colors
```

The checks cover what a student does: ticking items, reloading, filtering, resetting, switching theme, using a 375 px phone, using a browser that blocks storage or JavaScript, and using only the keyboard. They also measure text contrast in both themes against WCAG AA, confirm every exercise link points at a file that exists in `course/`, and check the favicon and link-preview tags.

## Publishing an exercise

When a new exercise lands in `course/`, set its item's `status` to `"available"` and give it a `path`: the exercise file relative to `course/`, such as `section03_tool_use/ex1_tool_result.py`. Never change or reuse an item's `id`: ids are how each student's browser remembers what they've finished.

## Deploy

`.github/workflows/pages.yml` publishes this folder to GitHub Pages on every push to the repository's default branch that touches `site/`. The browser checks run first, and a failing check blocks the deploy. Pull requests and other branches that touch `site/` run the same checks without deploying, and every run keeps its screenshots as a downloadable artifact.

Only `index.html`, `styles.css`, `app.js`, `curriculum.js` and `social.png` are published. The scripts and this README stay in the repo.

The link-preview tags in `index.html` use absolute URLs for `https://abhishekbarot.github.io/agent_harness/`. If the site moves to another address, update `og:url` and `og:image` there.

**One-time setup:** in the repository's **Settings → Pages → Build and deployment**, set **Source** to **GitHub Actions**. The site then appears at `https://abhishekbarot.github.io/agent_harness/` after the next deploy. You can also run the workflow by hand from the **Actions** tab.

Exercise links use `COURSE_URL` in `curriculum.js`. It points at `HEAD`, GitHub's name for the default branch, so the links work once the course is merged and keep working if the branch is renamed.

Any other static host works too. On Vercel or Netlify, set the root directory to `site`, with no build command.
