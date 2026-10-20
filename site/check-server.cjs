// Test helpers shared by the browser checks.
//
// serve() serves site/ the way GitHub Pages will, plus course/ at /course/ --
// minus the reference solutions, which are never published.
//
// routeLibraries() answers the CDN requests the pages make (Pyodide,
// CodeMirror) from local npm packages when they are installed, so the checks
// run the same offline as on CI:
//
//   npm install pyodide@0.26.4 codemirror@5.65.16 playwright

const http = require("http");
const fs = require("fs");
const path = require("path");

const SITE = __dirname;
const COURSE = path.join(__dirname, "..", "course");
const TYPES = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".css": "text/css",
  ".png": "image/png",
  ".py": "text/plain; charset=utf-8",
  ".whl": "application/octet-stream",
  ".wasm": "application/wasm",
  ".json": "application/json",
  ".zip": "application/zip",
};

function resolveRequest(urlPath, roots) {
  const clean = decodeURIComponent(urlPath.split("?")[0]);
  if (clean.startsWith("/course/")) {
    const rel = clean.slice("/course/".length);
    // Solutions and caches are never served, exactly as in the deploy.
    if (/(^|\/)(solutions|__pycache__)(\/|$)/.test(rel)) return null;
    const file = path.join(roots.course, rel);
    return file.startsWith(roots.course + path.sep) ? file : null;
  }
  const file = path.join(roots.site, clean === "/" ? "index.html" : clean);
  return file.startsWith(roots.site) ? file : null;
}

function serve({ site = SITE, course = COURSE } = {}) {
  const roots = { site: path.resolve(site), course: path.resolve(course) };
  const server = http.createServer((req, res) => {
    const file = resolveRequest(req.url, roots);
    if (!file || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404).end("not found");
      return;
    }
    res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] || "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

function packageDir(name) {
  try {
    return path.dirname(require.resolve(`${name}/package.json`, { paths: [process.cwd(), SITE, ...module.paths] }));
  } catch (_) {
    return null;
  }
}

const PYODIDE_CDN = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
const CODEMIRROR_CDN = "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/";
const CODEMIRROR_FILES = {
  "codemirror.min.js": "lib/codemirror.js",
  "codemirror.min.css": "lib/codemirror.css",
  "mode/python/python.min.js": "mode/python/python.js",
};

// Returns which libraries are served locally, e.g. { pyodide: true }.
async function routeLibraries(context) {
  const local = { pyodide: packageDir("pyodide"), codemirror: packageDir("codemirror") };
  if (local.pyodide) {
    await context.route(`${PYODIDE_CDN}**`, (route) => {
      const file = path.join(local.pyodide, new URL(route.request().url()).pathname.split("/").pop());
      if (!fs.existsSync(file)) return route.fulfill({ status: 404, body: "not in the local pyodide package" });
      return route.fulfill({
        path: file,
        headers: { "Content-Type": TYPES[path.extname(file)] || "application/octet-stream", "Access-Control-Allow-Origin": "*" },
      });
    });
  }
  if (local.codemirror) {
    await context.route(`${CODEMIRROR_CDN}**`, (route) => {
      const rel = CODEMIRROR_FILES[route.request().url().slice(CODEMIRROR_CDN.length)];
      if (!rel) return route.fulfill({ status: 404, body: "unknown codemirror file" });
      return route.fulfill({ path: path.join(local.codemirror, rel), headers: { "Access-Control-Allow-Origin": "*" } });
    });
  }
  return { pyodide: Boolean(local.pyodide), codemirror: Boolean(local.codemirror) };
}

// Every visible text element whose color falls below WCAG AA against the
// background actually behind it (4.5:1, or 3:1 for large text).
function lowContrast() {
  const lum = (c) => {
    const [r, g, b] = c.match(/[\d.]+/g).slice(0, 3).map((v) => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const bgOf = (n) => {
    for (; n; n = n.parentElement) {
      const c = getComputedStyle(n).backgroundColor;
      if (c !== "transparent" && !/,\s*0\)$/.test(c)) return c;
    }
    return "rgb(255, 255, 255)";
  };
  const fails = [];
  for (const n of document.querySelectorAll("body *")) {
    if (![...n.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim())) continue;
    const s = getComputedStyle(n);
    if (s.display === "none" || s.visibility === "hidden" || !n.getClientRects().length) continue;
    const [hi, lo] = [lum(s.color), lum(bgOf(n))].sort((a, b) => b - a);
    const ratio = (hi + 0.05) / (lo + 0.05);
    const large = parseFloat(s.fontSize) >= 24 || (parseFloat(s.fontSize) >= 18.66 && +s.fontWeight >= 700);
    if (ratio < (large ? 3 : 4.5)) fails.push(`${n.textContent.trim().slice(0, 20)} ${ratio.toFixed(2)}:1`);
  }
  return [...new Set(fails)];
}

function pngSize(file) {
  const head = fs.readFileSync(file).subarray(0, 24);
  return [head.readUInt32BE(16), head.readUInt32BE(20)];
}

module.exports = { serve, routeLibraries, lowContrast, pngSize, PYODIDE_CDN, CODEMIRROR_CDN };
