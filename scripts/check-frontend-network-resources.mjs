import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const ROOT = process.cwd();
const SCAN_ROOTS = ["src", "static", "build"];
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
  "http://www.w3.org/2000/svg"
]);

const URL_PATTERN = /https?:\/\/[^\s"'`()<>]+/giu;
const forbiddenHosts = ["mixkit.co", "assets.mixkit.co"];
const findings = [];

async function walk(directory) {
  let entries;
  try {
    entries = await readdir(directory, { withFileTypes: true });
  } catch (error) {
    if (error?.code === "ENOENT") return [];
    throw error;
  }

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
    if (error?.code === "ENOENT") continue;
    throw error;
  }

  for (const file of await walk(absoluteRoot)) {
    const text = await readFile(file, "utf8");
    const relativeFile = path.relative(ROOT, file);

    for (const host of forbiddenHosts) {
      if (text.toLowerCase().includes(host)) {
        findings.push(`${relativeFile}: forbidden runtime host reference: ${host}`);
      }
    }

    for (const match of text.matchAll(URL_PATTERN)) {
      const rawUrl = match[0].replace(/[),.;]+$/u, "");
      if (REVIEWED_NON_NETWORK_URIS.has(rawUrl)) continue;
      findings.push(`${relativeFile}: unexpected external runtime URL: ${rawUrl}`);
    }
  }
}

if (findings.length > 0) {
  console.error("Frontend privacy check failed. Runtime frontend files must not load external origins.");
  for (const finding of [...new Set(findings)].sort()) {
    console.error(`- ${finding}`);
  }
  process.exit(1);
}

console.log("Frontend privacy check passed: no unexpected external runtime URLs were found.");
