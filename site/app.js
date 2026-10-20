// Renders the sheet from curriculum.js and keeps per-visitor progress in
// localStorage. Storage can be unavailable (private windows, blocked site
// data), so every read and write is guarded and the page works without it.

(function () {
  "use strict";

  const PROGRESS_KEY = "agent-sheet:progress:v1";
  const weeks = window.CURRICULUM || [];
  const resetButton = document.getElementById("reset");

  const store = {
    get(key, fallback) {
      try {
        const raw = window.localStorage.getItem(key);
        return raw === null ? fallback : JSON.parse(raw);
      } catch (_) {
        return fallback;
      }
    },
    set(key, value) {
      try {
        window.localStorage.setItem(key, JSON.stringify(value));
      } catch (_) {
        /* progress just won't persist */
      }
    },
  };

  // Only ids that still exist count, so removing an item never leaves the
  // progress bar stuck above 100%.
  const knownIds = new Set(weeks.flatMap((w) => w.items.map((i) => i.id)));
  const saved = store.get(PROGRESS_KEY, []);
  const done = new Set(Array.isArray(saved) ? saved.filter((id) => knownIds.has(id)) : []);
  let filter = "all";

  const el = (tag, attrs, ...children) => {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === false || value === null || value === undefined) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else node.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children) if (child) node.append(child);
    return node;
  };

  const isAvailable = (item) => item.status === "available";

  const matches = (item) => {
    if (filter === "available") return isAvailable(item);
    if (filter === "exercise" || filter === "capstone") return item.type === filter;
    return true;
  };

  function renderItem(item) {
    const id = `item-${item.id}`;
    const soon = !isAvailable(item);
    const checked = done.has(item.id);

    const box = el("input", {
      type: "checkbox",
      id,
      "data-id": item.id,
      checked,
      disabled: soon,
      "aria-describedby": soon ? `${id}-soon` : null,
    });

    const tags = el(
      "span",
      { class: "tags" },
      el("span", { class: "tag", text: item.type }),
      el("span", { class: `tag ${item.level}`, text: item.level }),
      soon ? el("span", { class: "tag soon", id: `${id}-soon`, text: "coming soon" }) : null,
      !soon && item.path
        ? el("a", {
            class: "open",
            href: `workspace.html#${item.id}`,
            "aria-label": `Open exercise ${item.title} in your workspace`,
            text: "Open",
          })
        : null,
    );

    return el(
      "li",
      { class: `item${soon ? " is-soon" : ""}${checked ? " is-done" : ""}`, "data-type": item.type },
      box,
      el("label", { for: id, text: item.title }),
      tags,
    );
  }

  function weekMeta(week) {
    const available = week.items.filter(isAvailable);
    if (!available.length) return { text: "Coming soon", complete: false };
    const finished = available.filter((i) => done.has(i.id)).length;
    return {
      text: finished === available.length ? "Done ✓" : `${finished} / ${available.length}`,
      complete: finished === available.length,
    };
  }

  function render() {
    const container = document.getElementById("weeks");
    const openWeeks = new Set(
      [...container.querySelectorAll("details[open]")].map((d) => d.dataset.week),
    );
    const firstRender = !container.children.length;
    container.replaceChildren();

    let shown = 0;
    for (const week of weeks) {
      const items = week.items.filter(matches);
      if (!items.length) continue;
      shown += 1;

      const meta = weekMeta(week);
      const hasAvailable = week.items.some(isAvailable);
      const open = firstRender ? hasAvailable : openWeeks.has(String(week.week)) || filter !== "all";

      container.append(
        el(
          "details",
          { class: "week", "data-week": String(week.week), open },
          el(
            "summary",
            {},
            el("span", { class: "week-num", "aria-hidden": "true", text: String(week.week) }),
            el("h2", { class: "week-title", text: `Week ${week.week} · ${week.title}` }),
            el("span", { class: `week-meta${meta.complete ? " complete" : ""}`, text: meta.text }),
            el("span", { class: "week-summary", text: week.summary }),
          ),
          el("ul", { class: "items" }, ...items.map(renderItem)),
        ),
      );
    }
    document.getElementById("empty").hidden = shown > 0;
    renderProgress();
  }

  function renderProgress() {
    const available = weeks.flatMap((w) => w.items).filter(isAvailable);
    const finished = available.filter((i) => done.has(i.id)).length;
    const pct = available.length ? Math.round((finished / available.length) * 100) : 0;

    document.getElementById("progress-count").textContent = `${finished} / ${available.length}`;
    document.getElementById("progress-fill").style.width = `${pct}%`;
    const bar = document.getElementById("progress-bar");
    bar.setAttribute("aria-valuenow", String(pct));
    bar.setAttribute("aria-valuetext", `${finished} of ${available.length} done`);
    // Nothing to clear means nothing to click.
    resetButton.disabled = done.size === 0;
    document.getElementById("progress-note").textContent =
      finished === 0
        ? "Tick items off as you finish them. Progress is saved in this browser only."
        : finished === available.length
          ? "Everything available is done. New weeks are on the way."
          : `${pct}% of what's available so far. Keep going.`;
  }

  document.getElementById("weeks").addEventListener("change", (event) => {
    const box = event.target;
    if (!(box instanceof HTMLInputElement) || box.type !== "checkbox") return;
    const id = box.dataset.id;
    if (box.checked) done.add(id);
    else done.delete(id);
    store.set(PROGRESS_KEY, [...done]);
    box.closest(".item").classList.toggle("is-done", box.checked);

    const week = box.closest("details");
    const data = weeks.find((w) => String(w.week) === week.dataset.week);
    const meta = weekMeta(data);
    const metaEl = week.querySelector(".week-meta");
    metaEl.textContent = meta.text;
    metaEl.classList.toggle("complete", meta.complete);
    renderProgress();
  });

  for (const chip of document.querySelectorAll(".chip")) {
    chip.addEventListener("click", () => {
      filter = chip.dataset.filter;
      for (const other of document.querySelectorAll(".chip")) {
        other.setAttribute("aria-pressed", String(other === chip));
      }
      render();
    });
  }

  // Reset asks in the page itself. Native confirm() is blocked in some
  // embedded browsers, where it silently returns false.
  const resetConfirm = document.getElementById("reset-confirm");
  const showResetConfirm = (show) => {
    resetButton.hidden = show;
    resetConfirm.hidden = !show;
    // After a reset the button is disabled, so focus the filters next to it.
    const target = show
      ? document.getElementById("reset-no")
      : resetButton.disabled
        ? document.querySelector(".chip")
        : resetButton;
    target.focus();
  };
  resetButton.addEventListener("click", () => {
    if (done.size) showResetConfirm(true);
  });
  document.getElementById("reset-no").addEventListener("click", () => showResetConfirm(false));
  document.getElementById("reset-yes").addEventListener("click", () => {
    done.clear();
    store.set(PROGRESS_KEY, []);
    render();
    showResetConfirm(false);
  });
  resetConfirm.addEventListener("keydown", (event) => {
    if (event.key === "Escape") showResetConfirm(false);
  });

  window.Theme.bind(document.getElementById("theme-toggle"));

  render();
})();
