// Light/dark theme, shared by the sheet and the workspace. Follows the
// system until the visitor picks one; the button names the theme it switches
// to, so it always says what a click will do.

(function () {
  "use strict";

  const KEY = "agent-sheet:theme";
  const root = document.documentElement;
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

  const read = () => {
    try {
      return window.localStorage.getItem(KEY);
    } catch (_) {
      return null;
    }
  };
  const write = (value) => {
    try {
      window.localStorage.setItem(KEY, value);
    } catch (_) {
      /* the choice lasts for this visit only */
    }
  };

  // Stored as JSON by earlier versions of the sheet ("\"dark\"").
  const saved = String(read() || "").replace(/"/g, "");
  if (saved === "light" || saved === "dark") root.dataset.theme = saved;

  const current = () => root.dataset.theme || (systemDark.matches ? "dark" : "light");

  function bind(button) {
    const label = () => {
      button.textContent = current() === "dark" ? "Light theme" : "Dark theme";
    };
    button.addEventListener("click", () => {
      const next = current() === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      write(JSON.stringify(next));
      label();
      document.dispatchEvent(new CustomEvent("themechange", { detail: next }));
    });
    systemDark.addEventListener("change", label);
    label();
  }

  window.Theme = { bind, current };
})();
