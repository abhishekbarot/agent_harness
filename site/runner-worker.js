// Runs an exercise's pytest suite inside Pyodide, in a worker thread.
//
// A worker, not the page, because student code can loop forever (an agent
// loop with no exit is the classic bug). The page can terminate a worker and
// start a fresh one; it cannot interrupt Python running on its own thread.

/* global loadPyodide, importScripts */

let pyodide = null;

const ROOT = "/home/pyodide/course";

const COLLECT = `
import io, contextlib, importlib, re, sys
import pytest

sys.dont_write_bytecode = True  # never run a stale .pyc of the student's old code

class Collector:
    def __init__(self):
        self.results = []

    def _message(self, report):
        crash = getattr(report.longrepr, "reprcrash", None)
        if crash is not None and crash.message:
            return crash.message
        return (report.longreprtext or "")[-2000:]

    def pytest_collectreport(self, report):
        if report.failed:
            self.results.append({"name": "Loading the test file", "outcome": "error",
                                 "message": (report.longreprtext or "")[-2000:]})

    def pytest_runtest_logreport(self, report):
        if report.when == "call" or report.failed:
            name = report.nodeid.split("::", 1)[-1].replace("::", " > ")
            outcome = report.outcome if report.when == "call" else "error"
            self.results.append({"name": name, "outcome": outcome,
                                 "message": self._message(report) if report.failed else ""})

def run_suite(test_path, keyword):
    # Forget everything imported from the course on the previous run, so the
    # student's edited files are imported fresh.
    for name in list(sys.modules):
        if re.match(r"^(ex\\d+_|test_section|loader$|conftest$|common($|\\.))", name):
            del sys.modules[name]
    importlib.invalidate_caches()
    collector = Collector()
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = pytest.main(["-q", "-p", "no:cacheprovider", "-k", keyword, test_path],
                           plugins=[collector])
    return {"exit_code": int(code), "results": collector.results, "output": out.getvalue()[-8000:]}
`;

function writeFiles(files) {
  for (const [rel, text] of Object.entries(files)) {
    const path = `${ROOT}/${rel}`;
    pyodide.FS.mkdirTree(path.slice(0, path.lastIndexOf("/")));
    pyodide.FS.writeFile(path, text);
  }
}

async function init({ pyodideBase, wheels, common }) {
  postMessage({ type: "status", text: "Downloading Python (about 10 MB, first time only)…" });
  importScripts(`${pyodideBase}pyodide.js`);
  pyodide = await loadPyodide({ indexURL: pyodideBase });
  postMessage({ type: "status", text: "Installing pytest…" });
  await pyodide.loadPackage(wheels);
  writeFiles(common);
  pyodide.runPython(COLLECT);
}

self.onmessage = async (event) => {
  const message = event.data;
  try {
    if (message.type === "init") {
      await init(message);
      postMessage({ type: "ready" });
    } else if (message.type === "run") {
      writeFiles(message.files);
      const run = pyodide.globals.get("run_suite");
      const proxy = run(`${ROOT}/${message.testPath}`, message.keyword);
      const result = proxy.toJs({ dict_converter: Object.fromEntries });
      proxy.destroy();
      run.destroy();
      postMessage({ type: "result", id: message.id, ...result });
    }
  } catch (error) {
    postMessage({ type: "failed", id: message.id, error: String(error && error.message ? error.message : error) });
  }
};
