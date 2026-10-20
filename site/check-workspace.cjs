#!/usr/bin/env node
// Browser checks for the workspace, in headless Chromium.
//
//   python site/fetch_wheels.py                     # pytest wheels, once
//   npm install playwright pyodide@0.26.4 codemirror@5.65.16
//   node site/check-workspace.cjs                   # against site/ + course/
//   node site/check-workspace.cjs _site             # against a build (site/build.py)
//
// These run the course's real pytest suites in the browser through Pyodide,
// so a full run takes a minute or two. Sign-in is checked against a fake
// Supabase that keeps its data in localStorage and enforces the same
// one-student-one-set-of-rows rule as supabase/schema.sql.

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");
const { serve, routeLibraries, lowContrast } = require("./check-server.cjs");

const COURSE_SRC = path.join(__dirname, "..", "course");
const SHOTS = path.join(__dirname, "screenshots");
const built = process.argv[2] ? path.resolve(process.argv[2]) : null;

const failures = [];
let passed = 0;
function check(name, ok, detail = "") {
  if (ok) {
    passed += 1;
    console.log(`  ok    ${name}`);
  } else {
    failures.push(name);
    console.log(`  FAIL  ${name}${detail ? ` -- ${String(detail).slice(0, 300)}` : ""}`);
  }
}

const solution = (rel) => fs.readFileSync(path.join(COURSE_SRC, "solutions", rel), "utf8");
const code = (page) => page.evaluate(() => {
  const cm = document.querySelector(".CodeMirror");
  return cm ? cm.CodeMirror.getValue() : document.querySelector(".editor-plain").value;
});
const setCode = (page, text) => page.evaluate((value) => {
  const cm = document.querySelector(".CodeMirror");
  if (cm) cm.CodeMirror.setValue(value);
  else {
    const area = document.querySelector(".editor-plain");
    area.value = value;
    area.dispatchEvent(new Event("input"));
  }
}, text);
const local = (page, key) => page.evaluate((k) => JSON.parse(localStorage.getItem(k) || "null"), key);

async function openExercise(page, base, id, { reload = false } = {}) {
  await page.goto(`${base}workspace.html#${id}`);
  // Same page, new hash: the workspace keeps its state. Reload when a check
  // has changed storage behind its back.
  if (reload) await page.reload();
  await page.waitForSelector(".CodeMirror, .editor-plain", { timeout: 30000 });
}

async function runTests(page, expectPass) {
  await page.click("#run");
  await page.waitForSelector("#run-summary", { timeout: 180000 });
  const summary = await page.textContent("#run-summary");
  const pass = await page.locator("#run-summary.pass").count();
  if (expectPass !== undefined && Boolean(pass) !== expectPass) {
    const tests = await page.locator(".test").allTextContents();
    return { summary, pass: Boolean(pass), tests };
  }
  return { summary, pass: Boolean(pass) };
}

// -- a fake Supabase: auth plus three tables, with row-level security --------

