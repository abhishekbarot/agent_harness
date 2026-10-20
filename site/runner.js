// The page side of the in-browser grader: starts the Pyodide worker, sends it
// the student's files, and enforces a time limit.

(function () {
  "use strict";

  const PYODIDE_BASE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
  const WHEELS = [
    "vendor/py/iniconfig-2.0.0-py3-none-any.whl",
    "vendor/py/packaging-23.2-py3-none-any.whl",
    "vendor/py/pluggy-1.5.0-py3-none-any.whl",
    "vendor/py/pytest-8.1.1-py3-none-any.whl",
  ];
  // Shared by every section's tests.
  const COMMON = ["conftest.py", "loader.py", "common/__init__.py", "common/fakes.py", "common/harness.py"];
  // Generous for a first run on a slow laptop, short enough that an infinite
  // loop is caught before the student gives up on the page.
  const TIME_LIMIT_MS = 30000;

  const absolute = (rel) => new URL(rel, document.baseURI).href;

  async function fetchText(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`could not load ${url} (${response.status})`);
    return response.text();
  }

  class Runner {
    constructor({ courseBase = "course/", onStatus = () => {} } = {}) {
      this.courseBase = courseBase;
      this.onStatus = onStatus;
      this.worker = null;
      this.ready = null;
      this.pending = new Map();
      this.nextId = 1;
      this.fileCache = new Map();
    }

    // Course files are fetched once per visit; they don't change while the
    // page is open.
    courseFile(rel) {
      if (!this.fileCache.has(rel)) {
        this.fileCache.set(rel, fetchText(absolute(this.courseBase + rel)).catch((error) => {
          this.fileCache.delete(rel);
          throw error;
        }));
      }
      return this.fileCache.get(rel);
    }

    start() {
      if (this.ready) return this.ready;
      this.worker = new Worker(absolute("runner-worker.js"));
      this.ready = (async () => {
        const common = Object.fromEntries(
          await Promise.all(COMMON.map(async (rel) => [rel, await this.courseFile(rel)])),
        );
        await new Promise((resolve, reject) => {
          this.worker.onmessage = ({ data }) => {
            if (data.type === "status") this.onStatus(data.text);
            else if (data.type === "ready") resolve();
            else if (data.type === "failed") reject(new Error(data.error));
            else this.settle(data);
          };
          this.worker.onerror = (event) => reject(new Error(event.message || "the Python worker crashed"));
          this.worker.postMessage({
            type: "init",
            pyodideBase: window.PYODIDE_BASE || PYODIDE_BASE,
            wheels: WHEELS.map(absolute),
            common,
          });
        });
        this.worker.onmessage = ({ data }) => this.settle(data);
      })();
      this.ready.catch(() => this.stop());
      return this.ready;
    }

    settle(data) {
      const job = this.pending.get(data.id);
      if (!job) return;
      this.pending.delete(data.id);
      clearTimeout(job.timer);
      if (data.type === "failed") job.reject(new Error(data.error));
      else job.resolve(data);
    }

    stop() {
      if (this.worker) this.worker.terminate();
      this.worker = null;
      this.ready = null;
      for (const job of this.pending.values()) {
        clearTimeout(job.timer);
        job.reject(new Error("stopped"));
      }
      this.pending.clear();
    }

    // Run one exercise's tests. `files` maps paths under course/ to source
    // text: the student's code for every exercise in the section, since later
    // exercises import earlier ones.
    async run({ testPath, keyword, files }) {
      const testSource = await this.courseFile(testPath);
      await this.start();
      this.onStatus("Running tests…");
      const id = this.nextId++;
      // Tests may shorten the limit to check the timeout without waiting.
      const limit = window.WORKSPACE_TIME_LIMIT_MS || TIME_LIMIT_MS;
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
          this.pending.delete(id);
          this.stop();
          resolve({
            timedOut: true,
            exit_code: -1,
            results: [{
              name: "Time limit",
              outcome: "error",
              message: `The tests didn't finish within ${limit / 1000} seconds. Look for a loop that never exits, such as a while loop whose condition never becomes false.`,
            }],
            output: "",
          });
        }, limit);
        this.pending.set(id, { resolve, reject, timer });
        this.worker.postMessage({ type: "run", id, testPath, keyword, files: { ...files, [testPath]: testSource } });
      });
    }
  }

  window.WorkspaceRunner = { Runner, TIME_LIMIT_MS };
})();
