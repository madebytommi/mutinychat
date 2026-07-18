import { mkdir, readdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const ROOT = process.cwd();
const SCAN_ROOTS = ["src", "static", "build"];
const REPORT_PATH = path.join(ROOT, "artifacts", "frontend-network-report.txt");
const RUNTIME_EXTENSIONS = new Set([
  ".css",
  ".html",
  ".js",
  ".json",
  ".mjs",
  ".svelte",
  ".svg",
  ".ts"
]);

// These are DOM namespace identifiers, not fetchable runtime assets.
const REVIEWED_NON_NETWORK_URIS = new Set([
  "http://www.w3.org/1998/Math/MathML",
  "http://www.w3.org/1999/xhtml",
  "http://www.w3.org/1999/xlink",
  "http://www.w3.org/2000/svg"
]);

// Svelte embeds these strings in local error messages. It does not fetch them.
const REVIEWED_NON_NETWORK_PREFIXES = ["https://svelte.dev/e/"];

const URL_PATTERN = /https?:\/\/[^\s"'`()<>]+/giu;
const forbiddenHosts = ["mixkit.co", "assets.mixkit.co"];
/** @type {string[]} */
const findings = [];

/**
 * @param {unknown} error
 * @returns {boolean}
 */
function isMissingPathError(error) {
  return Boolean(
    error &&
      typeof error === "object" &&
      "code" in error &&
      error.code === "ENOENT"
  );
}

/**
 * Removes comments because comment-only license and documentation links cannot
 * initiate runtime requests. String literals and executable code remain scanned.
 *
 * @param {string} text
 * @param {string} extension
 * @returns {string}
 */
function removeNonExecutableComments(text, extension) {
  let scanned = text;

  if ([".css", ".js", ".mjs", ".svelte", ".ts"].includes(extension)) {
    scanned = scanned.replace(/\/\*[\s\S]*?\*\//gu, "");
  }
  if ([".html", ".svelte", ".svg"].includes(extension)) {
    scanned = scanned.replace(/<!--[\s\S]*?-->/gu, "");
  }
  if ([".js", ".mjs", ".svelte", ".ts"].includes(extension)) {
    scanned = scanned.replace(/^\s*\/\/.*$/gmu, "");
  }

  return scanned;
}

/**
 * @param {string} url
 * @returns {boolean}
 */
function isReviewedNonNetworkLiteral(url) {
  return (
    REVIEWED_NON_NETWORK_URIS.has(url) ||
    REVIEWED_NON_NETWORK_PREFIXES.some((prefix) => url.startsWith(prefix))
  );
}

/**
 * @param {string} directory
 * @returns {Promise<string[]>}
 */
async function walk(directory) {
  let entries;
  try {
    entries = await readdir(directory, { withFileTypes: true });
  } catch (error) {
    if (isMissingPathError(error)) return [];
    throw error;
  }

  /** @type {string[]} */
  const files = [];
  for (const entry of entries) {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await walk(fullPath)));
      continue;
    }
    if (entry.isFile() && RUNTIME_EXTENSIONS.has(path.extname(entry.name))) {
      files.push(fullPath);
    }
  }
  return files;
}

for (const relativeRoot of SCAN_ROOTS) {
  const absoluteRoot = path.join(ROOT, relativeRoot);
  try {
    if (!(await stat(absoluteRoot)).isDirectory()) continue;
  } catch (error) {
    if (isMissingPathError(error)) continue;
    throw error;
  }

  for (const file of await walk(absoluteRoot)) {
    const originalText = await readFile(file, "utf8");
    const relativeFile = path.relative(ROOT, file);
    const extension = path.extname(file);
    const executableText = removeNonExecutableComments(originalText, extension);

    for (const host of forbiddenHosts) {
      if (originalText.toLowerCase().includes(host)) {
        findings.push(`${relativeFile}: forbidden runtime host reference: ${host}`);
      }
    }

    for (const match of executableText.matchAll(URL_PATTERN)) {
      const rawUrl = match[0].replace(/[),.;]+$/u, "");
      if (isReviewedNonNetworkLiteral(rawUrl)) continue;
      findings.push(`${relativeFile}: unexpected external runtime URL: ${rawUrl}`);
    }
  }
}

const uniqueFindings = [...new Set(findings)].sort();
await mkdir(path.dirname(REPORT_PATH), { recursive: true });

if (uniqueFindings.length > 0) {
  const report = [
    "Frontend privacy check failed.",
    "Runtime frontend files must not load unexpected external origins.",
    "",
    ...uniqueFindings.map((finding) => `- ${finding}`),
    ""
  ].join("\n");
  await writeFile(REPORT_PATH, report, "utf8");
  console.error(report);
  process.exit(1);
}

const successMessage = "Frontend privacy check passed: no unexpected external runtime URLs were found.";
await writeFile(REPORT_PATH, `${successMessage}\n`, "utf8");
console.log(successMessage);
