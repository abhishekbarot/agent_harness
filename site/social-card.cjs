#!/usr/bin/env node
// Renders social.png, the 1200x630 image shown when the site's link is shared
// (WhatsApp, LinkedIn, Slack, X). Re-run after changing the headline or colors:
//
//   node site/social-card.cjs

const path = require("path");
const { chromium } = require("playwright");

const OUT = path.join(__dirname, "social.png");

const rows = [
  ["3.1 Tool result blocks", "easy", true],
  ["4.2 Handle every stop_reason", "medium", true],
  ["4.4 The full agent loop", "hard", false],
  ["5.1 Keep paths in the workspace", "medium", false],
];

const html = `<!doctype html><html><head><meta charset="utf-8"><style>
  :root { --bg:#f7f7f4; --surface:#fff; --text:#1c1c1a; --muted:#5f5e58; --border:#e2e0d8;
          --accent:#9c4520; --soft:#f6e6dd; --done:#2f7d4f; --easy:#256b42; --medium:#855209; --hard:#b23a3a; }
  * { box-sizing: border-box; margin: 0; }
  body { width: 1200px; height: 630px; background: var(--bg); color: var(--text);
         font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
         display: grid; grid-template-columns: 1.05fr 1fr; gap: 56px; padding: 72px 72px; }
  .brand { display: flex; align-items: center; gap: 14px; font-size: 26px; font-weight: 650; }
  .mark { width: 44px; height: 44px; border-radius: 11px; background: var(--accent); display: grid; place-items: center; }
  h1 { font-size: 58px; line-height: 1.08; letter-spacing: -0.025em; margin-top: 48px; }
  p { margin-top: 26px; font-size: 25px; line-height: 1.4; color: var(--muted); }
  .card { align-self: center; background: var(--surface); border: 1px solid var(--border); border-radius: 18px;
          padding: 10px 26px; box-shadow: 0 2px 4px rgb(0 0 0 / .04), 0 12px 32px rgb(0 0 0 / .06); }
  .row { display: flex; align-items: center; gap: 16px; padding: 20px 0; font-size: 21px; }
  .row + .row { border-top: 1px solid var(--border); }
  .box { width: 26px; height: 26px; border-radius: 6px; border: 2px solid #b9b7ad; flex: none; display: grid; place-items: center; }
  .box.on { background: var(--done); border-color: var(--done); }
  .label { flex: 1; }
  .on + .label { color: var(--muted); text-decoration: line-through; }
  .tag { font-size: 15px; font-weight: 650; padding: 4px 12px; border-radius: 999px; background: #f0efe9; }
  .easy { color: var(--easy); } .medium { color: var(--medium); } .hard { color: var(--hard); }
</style></head><body>
  <div>
    <div class="brand"><span class="mark">${tick("#fff", 26)}</span>Agent Engineering Sheet</div>
    <h1>Learn AI agent engineering by building one from scratch.</h1>
    <p>Free and week by week, for students. Every exercise is graded on your own laptop.</p>
  </div>
  <div class="card">${rows
    .map(
      ([label, level, done]) => `<div class="row"><span class="box${done ? " on" : ""}">${
        done ? tick("#fff", 18) : ""
      }</span><span class="label">${label}</span><span class="tag ${level}">${level}</span></div>`,
    )
    .join("")}</div>
</body></html>`;

function tick(color, size) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 32 32"><path d="M8 16.5l5 5L24 10.5" fill="none" stroke="${color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 } });
  await page.setContent(html);
  await page.screenshot({ path: OUT });
  await browser.close();
  console.log(`wrote ${path.relative(process.cwd(), OUT)}`);
})();
