#!/usr/bin/env node
// Browser checks for the sheet page, in headless Chromium.
//
//   npm install playwright      # once, if it isn't installed
//   node site/check.cjs         # screenshots land in site/screenshots/
//
// Serves site/ over HTTP (as GitHub Pages would), then walks through what a
// student does: load, tick items, reload, filter, reset, switch theme, use a
// phone, use a browser that blocks storage, and use only the keyboard.

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");
const { serve, lowContrast, pngSize } = require("./check-server.cjs");

const ROOT = __dirname;
const SHOTS = path.join(ROOT, "screenshots");

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
  // `node site/check.cjs _site` checks a build from site/build.py instead.
  const built = process.argv[2] ? path.resolve(process.argv[2]) : null;
  const server = await serve(built ? { site: built, course: path.join(built, "course") } : {});
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

      const links = await page.locator(".item a.open").evaluateAll((as) => as.map((a) => a.getAttribute("href")));
      check(`every available exercise has an Open link (${links.length}/${total})`, links.length === total);
      check(
        "each link opens that exercise in the workspace",
        links.every((h, i) => h === `workspace.html#${data.available[i].id}`),
        links.find((h, i) => h !== `workspace.html#${data.available[i].id}`),
      );
      const missing = data.available
        .filter((item) => !item.path || !fs.existsSync(path.join(ROOT, "..", "course", item.path)))
        .map((item) => item.id);
      check("every exercise's file exists in course/", missing.length === 0, missing.join(", "));
      check("the hero links to the workspace", (await page.getAttribute(".cta a", "href")) === "workspace.html");

      const headings = await page.locator("h2.week-title").allTextContents();
      check("each week is a heading", headings.length === data.weeks, `${headings.length} headings`);
      const lowLight = await page.evaluate(lowContrast);
      check("light theme text meets WCAG AA contrast", lowLight.length === 0, lowLight.join("; "));
      check("theme button names the dark theme", (await page.textContent("#theme-toggle")) === "Dark theme");
      check("reset is disabled with nothing to clear", await page.locator("#reset").isDisabled());

      const meta = await page.evaluate(() => ({
        icon: document.querySelector('link[rel="icon"]')?.getAttribute("href") || "",
        image: document.querySelector('meta[property="og:image"]')?.content || "",
        title: document.querySelector('meta[property="og:title"]')?.content || "",
        desc: document.querySelector('meta[property="og:description"]')?.content || "",
        card: document.querySelector('meta[name="twitter:card"]')?.content || "",
      }));
      check("has a favicon", meta.icon.startsWith("data:image/svg+xml"));
      check("has link-preview title, description and card",
        !!(meta.title && meta.desc && meta.card === "summary_large_image"));
      const imageFile = path.join(ROOT, path.basename(new URL(meta.image || "http://x/").pathname));
      check("preview image URL is absolute and the file exists",
        /^https:\/\//.test(meta.image) && fs.existsSync(imageFile), meta.image);
      const [w, h] = fs.existsSync(imageFile) ? pngSize(imageFile) : [0, 0];
      check("preview image is 1200×630", w === 1200 && h === 630, `${w}×${h}`);
      await page.screenshot({ path: path.join(SHOTS, "desktop-light.png"), fullPage: true });

      console.log("\nTicking items off");
      await box(page, "ex-3-1").check();
      check(`progress shows 1 / ${total}`, (await count(page)) === `1 / ${total}`);
      check("reset is enabled once there is progress", await page.locator("#reset").isEnabled());
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
      let nativeDialog = false;
      page.on("dialog", (d) => {
        nativeDialog = true;
        d.dismiss();
      });
      await page.click("#reset");
      check("reset asks in the page", await page.locator("#reset-confirm").isVisible());
      check("focus moves to the safe choice",
        (await page.evaluate(() => document.activeElement.id)) === "reset-no");
      await page.click("#reset-no");
      check("Keep it keeps progress", (await count(page)) === `3 / ${total}`);
      check("the prompt closes", await page.locator("#reset-confirm").isHidden());
      await page.click("#reset");
      await page.keyboard.press("Escape");
      check("Escape cancels too", (await count(page)) === `3 / ${total}`
        && (await page.locator("#reset").isVisible()));
      await page.click("#reset");
      await page.click("#reset-yes");
      check("Clear progress clears it", (await count(page)) === `0 / ${total}`);
      check("no native pop-up is used", !nativeDialog);
      check("after clearing, reset is disabled again", await page.locator("#reset").isDisabled());
      check("focus lands on the filters, not lost",
        await page.evaluate(() => document.activeElement.matches(".chip")));
      await page.reload();
      check("reset sticks after a reload", (await count(page)) === `0 / ${total}`);

      console.log("\nTheme");
      await page.click("#theme-toggle");
      check("toggle switches to dark", (await page.getAttribute("html", "data-theme")) === "dark");
      check("button now offers the light theme", (await page.textContent("#theme-toggle")) === "Light theme");
      const lowDark = await page.evaluate(lowContrast);
      check("dark theme text meets WCAG AA contrast", lowDark.length === 0, lowDark.join("; "));
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
      check("button offers the light theme on a dark system",
        (await page.textContent("#theme-toggle")) === "Light theme");
      await context.close();
    }

    console.log("\nJavaScript turned off");
    {
      const context = await browser.newContext({ javaScriptEnabled: false });
      const page = await context.newPage();
      await page.goto(url);
      const note = page.locator(".noscript");
      check("explains that JavaScript is needed", await note.isVisible());
      check("still links to the exercises", (await note.locator("a").getAttribute("href")).includes("/course"));
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
