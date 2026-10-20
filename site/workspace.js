// The workspace: a dashboard of the student's progress, and an exercise view
// where they edit the exercise file and run its real pytest suite in the
// browser. Navigation is by URL hash: #dashboard, or #ex-3-1 for an exercise.

(function () {
  "use strict";

  const COURSE_URL = window.COURSE_URL || "";
  const CODEMIRROR = "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/";
  const SAVE_DELAY_MS = 600;

  // -- course data -----------------------------------------------------------

  const weeks = (window.CURRICULUM || [])
    .map((week) => ({
      ...week,
      exercises: week.items.filter((i) => i.type === "exercise" && i.status === "available" && i.path),
    }))
    .filter((week) => week.exercises.length);
  const exercises = weeks.flatMap((week) => week.exercises.map((item) => ({ ...item, week })));
  const byId = new Map(exercises.map((ex) => [ex.id, ex]));

  const sectionOf = (ex) => ex.path.split("/")[0];
  // "section03_tool_use" -> "section03_tool_use/test_section03.py"
  const testPathOf = (ex) => `${sectionOf(ex)}/test_${sectionOf(ex).match(/^section\d+/)[0]}.py`;
  // "ex2_strict_schema.py" -> "TestEx2", the test class for that exercise.
  const keywordOf = (ex) => `TestEx${ex.path.match(/\/ex(\d+)_/)[1]}`;
  const siblingsOf = (ex) => exercises.filter((other) => sectionOf(other) === sectionOf(ex));

  // -- small DOM helpers -----------------------------------------------------

  const $ = (id) => document.getElementById(id);
  const el = (tag, attrs, ...children) => {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === false || value === null || value === undefined) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children.flat()) if (child !== null && child !== undefined && child !== false) node.append(child);
    return node;
  };

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      script.onload = resolve;
      script.onerror = () => reject(new Error(`could not load ${src}`));
      document.head.append(script);
    });
  }

  // CodeMirror gives syntax highlighting and Python indentation. If the CDN is
  // unreachable the editor falls back to a plain text area that still works.
  let editorLib = null;
  function loadEditorLib() {
    if (!editorLib) {
      editorLib = (async () => {
        await loadScript(`${CODEMIRROR}codemirror.min.js`);
        await loadScript(`${CODEMIRROR}mode/python/python.min.js`);
        return window.CodeMirror;
      })().catch(() => null);
    }
    return editorLib;
  }

  // -- the exercise brief, from the exercise file's docstring -----------------

  function docstringOf(source) {
    const match = source.match(/^\s*(?:#[^\n]*\n|\s)*(?:"""|''')([\s\S]*?)(?:"""|''')/);
    if (!match) return "";
    // The first line repeats the exercise title, which the page already shows.
    return match[1].replace(/\\\\/g, "\\").trim().replace(/^Exercise [\d.]+ -- [^\n]*\n+/, "");
  }

  // "TestEx1ToolResult > test_error_block_sets_is_error[abc]" ->
  // "Error block sets is error [abc]": what the test checks, in plain words.
  function testLabel(name) {
    const last = name.split(" > ").pop();
    const match = last.match(/^test_(\w+?)(\[.*\])?$/);
    if (!match) return name;
    const words = match[1].replace(/_/g, " ");
    return `${words[0].toUpperCase()}${words.slice(1)}${match[2] ? ` ${match[2]}` : ""}`;
  }

  // Inline ``code`` -> <code> and **bold** -> <strong>; everything else as text.
  function inline(text) {
    const out = [];
    text.split(/``(.+?)``/g).forEach((part, i) => {
      if (i % 2) out.push(el("code", { text: part }));
      else part.split(/\*\*(.+?)\*\*/g).forEach((bit, j) => out.push(j % 2 ? el("strong", { text: bit }) : bit));
    });
    return out;
  }

  // A small renderer for the docstrings' plain-text conventions: paragraphs,
  // "* " bullets, "1. " steps, and ==== tables (shown as preformatted text).
  function renderBrief(doc) {
    const blocks = doc.split(/\n\s*\n/);
    const nodes = [];
    for (const block of blocks) {
      const lines = block.split("\n");
      const trimmed = lines.map((l) => l.trim());
      if (trimmed.some((l) => /^=+(\s+=+)+$/.test(l))) {
        nodes.push(el("pre", { text: lines.join("\n").replace(/^\n+|\s+$/g, "") }));
      } else if (/^[*-] /.test(trimmed[0])) {
        nodes.push(el("ul", {}, groupItems(trimmed, /^[*-] /).map((t) => el("li", {}, inline(t)))));
      } else if (/^\d+\. /.test(trimmed[0])) {
        nodes.push(el("ol", {}, groupItems(trimmed, /^\d+\. /).map((t) => el("li", {}, inline(t)))));
      } else {
        nodes.push(el("p", {}, inline(trimmed.join(" "))));
      }
    }
    return nodes;
  }

  // Join wrapped continuation lines onto the item they belong to.
  function groupItems(lines, marker) {
    const items = [];
    for (const line of lines) {
      if (marker.test(line)) items.push(line.replace(marker, ""));
      else if (items.length) items[items.length - 1] += ` ${line}`;
    }
    return items;
  }

  // -- state ---------------------------------------------------------------

  let store = null;
  let runner = null;
  let current = null; // { ex, editor, running, saveTimer }

  const notice = (text) => {
    $("notice").textContent = text || "";
    $("notice").hidden = !text;
  };

  // -- sidebar -------------------------------------------------------------

  function statusOf(ex) {
    if (store.isDone(ex.id)) return "done";
    if (store.draft(ex.id) !== null) return "started";
    return "todo";
  }
  const STATUS_TEXT = { done: "Done", started: "Started", todo: "Not started" };

  function renderTree(activeId) {
    $("tree").replaceChildren(
      ...weeks.map((week) =>
        el(
          "section",
          { class: "tree-week", "aria-labelledby": `tree-week-${week.week}` },
          el("h2", { id: `tree-week-${week.week}`, text: `Week ${week.week} · ${week.title}` }),
          el(
            "ul",
            {},
            week.exercises.map((ex) => {
              const status = statusOf(ex);
              return el(
                "li",
                {},
                el(
                  "a",
                  { href: `#${ex.id}`, "aria-current": ex.id === activeId ? "page" : null, "data-id": ex.id },
                  el("span", { class: `status-dot ${status}`, "aria-hidden": "true" }),
                  el("span", { class: "label", title: ex.title, text: ex.title }),
                  el("span", { class: "sr-only", text: `, ${STATUS_TEXT[status]}` }),
                ),
              );
            }),
          ),
        ),
      ),
    );
    if (activeId) $("nav-dashboard").removeAttribute("aria-current");
    else $("nav-dashboard").setAttribute("aria-current", "page");
  }

  function renderAccount() {
    const box = $("account");
    if (!store.accountsEnabled) {
      box.replaceChildren(el("p", { text: "Your work is saved in this browser." }));
      return;
    }
    if (!store.user) {
      const names = { github: "GitHub", google: "Google" };
      box.replaceChildren(
        el("p", { text: "Sign in to keep your work on every device." }),
        ...(window.WORKSPACE_CONFIG.providers || ["github"]).map((provider) =>
          el("button", {
            type: "button",
            class: "ghost provider",
            "data-provider": provider,
            text: `Continue with ${names[provider] || provider}`,
            onclick: () => store.signIn(provider),
          }),
        ),
      );
      return;
    }
    const initials = store.user.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
    box.replaceChildren(
      el(
        "div",
        { class: "who" },
        store.user.avatarUrl
          ? el("img", { class: "avatar", src: store.user.avatarUrl, alt: "" })
          : el("span", { class: "avatar", "aria-hidden": "true", text: initials }),
        el("span", { class: "name", text: store.user.name }),
      ),
      el("button", { type: "button", class: "ghost", id: "sign-out", text: "Sign out", onclick: () => store.signOut() }),
    );
  }

  // -- dashboard -------------------------------------------------------------

  function nextExercise(after) {
    const start = after ? exercises.findIndex((ex) => ex.id === after) + 1 : 0;
    return exercises.slice(start).find((ex) => !store.isDone(ex.id)) || exercises.find((ex) => !store.isDone(ex.id)) || null;
  }

  function resumeTarget() {
    const last = byId.get(store.lastExercise());
    if (last && !store.isDone(last.id)) return { ex: last, verb: "Resume" };
    const next = nextExercise(last && last.id);
    return next ? { ex: next, verb: store.doneIds().size ? "Continue" : "Start" } : null;
  }

  function renderDashboard() {
    const done = exercises.filter((ex) => store.isDone(ex.id)).length;
    const pct = exercises.length ? Math.round((done / exercises.length) * 100) : 0;
    const streak = store.streak();
    const target = resumeTarget();
    const first = store.user ? store.user.name.split(/\s+/)[0] : "";

    setCrumb("Dashboard");
    document.title = "Dashboard · Agent Engineering Workspace";
    $("view").replaceChildren(
      el(
        "div",
        { class: "dash" },
        el(
          "div",
          {},
          el("h1", { id: "view-title", tabindex: "-1", text: first ? `Welcome back, ${first}` : "Your workspace" }),
          el("p", {
            class: "lede",
            text: store.accountsEnabled && !store.user
              ? "Your work is saved in this browser. Sign in to keep it on every device."
              : "Write each exercise here and run its real tests in your browser. Nothing to install.",
          }),
        ),
        el(
          "div",
          { class: "stats" },
          el(
            "div",
            { class: "card" },
            el("div", { class: "stat-label", text: "Completed" }),
            el("div", { class: "stat-value", id: "stat-done" }, `${done} `, el("small", { text: `of ${exercises.length}` })),
            el("div", { class: "bar", role: "progressbar", "aria-label": "Exercises completed", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(pct) }, el("span", { style: `width:${pct}%` })),
          ),
          el(
            "div",
            { class: "card" },
            el("div", { class: "stat-label", text: "Streak" }),
            el("div", { class: "stat-value", id: "stat-streak" }, `${streak} `, el("small", { text: streak === 1 ? "day" : "days" })),
            el("p", { class: "hint", text: streak ? "Run tests on any exercise today to keep it going." : "Run tests on any exercise to start a streak." }),
          ),
        ),
        target
          ? el(
              "div",
              { class: "card next" },
              el(
                "div",
                {},
                el("div", { class: "stat-label", text: "Next up" }),
                el("h2", { text: target.ex.title }),
                el("p", { class: "hint", text: `Week ${target.ex.week.week} · ${target.ex.week.title}` }),
              ),
              el("a", { class: "button", id: "resume", href: `#${target.ex.id}`, text: target.verb }),
            )
          : el("div", { class: "card" }, el("h2", { text: "Every available exercise is done." }), el("p", { class: "hint", text: "New weeks are on the way. Check the curriculum sheet for what's next." })),
        el(
          "section",
          { class: "weeks", "aria-labelledby": "weeks-title" },
          el("h2", { id: "weeks-title", text: "By week" }),
          weeks.map((week) => {
            const finished = week.exercises.filter((ex) => store.isDone(ex.id)).length;
            const go = week.exercises.find((ex) => !store.isDone(ex.id)) || week.exercises[0];
            const p = Math.round((finished / week.exercises.length) * 100);
            return el(
              "div",
              { class: "card week-row" },
              el("a", { href: `#${go.id}`, text: `Week ${week.week} · ${week.title}` }),
              el("span", { class: "count", text: `${finished} / ${week.exercises.length}` }),
              el("div", { class: "bar", "aria-hidden": "true" }, el("span", { style: `width:${p}%` })),
            );
          }),
        ),
      ),
    );
    renderTree(null);
  }

  // -- exercise view ---------------------------------------------------------

  function setCrumb(text) {
    $("crumb").textContent = text;
  }

  async function renderExercise(ex) {
    store.setLastExercise(ex.id);
    setCrumb(`Week ${ex.week.week} · ${ex.week.title}  ›  ${ex.title}`);
    document.title = `${ex.title} · Agent Engineering Workspace`;
    renderTree(ex.id);

    const results = el(
      "aside",
      { class: "results", "aria-labelledby": "results-title" },
      el("h2", { id: "results-title", text: "Tests" }),
      el("div", { id: "results-body", "aria-live": "polite" }, el("p", { class: "empty-state", text: "Run the tests to check your code. The first run downloads Python, so it takes a few seconds." })),
    );
    const runButton = el("button", { type: "button", class: "button", id: "run", onclick: () => runTests() }, "Run tests", el("kbd", { "aria-hidden": "true", text: "Ctrl ↵" }));
    const resetButton = el("button", { type: "button", class: "ghost", id: "reset-code", text: "Reset code", onclick: () => askReset() });
    const editorHost = el("div", { id: "editor-host" }, el("p", { class: "empty-state", style: "padding:12px 14px", text: "Loading the exercise…" }));

    $("view").replaceChildren(
      el(
        "div",
        { class: "exercise" },
        el(
          "div",
          { class: "ex-head" },
          el(
            "div",
            {},
            el("h1", { id: "view-title", tabindex: "-1", text: ex.title }),
            el(
              "div",
              { class: "ex-meta" },
              el("span", { class: `tag ${ex.level}`, text: ex.level }),
              store.isDone(ex.id) ? el("span", { class: "tag done", id: "done-tag", text: "✓ done" }) : null,
            ),
          ),
          el("div", { class: "actions", id: "actions" }, runButton, resetButton, el("a", { class: "ghost", href: `${COURSE_URL}/${ex.path}`, target: "_blank", rel: "noopener", text: "View on GitHub ↗" })),
        ),
        el(
          "div",
          { class: "work" },
          el("details", { class: "brief", open: true }, el("summary", { text: "The task" }), el("div", { class: "brief-body", id: "brief" })),
          el(
            "div",
            { class: "editor-wrap" },
            el("div", { class: "editor-bar" }, el("span", { class: "file", text: `course/${ex.path}` }), el("span", { id: "save-state", "aria-live": "polite" })),
            editorHost,
          ),
          el("p", { class: "hint", text: "Tab indents. Press Esc to leave the editor. Ctrl+Enter (⌘+Enter on Mac) runs the tests." }),
        ),
        results,
      ),
    );

    const session = { ex, editor: null, running: false, saveTimer: null };
    current = session;

    let stub;
    try {
      stub = await runner.courseFile(ex.path);
    } catch (error) {
      editorHost.replaceChildren(el("p", { class: "empty-state", style: "padding:12px 14px", text: `Couldn't load this exercise (${error.message}). Check your connection and reload the page.` }));
      runButton.disabled = true;
      return;
    }
    if (current !== session) return; // the student navigated away meanwhile

    session.stub = stub;
    $("brief").replaceChildren(...renderBrief(docstringOf(stub)));
    const code = store.draft(ex.id) ?? stub;
    const CodeMirror = await loadEditorLib();
    if (current !== session) return;
    session.editor = mountEditor(editorHost, code, CodeMirror, ex);
  }

  function mountEditor(host, code, CodeMirror, ex) {
    host.replaceChildren();
    const onChange = () => scheduleSave();
    if (CodeMirror) {
      const cm = CodeMirror(host, {
        value: code,
        mode: "python",
        lineNumbers: true,
        indentUnit: 4,
        tabSize: 4,
        indentWithTabs: false,
        viewportMargin: Infinity,
        extraKeys: {
          Tab: (editor) => editor.execCommand(editor.somethingSelected() ? "indentMore" : "insertSoftTab"),
          "Shift-Tab": "indentLess",
          "Ctrl-Enter": () => runTests(),
          "Cmd-Enter": () => runTests(),
          // Leaving the editor by keyboard: Esc moves focus to Run tests.
          Esc: () => $("run").focus(),
        },
      });
      cm.getInputField().setAttribute("aria-label", `Code for ${ex.title}`);
      cm.on("change", onChange);
      return { get: () => cm.getValue(), set: (v) => cm.setValue(v), focus: () => cm.focus(), kind: "codemirror" };
    }
    const area = el("textarea", { class: "editor-plain", spellcheck: "false", "aria-label": `Code for ${ex.title}` });
    area.value = code;
    area.addEventListener("input", onChange);
    area.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        runTests();
      } else if (event.key === "Escape") {
        $("run").focus();
      } else if (event.key === "Tab" && !event.shiftKey) {
        event.preventDefault();
        area.setRangeText("    ", area.selectionStart, area.selectionEnd, "end");
        onChange();
      }
    });
    host.append(area);
    return { get: () => area.value, set: (v) => { area.value = v; }, focus: () => area.focus(), kind: "textarea" };
  }

  function scheduleSave() {
    const session = current;
    if (!session || !session.editor) return;
    $("save-state").textContent = "Saving…";
    clearTimeout(session.saveTimer);
    session.saveTimer = setTimeout(() => saveNow(session), SAVE_DELAY_MS);
  }

  async function saveNow(session) {
    clearTimeout(session.saveTimer);
    if (!session.editor) return;
    const code = session.editor.get();
    // Opening an exercise isn't starting it: an untouched file isn't a draft.
    if (code === session.stub && store.draft(session.ex.id) === null) return;
    await store.saveDraft(session.ex.id, code);
    if (current === session) $("save-state").textContent = store.user ? "Saved to your account" : "Saved in this browser";
    renderTreeStatus(session.ex);
  }

  function renderTreeStatus(ex) {
    const link = document.querySelector(`.tree a[data-id="${ex.id}"]`);
    if (!link) return;
    const status = statusOf(ex);
    link.querySelector(".status-dot").className = `status-dot ${status}`;
    link.querySelector(".sr-only").textContent = `, ${STATUS_TEXT[status]}`;
  }

  // Reset asks in place: replacing the student's code can't be undone.
  function askReset() {
    const actions = $("actions");
    const keep = Array.from(actions.children);
    const restore = () => {
      actions.replaceChildren(...keep);
      $("reset-code").focus();
    };
    const no = el("button", { type: "button", class: "ghost", id: "reset-no", text: "Keep my code", onclick: restore });
    actions.replaceChildren(
      el("span", { class: "hint", text: "Replace your code with the original exercise?" }),
      el("button", {
        type: "button",
        class: "button",
        id: "reset-yes",
        text: "Replace",
        onclick: async () => {
          const session = current;
          session.editor.set(session.stub);
          clearTimeout(session.saveTimer);
          await store.clearDraft(session.ex.id);
          $("save-state").textContent = "Reset to the original";
          renderTreeStatus(session.ex);
          restore();
        },
      }),
      no,
    );
    no.focus();
  }

  async function runTests() {
    const session = current;
    if (!session || !session.editor || session.running) return;
    session.running = true;
    const runButton = $("run");
    runButton.disabled = true;
    const body = $("results-body");
    const status = el("p", { class: "summary", id: "run-status", text: "Starting…" });
    body.replaceChildren(status);
    runner.onStatus = (text) => {
      if (current === session) status.textContent = text;
    };

    try {
      await saveNow(session);
      const ex = session.ex;
      const files = {};
      for (const other of siblingsOf(ex)) {
        files[other.path] = other.id === ex.id ? session.editor.get() : store.draft(other.id) ?? (await runner.courseFile(other.path));
      }
      const result = await runner.run({ testPath: testPathOf(ex), keyword: keywordOf(ex), files });
      store.recordActivity();
      if (current !== session) return;
      showResults(session, result);
    } catch (error) {
      if (current === session) {
        body.replaceChildren(
          el("p", { class: "summary fail", text: "Couldn't run the tests." }),
          el("p", { class: "empty-state", text: `${error.message}. Check your internet connection (the first run downloads Python) and try again.` }),
        );
      }
    } finally {
      session.running = false;
      if (current === session) runButton.disabled = false;
    }
  }

  function showResults(session, result) {
    const tests = result.results || [];
    const failed = tests.filter((t) => t.outcome !== "passed");
    const passed = tests.length - failed.length;
    const allPassed = tests.length > 0 && failed.length === 0 && !result.timedOut;
    const body = $("results-body");

    const summary = allPassed
      ? `All ${passed} tests passed. Exercise complete.`
      : tests.length === 0
        ? "No tests ran. Check that the file still defines the function or class it started with."
        : `${passed} of ${tests.length} passed.`;

    body.replaceChildren(
      el("p", { class: `summary ${allPassed ? "pass" : "fail"}`, id: "run-summary", text: summary }),
      el(
        "ul",
        { class: "test-list" },
        tests.map((t) =>
          el(
            "li",
            { class: "test", "data-outcome": t.outcome },
            el(
              "div",
              { class: "row" },
              el("span", { class: t.outcome === "passed" ? "mark-ok" : "mark-bad", "aria-hidden": "true", text: t.outcome === "passed" ? "✓" : "✗" }),
              el("span", { class: "name", title: t.name, text: testLabel(t.name) }),
              el("span", { class: "sr-only", text: t.outcome === "passed" ? " passed" : " failed" }),
            ),
            t.message ? el("pre", { text: t.message }) : null,
          ),
        ),
      ),
      result.output ? el("details", { class: "output" }, el("summary", { text: "Full pytest output" }), el("pre", { text: result.output })) : null,
    );

    if (allPassed) {
      store.markDone(session.ex.id);
      if (!$("done-tag")) document.querySelector(".ex-meta").append(el("span", { class: "tag done", id: "done-tag", text: "✓ done" }));
      renderTreeStatus(session.ex);
      const next = nextExercise(session.ex.id);
      if (next) body.append(el("a", { class: "button next-step", id: "next-exercise", href: `#${next.id}`, text: `Next: ${next.title}` }));
    }
  }

  // -- routing and the drawer --------------------------------------------------

  function closeDrawer() {
    $("sidebar").classList.remove("open");
    $("scrim").hidden = true;
    $("open-drawer").setAttribute("aria-expanded", "false");
  }

  function route() {
    closeDrawer();
    if (current && current.editor) saveNow(current);
    current = null;
    const id = decodeURIComponent(window.location.hash.slice(1));
    const ex = byId.get(id);
    if (ex) renderExercise(ex);
    else renderDashboard();
    const title = $("view-title");
    if (title && document.activeElement !== document.body) title.focus({ preventScroll: true });
  }

  function bindChrome() {
    window.Theme.bind($("theme-toggle"));
    $("open-drawer").addEventListener("click", () => {
      $("sidebar").classList.add("open");
      $("scrim").hidden = false;
      $("open-drawer").setAttribute("aria-expanded", "true");
      $("close-drawer").focus();
    });
    $("close-drawer").addEventListener("click", () => {
      closeDrawer();
      $("open-drawer").focus();
    });
    $("scrim").addEventListener("click", closeDrawer);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && $("sidebar").classList.contains("open")) {
        closeDrawer();
        $("open-drawer").focus();
      }
    });
    window.addEventListener("hashchange", route);
    // Save before the tab closes, in case the debounce hasn't fired.
    window.addEventListener("pagehide", () => {
      if (current && current.editor) saveNow(current);
    });
  }

  async function start() {
    bindChrome();
    store = await window.WorkspaceStore.create(window.WORKSPACE_CONFIG || {});
    runner = new window.WorkspaceRunner.Runner();
    store.onChange(() => {
      notice(store.error);
      renderAccount();
      // A sign-in or sign-out changes whose work is shown.
      if (!current) renderDashboard();
      else renderTree(current.ex.id);
    });
    notice(store.error);
    renderAccount();
    route();
  }

  window.Workspace = { docstringOf, renderBrief, keywordOf, testPathOf, testLabel };
  start();
})();
