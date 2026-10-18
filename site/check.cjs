#!/usr/bin/env node
// Browser checks for the sheet page, in headless Chromium.
//
//   npm install playwright      # once, if it isn't installed
//   node site/check.cjs         # screenshots land in site/screenshots/
//
// Serves site/ over HTTP (as GitHub Pages would), then walks through what a
// student does: load, tick items, reload, filter, reset, switch theme, use a
// phone, use a browser that blocks storage, and use only the keyboard.

const http = require("http");
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const ROOT = __dirname;
const SHOTS = path.join(ROOT, "screenshots");
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css" };

const failures = [];
let passed = 0;

function check(name, ok, detail = "") {
  if (ok) {
    passed += 1;
    console.log(`  ok    ${name}`);
  } else {
    failures.push(name);
    console.log(`  FAIL  ${name}${detail ? ` -- ${detail}` : ""}`);
  }
}

function serve() {
  const server = http.createServer((req, res) => {
    const urlPath = decodeURIComponent(req.url.split("?")[0]);
    const file = path.join(ROOT, urlPath === "/" ? "index.html" : urlPath);
    if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404).end("not found");
      return;
    }
    res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] || "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

async function openPage(browser, url, options = {}) {
  const context = await browser.newContext(options.context || {});
  if (options.blockStorage) {
    await context.addInitScript(() => {
      const fail = () => {
        throw new DOMException("blocked", "SecurityError");
      };
      Storage.prototype.getItem = fail;
      Storage.prototype.setItem = fail;
    });
  }
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (err) => errors.push(err.message));
  page.on("console", (msg) => msg.type() === "error" && errors.push(msg.text()));
  await page.goto(url);
  return { context, page, errors };
}

const count = (page) => page.locator("#progress-count").textContent();
const box = (page, id) => page.locator(`input[data-id="${id}"]`);