const FAKE_SUPABASE = `(function () {
  const DB = "fake-supabase-db", SESSION = "fake-supabase-session", FAIL = "fake-supabase-fail";
  const KEYS = { progress: ["user_id", "item_id"], drafts: ["user_id", "item_id"], activity: ["user_id", "day"] };
  const load = () => JSON.parse(localStorage.getItem(DB) || '{"progress":[],"drafts":[],"activity":[]}');
  const save = (db) => localStorage.setItem(DB, JSON.stringify(db));
  const session = () => JSON.parse(localStorage.getItem(SESSION) || "null");
  function run(q) {
    const s = session();
    if (!s) return { data: null, error: { message: "not signed in" } };
    if (JSON.parse(localStorage.getItem(FAIL) || "[]").includes(q.table + ":" + q.op)) {
      return { data: null, error: { message: "simulated outage" } };
    }
    const db = load(), rows = db[q.table], uid = s.user.id, mine = (r) => r.user_id === uid;
    if (q.op === "select") return { data: rows.filter(mine).map((r) => ({ ...r })), error: null };
    if (q.op === "upsert") {
      for (const row of q.rows) {
        if (row.user_id !== uid) return { data: null, error: { message: "new row violates row-level security policy" } };
        const i = rows.findIndex((r) => KEYS[q.table].every((c) => r[c] === row[c]));
        if (i < 0) rows.push({ ...row });
        else if (!q.opts.ignoreDuplicates) rows[i] = { ...rows[i], ...row };
      }
      save(db);
      return { data: null, error: null };
    }
    if (q.op === "delete") {
      db[q.table] = rows.filter((r) => !(mine(r) && q.filters.every(([c, v]) => r[c] === v)));
      save(db);
      return { data: null, error: null };
    }
  }
  function from(table) {
    const q = { table, op: "select", rows: [], opts: {}, filters: [] };
    const builder = {
      select() { q.op = "select"; return builder; },
      upsert(rows, opts) { q.op = "upsert"; q.rows = [].concat(rows); q.opts = opts || {}; return builder; },
      delete() { q.op = "delete"; return builder; },
      eq(column, value) { q.filters.push([column, value]); return builder; },
      then(resolve, reject) { return Promise.resolve(run(q)).then(resolve, reject); },
    };
    return builder;
  }
  window.supabase = {
    createClient(url, key, options) {
      window.__fakeSupabase = { url, key, options };
      const listeners = [];
      return {
        auth: {
          async getSession() { return { data: { session: session() } }; },
          onAuthStateChange(cb) { listeners.push(cb); return { data: { subscription: { unsubscribe() {} } } }; },
          async signInWithOAuth({ provider, options }) {
            sessionStorage.setItem("fake-sign-in", JSON.stringify({ provider, redirectTo: options.redirectTo }));
            localStorage.setItem(SESSION, JSON.stringify({ user: { id: "user-asha", email: "asha@example.com", user_metadata: { full_name: "Asha Rao" } } }));
            // Like the real provider: a full load of redirectTo, with no #hash.
            location.assign(options.redirectTo);
            return { data: {}, error: null };
          },
          async signOut() {
            localStorage.removeItem(SESSION);
            listeners.forEach((cb) => cb("SIGNED_OUT", null));
            return { error: null };
          },
        },
        from,
      };
    },
  };
})();`;

const FAKE_CONFIG = `window.WORKSPACE_CONFIG = { supabaseUrl: "https://fake-project.supabase.co", supabaseAnonKey: "anon-test-key", providers: ["github", "google"] };`;

async function accountContext(browser) {
  const context = await browser.newContext({ viewport: { width: 1360, height: 900 } });
  await routeLibraries(context);
  await context.route("**/config.js", (route) => route.fulfill({ contentType: "text/javascript", body: FAKE_CONFIG }));
  await context.route("https://cdn.jsdelivr.net/npm/@supabase/**", (route) =>
    route.fulfill({ contentType: "text/javascript", body: FAKE_SUPABASE }));
  return context;
}

