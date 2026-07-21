import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const RELEASE_VERSION = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;

function readJson(relativePath) {
  return JSON.parse(fs.readFileSync(path.join(ROOT, relativePath), "utf8"));
}

function cargoPackageVersion() {
  const manifest = fs.readFileSync(path.join(ROOT, "src-tauri", "Cargo.toml"), "utf8");
  const packageBlock = manifest.match(/\[package\]([\s\S]*?)(?:\n\[|$)/)?.[1] || "";
  return packageBlock.match(/^version\s*=\s*"([^"]+)"/m)?.[1] || "";
}

function cargoLockVersion() {
  const lock = fs.readFileSync(path.join(ROOT, "src-tauri", "Cargo.lock"), "utf8");
  return lock.match(/\[\[package\]\]\s*\nname = "mutinychat"\s*\nversion = "([^"]+)"/)?.[1] || "";
}

const packageJson = readJson("package.json");
const packageLock = readJson("package-lock.json");
const tauriConfig = readJson(path.join("src-tauri", "tauri.conf.json"));
const versions = new Map([
  ["package.json", String(packageJson.version || "")],
  ["package-lock.json", String(packageLock.version || "")],
  ["package-lock.json root package", String(packageLock.packages?.[""]?.version || "")],
  ["src-tauri/Cargo.toml", cargoPackageVersion()],
  ["src-tauri/Cargo.lock", cargoLockVersion()],
  ["src-tauri/tauri.conf.json", String(tauriConfig.version || "")]
]);

const expected = versions.get("package.json");
if (!expected || !RELEASE_VERSION.test(expected)) {
  throw new Error(`package.json contains an invalid release version: ${expected || "<missing>"}`);
}

for (const [source, version] of versions) {
  if (version !== expected) {
    throw new Error(`Release version mismatch: ${source} has ${version || "<missing>"}, expected ${expected}`);
  }
}

const tagIndex = process.argv.indexOf("--tag");
if (tagIndex !== -1) {
  const tag = String(process.argv[tagIndex + 1] || "");
  if (tag !== `v${expected}`) {
    throw new Error(`Release tag ${tag || "<missing>"} does not match manifest version v${expected}`);
  }
}

console.log(`Release version verified: ${expected}`);