async function main() {
  fs.mkdirSync(SHOTS, { recursive: true });
  const server = await serve();
  const url = `http://127.0.0.1:${server.address().port}/`;
  const browser = await chromium.launch();

  try {
    const data = await (async () => {
      const { context, page } = await openPage(browser, url);
      const d = await page.evaluate(() => ({
        weeks: window.CURRICULUM.length,
        available: window.CURRICULUM.flatMap((w) => w.items).filter((i) => i.status === "available"),
        ids: window.CURRICULUM.flatMap((w) => w.items).map((i) => i.id),
      }));
      await context.close();
      return d;
    })();
    const total = data.available.length;

    console.log("\nFirst visit (desktop)");
    {
      const { context, page, errors } = await openPage(browser, url, {
        context: { viewport: { width: 1280, height: 900 }, colorScheme: "light" },
      });
      check("no console or page errors", errors.length === 0, errors.join("; "));
      check("curriculum ids are unique", new Set(data.ids).size === data.ids.length);
      check(`renders all ${data.weeks} weeks`, (await page.locator("details.week").count()) === data.weeks);
      check(`progress starts at 0 / ${total}`, (await count(page)) === `0 / ${total}`);
      check(
        "every checkbox has a label",
        await page.evaluate(() =>
          [...document.querySelectorAll(".item input")].every(
            (i) => document.querySelector(`label[for="${i.id}"]`)?.textContent.trim(),
          ),
        ),
      );
      const soonDisabled = await page.evaluate(() =>
        [...document.querySelectorAll(".item.is-soon input")].every((i) => i.disabled),
      );
      check("coming-soon items can't be ticked", soonDisabled);
      check(
        "weeks with exercises start open; the rest start closed",
        await page.evaluate(() =>
          [...document.querySelectorAll("details.week")].every(
            (d) => d.open === !!d.querySelector(".item:not(.is-soon)"),
          ),
        ),
      );

      const links = await page.locator(".item a.open").evaluateAll((as) => as.map((a) => a.href));
      check(`every available exercise links to GitHub (${links.length}/${total})`, links.length === total);
      check(
        "links point at the course section folders",
        links.every((h) => /github\.com\/.+\/course\/section\d\d_[a-z_]+$/.test(h)),
        links.find((h) => !/course\/section\d\d_/.test(h)),
      );
      await page.screenshot({ path: path.join(SHOTS, "desktop-light.png"), fullPage: true });

      console.log("\nTicking items off");
      await box(page, "ex-3-1").check();
      check(`progress shows 1 / ${total}`, (await count(page)) === `1 / ${total}`);
      const week2 = page.locator('details[data-week="2"] .week-meta');
      check("week 2 shows 1 / 4", (await week2.textContent()) === "1 / 4");
      check("ticked item is struck through", await page.locator(".item.is-done").count() === 1);
      for (const id of ["ex-3-2", "ex-3-3", "ex-3-4"]) await box(page, id).check();
      check("finished week shows Done", (await week2.textContent()) === "Done ✓");
      const fill = await page.locator("#progress-fill").evaluate((n) => n.style.width);
      check("progress bar fills", fill === `${Math.round((4 / total) * 100)}%`, fill);

      await page.reload();
      check("progress survives a reload", (await count(page)) === `4 / ${total}`);
      check("checkboxes survive a reload", await box(page, "ex-3-3").isChecked());

      await box(page, "ex-3-3").uncheck();
      check("unticking counts down", (await count(page)) === `3 / ${total}`);

      console.log("\nFilters");
      await page.click('.chip[data-filter="capstone"]');
      const types = await page.locator(".item").evaluateAll((n) => n.map((x) => x.dataset.type));
      check("Capstones shows only capstones", types.length > 0 && types.every((t) => t === "capstone"));
      await page.click('.chip[data-filter="available"]');
      check(`Available now shows the ${total} live items`, (await page.locator(".item").count()) === total);
      check("ticks are kept across filters", await box(page, "ex-3-1").isChecked());
      check("filtered weeks are open", await page.evaluate(() =>
        [...document.querySelectorAll("details.week")].every((d) => d.open)));
      check("the active chip is marked pressed",
        (await page.getAttribute('.chip[data-filter="available"]', "aria-pressed")) === "true");
      check("empty-state message stays hidden", await page.locator("#empty").isHidden());
      await page.click('.chip[data-filter="all"]');

      console.log("\nReset");
      page.once("dialog", (d) => d.dismiss());
      await page.click("#reset");
      check("cancelling reset keeps progress", (await count(page)) === `3 / ${total}`);
      page.once("dialog", (d) => d.accept());
      await page.click("#reset");
      check("confirming reset clears progress", (await count(page)) === `0 / ${total}`);
      await page.reload();
      check("reset sticks after a reload", (await count(page)) === `0 / ${total}`);

      console.log("\nTheme");
      await page.click("#theme-toggle");
      check("toggle switches to dark", (await page.getAttribute("html", "data-theme")) === "dark");
      const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
      check("dark background applied", bg === "rgb(22, 22, 20)", bg);
      await page.reload();
      check("theme choice survives a reload", (await page.getAttribute("html", "data-theme")) === "dark");
      await page.screenshot({ path: path.join(SHOTS, "desktop-dark.png"), fullPage: true });
      await context.close();
    }

    console.log("\nSystem dark mode");
    {
      const { context, page } = await openPage(browser, url, { context: { colorScheme: "dark" } });
      const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
      check("follows the system dark setting", bg === "rgb(22, 22, 20)", bg);
      await context.close();
    }

    console.log("\nPhone (375 px)");
    {
      const { context, page, errors } = await openPage(browser, url, {
        context: { viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 },
      });
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      check("no sideways scrolling", overflow <= 0, `${overflow}px too wide`);
      const narrow = await page.evaluate(() =>
        [...document.querySelectorAll("body *")]
          .filter((n) => n.getBoundingClientRect().right > window.innerWidth + 1)
          .map((n) => n.className || n.tagName)
          .slice(0, 5),
      );
      check("nothing pokes past the screen edge", narrow.length === 0, narrow.join(", "));
      const misaligned = await page.evaluate(() =>
        [...document.querySelectorAll(".item")]
          .filter((item) => {
            const b = item.querySelector("input").getBoundingClientRect();
            const l = item.querySelector("label").getBoundingClientRect();
            // Same row: the label starts beside the box, not below it.
            return l.left < b.right || l.top > b.bottom;
          })
          .map((item) => item.querySelector("label").textContent),
      );
      check("each checkbox sits beside its label", misaligned.length === 0, misaligned[0]);
      const order = await page.evaluate(() => {
        const s = document.querySelector('details[data-week="2"] summary');
        const top = (sel) => s.querySelector(sel).getBoundingClientRect().top;
        return top(".week-title") < top(".week-summary") && top(".week-summary") < top(".week-meta");
      });
      check("week header reads title, description, then count", order);
      const small = await page.locator(".item input:not(:disabled)").first().boundingBox();
      check("checkboxes are at least 20 px", small.width >= 20 && small.height >= 20);
      await box(page, "ex-4-1").tap();
      check("tapping ticks an item", (await count(page)) === `1 / ${total}`);
      check("no errors on mobile", errors.length === 0, errors.join("; "));
      await page.screenshot({ path: path.join(SHOTS, "phone.png"), fullPage: true });
      await context.close();
    }

    console.log("\nStorage blocked (private mode, strict settings)");
    {
      const { context, page, errors } = await openPage(browser, url, { blockStorage: true });
      check("page still renders", (await page.locator(".item").count()) === data.ids.length);
      await box(page, "ex-5-1").check();
      check("ticking still works for the visit", (await count(page)) === `1 / ${total}`);
      await page.click("#theme-toggle");
      check("theme toggle still works", (await page.getAttribute("html", "data-theme")) === "dark");
      check("no errors when storage throws", errors.length === 0, errors.join("; "));
      await context.close();
    }

    console.log("\nKeyboard only");
    {
      const { context, page } = await openPage(browser, url);
      await page.keyboard.press("Tab");
      check("first Tab reaches the skip link",
        (await page.evaluate(() => document.activeElement.className)) === "skip");
      let reached = false;
      for (let i = 0; i < 20 && !reached; i += 1) {
        await page.keyboard.press("Tab");
        reached = await page.evaluate(() => document.activeElement.matches(".item input"));
      }
      check("Tab reaches the first exercise checkbox", reached);
      await page.keyboard.press("Space");
      check("Space ticks it", (await count(page)) === `1 / ${total}`);
      await context.close();
    }
  } finally {
    await browser.close();
    server.close();
  }

  console.log(`\n${passed} passed, ${failures.length} failed`);
  console.log(`screenshots: ${path.relative(process.cwd(), SHOTS)}/`);
  process.exitCode = failures.length ? 1 : 0;
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