async function main() {
  fs.mkdirSync(SHOTS, { recursive: true });
  const server = await serve(built ? { site: built, course: path.join(built, "course") } : {});
  const base = `http://127.0.0.1:${server.address().port}/`;
  const browser = await chromium.launch();
  if (built) console.log(`checking the build in ${built}`);

  try {
    const context = await browser.newContext({ viewport: { width: 1360, height: 900 }, colorScheme: "light" });
    const libs = await routeLibraries(context);
    console.log(`libraries: pyodide ${libs.pyodide ? "local" : "CDN"}, codemirror ${libs.codemirror ? "local" : "CDN"}`);
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

    const data = await (async () => {
      await page.goto(`${base}workspace.html`);
      await page.waitForSelector("#view-title");
      return page.evaluate(() =>
        window.CURRICULUM.flatMap((w) => w.items).filter((i) => i.type === "exercise" && i.status === "available"));
    })();

    console.log("\nDashboard (no accounts configured)");
    check("no console or page errors", errors.length === 0, errors.join("; "));
    check("shows 0 of all exercises", (await page.textContent("#stat-done")).replace(/\s+/g, " ").trim() === `0 of ${data.length}`);
    check("sidebar lists every exercise", (await page.locator(".tree a").count()) === data.length);
    check("says work is saved in this browser", (await page.textContent("#account")).includes("saved in this browser"));
    check("next up starts at the first exercise", (await page.getAttribute("#resume", "href")) === `#${data[0].id}`);
    const lowLight = await page.evaluate(lowContrast);
    check("light theme text meets WCAG AA contrast", lowLight.length === 0, lowLight.join("; "));
    {
      // A separate page, so the expected 404 isn't logged as a page error.
      const probe = await context.newPage();
      const status = (await probe.goto(`${base}course/solutions/section03_tool_use/ex1_tool_result.py`)).status();
      check("solutions are never served", status === 404, status);
      await probe.close();
    }
    await page.screenshot({ path: path.join(SHOTS, "workspace-dashboard.png") });

    console.log("\nEvery exercise opens");
    const problems = [];
    for (const ex of data) {
      await openExercise(page, base, ex.id);
      const [editorText, stub, test, brief, crumb] = await Promise.all([
        code(page),
        page.evaluate(async (p) => (await fetch(`course/${p}`)).text(), ex.path),
        page.evaluate(async (p) => {
          const section = p.split("/")[0];
          const r = await fetch(`course/${section}/test_${section.match(/^section\d+/)[0]}.py`);
          return r.ok ? r.text() : "";
        }, ex.path),
        page.locator("#brief").textContent(),
        page.textContent("#crumb"),
      ]);
      const keyword = `class TestEx${ex.path.match(/\/ex(\d+)_/)[1]}`;
      if (editorText !== stub) problems.push(`${ex.id}: editor doesn't hold the stub`);
      if (!stub.includes("NotImplementedError")) problems.push(`${ex.id}: served file isn't a stub`);
      if (!test.includes(keyword)) problems.push(`${ex.id}: test file has no ${keyword}`);
      if (brief.trim().length < 40 || /^Exercise \d/.test(brief.trim())) problems.push(`${ex.id}: brief missing or repeats the title`);
      if (!crumb.includes(ex.title)) problems.push(`${ex.id}: breadcrumb`);
    }
    check(`all ${data.length} exercises load their stub, brief and tests`, problems.length === 0, problems.join("; "));
    check("opening exercises doesn't create drafts", Object.keys((await local(page, "agent-sheet:drafts:v1")) || {}).length === 0);

    console.log("\nRunning tests in the browser");
    await openExercise(page, base, "ex-3-1");
    const stubRun = await runTests(page, false);
    check("the untouched stub fails its tests", /^0 of 3 passed/.test(stubRun.summary), stubRun.summary);
    check("failures name what's missing",
      (await page.locator(".test pre").first().textContent()).includes("Exercise 3.1"));
    check("test names read as plain words",
      (await page.locator(".test .name").first().textContent()) === "Success block");

    await setCode(page, "def to_block(:\n");
    await runTests(page);
    const loadError = await page.locator('.test[data-outcome="error"]').first().textContent();
    check("a syntax error is reported, not a crash", loadError.includes("Loading the test file") && loadError.includes("SyntaxError"), loadError);

    await setCode(page, solution("section03_tool_use/ex1_tool_result.py"));
    const good = await runTests(page, true);
    check("a correct solution passes", good.pass, good.tests && good.tests.join(" | "));
    check("the exercise is marked done", await page.locator("#done-tag").isVisible());
    check("the sidebar shows it done", await page.locator('.tree a[data-id="ex-3-1"] .status-dot.done').count() === 1);
    check("a Next button goes to the next exercise", (await page.getAttribute("#next-exercise", "href")) === "#ex-3-2");
    check("progress is saved for the sheet", ((await local(page, "agent-sheet:progress:v1")) || []).includes("ex-3-1"));
    check("today counts toward the streak",
      ((await local(page, "agent-sheet:activity:v1")) || []).includes(await page.evaluate(() => window.WorkspaceStore.today())));
    await page.screenshot({ path: path.join(SHOTS, "workspace-exercise.png") });

    console.log("\nDrafts and reset");
    await openExercise(page, base, "ex-3-2");
    const stub32 = await code(page);
    await setCode(page, `# my note\n${stub32}`);
    await page.waitForFunction(() => /Saved/.test(document.getElementById("save-state").textContent));
    await page.reload();
    await page.waitForSelector(".CodeMirror, .editor-plain");
    check("code survives a reload", (await code(page)).startsWith("# my note"));
    check("the sidebar shows it started", await page.locator('.tree a[data-id="ex-3-2"] .status-dot.started').count() === 1);
    await page.click("#reset-code");
    check("reset asks first, focused on keeping the code",
      (await page.evaluate(() => document.activeElement.id)) === "reset-no");
    await page.click("#reset-no");
    check("Keep my code keeps it", (await code(page)).startsWith("# my note"));
    await page.click("#reset-code");
    await page.click("#reset-yes");
    check("Replace restores the original", (await code(page)) === stub32);
    check("and deletes the draft", !Object.hasOwn((await local(page, "agent-sheet:drafts:v1")) || {}, "ex-3-2"));

    console.log("\nLater exercises run on the student's earlier code");
    await page.evaluate((drafts) => {
      const saved = JSON.parse(localStorage.getItem("agent-sheet:drafts:v1") || "{}");
      localStorage.setItem("agent-sheet:drafts:v1", JSON.stringify({ ...saved, ...drafts }));
    }, {
      "ex-4-1": solution("section04_agent_loop/ex1_text_of.py"),
      "ex-4-2": solution("section04_agent_loop/ex2_next_action.py"),
      "ex-4-3": solution("section04_agent_loop/ex3_dispatch_tools.py"),
    });
    await openExercise(page, base, "ex-4-4", { reload: true });
    check("the earlier drafts are loaded", (await page.locator(".tree .status-dot.started").count()) >= 3);
    await setCode(page, solution("section04_agent_loop/ex4_run_agent.py"));
    const loopOk = await runTests(page, true);
    check("4.4 passes when 4.1–4.3 are solved", loopOk.pass, loopOk.tests && loopOk.tests.join(" | "));
    await page.evaluate(() => {
      const drafts = JSON.parse(localStorage.getItem("agent-sheet:drafts:v1"));
      delete drafts["ex-4-2"];
      localStorage.setItem("agent-sheet:drafts:v1", JSON.stringify(drafts));
    });
    await openExercise(page, base, "ex-4-4", { reload: true });
    const loopBroken = await runTests(page, false);
    const brokenText = (await page.locator(".test").allTextContents()).join(" ");
    check("4.4 fails while 4.2 is still a stub, and says so",
      !loopBroken.pass && brokenText.includes("Exercise 4.2") && !brokenText.includes("Exercise 4.1"), loopBroken.summary);

    console.log("\nA loop that never ends");
    await page.evaluate(() => { window.WORKSPACE_TIME_LIMIT_MS = 4000; });
    await openExercise(page, base, "ex-5-3");
    await setCode(page, "def truncate(text, limit):\n    while True:\n        pass\n");
    const hang = await runTests(page, false);
    check("the run is stopped at the time limit",
      (await page.locator(".test").first().textContent()).includes("didn't finish within 4 seconds"), hang.summary);
    await page.evaluate(() => { window.WORKSPACE_TIME_LIMIT_MS = 0; });
    await setCode(page, solution("section05_safe_tools/ex3_truncate.py"));
    const recovered = await runTests(page, true);
    check("the next run works on a fresh Python", recovered.pass, recovered.tests && recovered.tests.join(" | "));

    console.log("\nKeyboard");
    await openExercise(page, base, "ex-6-1");
    await page.click(".CodeMirror, .editor-plain");
    await page.keyboard.press("Escape");
    check("Esc leaves the editor for Run tests", (await page.evaluate(() => document.activeElement.id)) === "run");
    await page.click(".CodeMirror, .editor-plain");
    await page.keyboard.press("Control+Enter");
    await page.waitForSelector("#run-summary", { timeout: 180000 });
    check("Ctrl+Enter runs the tests", (await page.textContent("#run-summary")).includes("passed"));

    console.log("\nDashboard and sheet after practice");
    await page.goto(`${base}workspace.html#dashboard`);
    await page.waitForSelector("#stat-done");
    const done = ((await local(page, "agent-sheet:progress:v1")) || []).length;
    check(`dashboard counts ${done} done`, (await page.textContent("#stat-done")).trim().startsWith(String(done)));
    check("streak shows 1 day", (await page.textContent("#stat-streak")).replace(/\s+/g, " ").trim() === "1 day");
    check("resume points at the last unfinished exercise", (await page.getAttribute("#resume", "href")) === "#ex-6-1");
    await page.goto(`${base}index.html`);
    check("the sheet shows the same progress", (await page.textContent("#progress-count")).startsWith(`${done} /`));
    check("the sheet ticks finished exercises", await page.locator('input[data-id="ex-3-1"]').isChecked());

    console.log("\nDark theme");
    await openExercise(page, base, "ex-3-1");
    await page.click("#theme-toggle");
    await page.click("#run");
    await page.waitForSelector("#run-summary.pass", { timeout: 180000 });
    const lowDark = await page.evaluate(lowContrast);
    check("dark theme text meets WCAG AA contrast", lowDark.length === 0, lowDark.join("; "));
    await page.screenshot({ path: path.join(SHOTS, "workspace-dark.png") });
    check("no errors during the whole session", errors.length === 0, errors.join("; "));
    await context.close();

    console.log("\nTwo tabs open at once");
    {
      const ctx = await browser.newContext();
      await routeLibraries(ctx);
      const [a, b] = [await ctx.newPage(), await ctx.newPage()];
      await openExercise(a, base, "ex-5-1");
      await openExercise(b, base, "ex-5-2");
      await setCode(b, "# saved in tab B\n");
      await b.waitForFunction(() => /Saved/.test(document.getElementById("save-state").textContent));
      await setCode(a, "# saved in tab A\n");
      await a.waitForFunction(() => /Saved/.test(document.getElementById("save-state").textContent));
      const drafts = await local(a, "agent-sheet:drafts:v1");
      check("saving in one tab keeps the other tab's work",
        drafts["ex-5-1"] === "# saved in tab A\n" && drafts["ex-5-2"] === "# saved in tab B\n", JSON.stringify(Object.keys(drafts)));
      await ctx.close();
    }

    console.log("\nPhone (375 px)");
    {
      const ctx = await browser.newContext({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
      await routeLibraries(ctx);
      const p = await ctx.newPage();
      await p.goto(`${base}workspace.html`);
      await p.waitForSelector("#view-title");
      const overflow = () => p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      check("dashboard has no sideways scrolling", (await overflow()) <= 0, `${await overflow()}px`);
      check("the sidebar starts hidden", !(await p.locator("#sidebar").evaluate((n) => n.getBoundingClientRect().right > 0)));
      await p.tap("#open-drawer");
      await p.waitForTimeout(300);
      check("the menu button opens it", await p.locator("#sidebar").evaluate((n) => n.getBoundingClientRect().left >= 0));
      check("focus moves into the menu", (await p.evaluate(() => document.activeElement.id)) === "close-drawer");
      await p.keyboard.press("Escape");
      check("Esc closes it", (await p.getAttribute("#open-drawer", "aria-expanded")) === "false");
      await p.tap("#open-drawer");
      await p.waitForTimeout(300);
      await p.tap('.tree a[data-id="ex-3-3"]');
      await p.waitForSelector(".CodeMirror, .editor-plain");
      check("picking an exercise opens it and closes the menu",
        (await p.textContent("#view-title")) === data[2].title && (await p.getAttribute("#open-drawer", "aria-expanded")) === "false");
      check("exercise view has no sideways scrolling", (await overflow()) <= 0, `${await overflow()}px`);
      check("the closed menu casts no shadow onto the page",
        (await p.locator("#sidebar").evaluate((n) => getComputedStyle(n).boxShadow)) === "none");
      check("**bold** in a brief renders as bold, not asterisks",
        (await p.locator("#brief strong").count()) > 0 && !(await p.textContent("#brief")).includes("**"));
      await p.screenshot({ path: path.join(SHOTS, "workspace-phone.png"), fullPage: true });
      await ctx.close();
    }

    console.log("\nStorage blocked, CDN for the editor unreachable");
    {
      const ctx = await browser.newContext();
      await routeLibraries(ctx);
      await ctx.route("https://cdnjs.cloudflare.com/**", (route) => route.abort());
      await ctx.addInitScript(() => {
        const fail = () => { throw new DOMException("blocked", "SecurityError"); };
        Storage.prototype.getItem = fail;
        Storage.prototype.setItem = fail;
      });
      const p = await ctx.newPage();
      const errs = [];
      p.on("pageerror", (e) => errs.push(e.message));
      await openExercise(p, base, "ex-3-1");
      check("falls back to a plain editor", await p.locator(".editor-plain").isVisible());
      await p.locator(".editor-plain").press("Tab");
      check("Tab indents in the plain editor", (await code(p)).includes("    "));
      check("no page errors without storage", errs.length === 0, errs.join("; "));
      await ctx.close();
    }

    console.log("\nAccounts (fake Supabase)");
    {
      const ctx = await accountContext(browser);
      const p = await ctx.newPage();
      const errs = [];
      p.on("pageerror", (e) => errs.push(e.message));
      // Work done in this browser before signing in, and a newer draft that
      // already exists in the account.
      await p.goto(`${base}workspace.html`);
      await p.evaluate(() => {
        localStorage.setItem("agent-sheet:progress:v1", JSON.stringify(["ex-3-1"]));
        localStorage.setItem("agent-sheet:drafts:v1", JSON.stringify({ "ex-3-2": "# local draft\n", "ex-3-3": "# local only\n" }));
        localStorage.setItem("fake-supabase-db", JSON.stringify({
          progress: [{ user_id: "someone-else", item_id: "ex-6-4" }],
          drafts: [{ user_id: "user-asha", item_id: "ex-3-2", code: "# account draft\n" }],
          activity: [],
        }));
      });
      await p.reload();
      await p.waitForSelector("#view-title");
      check("uses the configured project", (await p.evaluate(() => window.__fakeSupabase.url)) === "https://fake-project.supabase.co");
      const providers = await p.locator("#account [data-provider]").allTextContents();
      check("offers GitHub and Google sign-in", providers.join("|") === "Continue with GitHub|Continue with Google", providers.join("|"));

      check("uses the PKCE flow, keeping #hash free for navigation",
        (await p.evaluate(() => window.__fakeSupabase.options.auth.flowType)) === "pkce");
      await openExercise(p, base, "ex-3-3");
      await p.click('[data-provider="github"]');
      await p.waitForSelector("#sign-out");
      const signIn = JSON.parse(await p.evaluate(() => sessionStorage.getItem("fake-sign-in")));
      check("sends the provider back to the bare page address", signIn.redirectTo === `${base}workspace.html`, signIn.redirectTo);
      check("reopens the exercise the student was on",
        (await p.evaluate(() => location.hash)) === "#ex-3-3" && (await p.textContent("#view-title")) === data[2].title);
      await p.goto(`${base}workspace.html#dashboard`);
      await p.waitForSelector("#stat-done");
      check("greets the student by first name", (await p.textContent("#view-title")) === "Welcome back, Asha");
      check("shows their initials", (await p.textContent(".avatar")) === "AR");
      const db = () => p.evaluate(() => JSON.parse(localStorage.getItem("fake-supabase-db")));
      let rows = await db();
      check("progress from this browser moves into the account",
        rows.progress.some((r) => r.user_id === "user-asha" && r.item_id === "ex-3-1"));
      check("drafts only in this browser move into the account",
        rows.drafts.some((r) => r.user_id === "user-asha" && r.item_id === "ex-3-3" && r.code === "# local only\n"));
      check("an older browser draft never overwrites the account's",
        rows.drafts.find((r) => r.user_id === "user-asha" && r.item_id === "ex-3-2").code === "# account draft\n");
      check("another student's progress is not visible", (await p.textContent("#stat-done")).trim().startsWith("1"));

      await openExercise(p, base, "ex-3-2");
      check("the editor shows the account's draft", (await code(p)) === "# account draft\n");
      await setCode(p, "# edited while signed in\n");
      await p.waitForFunction(() => /account/.test(document.getElementById("save-state").textContent));
      rows = await db();
      check("edits save to the account",
        rows.drafts.find((r) => r.user_id === "user-asha" && r.item_id === "ex-3-2").code === "# edited while signed in\n");

      await p.evaluate(() => localStorage.setItem("fake-supabase-fail", JSON.stringify(["drafts:upsert"])));
      await setCode(p, "# during an outage\n");
      await p.waitForSelector("#notice:not([hidden])");
      check("a failed save is reported, and the work is kept in the browser",
        (await p.textContent("#notice")).includes("Couldn't save your code")
          && (await local(p, "agent-sheet:drafts:v1"))["ex-3-2"] === "# during an outage\n");
      await p.evaluate(() => localStorage.removeItem("fake-supabase-fail"));

      await p.goto(`${base}workspace.html#dashboard`);
      await p.waitForSelector("#sign-out");
      await p.click("#sign-out");
      await p.waitForSelector('[data-provider="github"]');
      check("sign-out clears this browser's copy",
        ((await local(p, "agent-sheet:progress:v1")) || []).length === 0
          && Object.keys((await local(p, "agent-sheet:drafts:v1")) || {}).length === 0);
      check("the dashboard no longer shows their work", (await p.textContent("#stat-done")).trim().startsWith("0"));
      await p.click('[data-provider="google"]');
      await p.waitForSelector("#sign-out");
      check("signing back in brings the work back", (await p.textContent("#stat-done")).trim().startsWith("1"));
      check("no page errors with accounts", errs.length === 0, errs.join("; "));
      await ctx.close();
    }
  } finally {
    await browser.close();
    server.close();
  }

  console.log(`\n${passed} passed, ${failures.length} failed`);
  process.exitCode = failures.length ? 1 : 0;
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
