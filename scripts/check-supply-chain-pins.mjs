import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const workflowDirectory = path.join(ROOT, ".github", "workflows");
const workflowFiles = fs.readdirSync(workflowDirectory).filter((name) => /\.ya?ml$/i.test(name));
const errors = [];

for (const name of workflowFiles) {
  const relativePath = path.posix.join(".github/workflows", name);
  const content = fs.readFileSync(path.join(workflowDirectory, name), "utf8");
  for (const match of content.matchAll(/^\s*-?\s*uses:\s*([^\s#]+)(?:\s*#.*)?$/gm)) {
    const reference = match[1];
    if (reference.startsWith("./") || reference.startsWith("docker://")) continue;
    const separator = reference.lastIndexOf("@");
    const revision = separator === -1 ? "" : reference.slice(separator + 1);
    if (!/^[0-9a-f]{40}$/.test(revision)) {
      errors.push(`${relativePath}: action is not pinned to a full commit SHA: ${reference}`);
    }
  }
  if (/toolchain:\s*stable\b/.test(content)) {
    errors.push(`${relativePath}: Rust toolchain must not use the mutable stable channel`);
  }
  if (/python -m pip install(?![^\n]*--require-hashes)/.test(content)) {
    errors.push(`${relativePath}: Python installs must require reviewed artifact hashes`);
  }
  if (/^\s*runs-on:\s*[^\s#]+-latest\s*$/m.test(content)) {
    errors.push(`${relativePath}: runner OS generation must not use a mutable *-latest label`);
  }
  for (const match of content.matchAll(/^\s*(?:node|python)-version:\s*["']?(\d+(?:\.\d+){0,2})["']?\s*$/gm)) {
    if (!/^\d+\.\d+\.\d+$/.test(match[1])) {
      errors.push(`${relativePath}: runtime version must include an exact patch: ${match[0].trim()}`);
    }
  }
}

const windowsWorkflow = fs.readFileSync(path.join(workflowDirectory, "windows-release.yml"), "utf8");
const ciWorkflow = fs.readFileSync(path.join(workflowDirectory, "ci.yml"), "utf8");
const dependencyAudit = fs.readFileSync(
  path.join(ROOT, "scripts", "run-dependency-audit.sh"),
  "utf8",
);
const osvConfiguration = fs.readFileSync(path.join(ROOT, "osv-scanner.toml"), "utf8");
if (!/^\s*GNUPG_VERSION:\s*"\d+\.\d+\.\d+"\s*$/m.test(windowsWorkflow)) {
  errors.push("windows-release.yml: GnuPG version must be exact");
}
if (!/^\s*GNUPG_PACKAGE_SHA256:\s*[0-9A-F]{64}\s*$/m.test(windowsWorkflow)) {
  errors.push("windows-release.yml: GnuPG Chocolatey package SHA-256 must be pinned");
}
if (!/Get-FileHash[^\n]+SHA256/.test(windowsWorkflow)) {
  errors.push("windows-release.yml: GnuPG package hash must be verified before installation");
}
for (const variable of ["NODE_VERSION", "PYTHON_VERSION", "RUST_VERSION"]) {
  if (!new RegExp(`^\\s*${variable}:\\s*"\\d+\\.\\d+\\.\\d+"\\s*$`, "m").test(windowsWorkflow)) {
    errors.push(`windows-release.yml: ${variable} must use an exact patch version`);
  }
}
if (/\bnpx\s+tauri\s+build\b/.test(windowsWorkflow)) {
  errors.push("windows-release.yml: npx must not download a missing Tauri CLI during a release build");
}
for (const [name, workflow] of [
  ["ci.yml", ciWorkflow],
  ["windows-release.yml", windowsWorkflow],
]) {
  if (!/bash scripts\/run-dependency-audit\.sh/.test(workflow)) {
    errors.push(`${name}: dependency vulnerability audit is not enforced`);
  }
}
if (!/^OSV_VERSION="2\.3\.8"$/m.test(dependencyAudit)) {
  errors.push("run-dependency-audit.sh: OSV Scanner version must be exact");
}
if (!/^OSV_SHA256="[0-9a-f]{64}"$/m.test(dependencyAudit)) {
  errors.push("run-dependency-audit.sh: OSV Scanner SHA-256 must be pinned");
}
if (!/sha256sum --check --strict/.test(dependencyAudit)) {
  errors.push("run-dependency-audit.sh: OSV Scanner hash must be verified before execution");
}
if (!dependencyAudit.includes("--config=osv-scanner.toml")) {
  errors.push("run-dependency-audit.sh: reviewed OSV exception policy is not applied");
}
for (const lockfile of [
  "package-lock.json",
  "src-tauri/Cargo.lock",
  "requirements.txt:backend/requirements.txt",
  "requirements.txt:backend/requirements-windows.lock",
]) {
  if (!dependencyAudit.includes(`--lockfile=${lockfile}`)) {
    errors.push(`run-dependency-audit.sh: missing vulnerability scan input ${lockfile}`);
  }
}
const osvExceptions = osvConfiguration.split("[[IgnoredVulns]]").slice(1);
for (const exception of osvExceptions) {
  const id = exception.match(/^id\s*=\s*"([^"]+)"/m)?.[1] ?? "<unknown>";
  if (!/^ignoreUntil\s*=\s*\d{4}-\d{2}-\d{2}\s*$/m.test(exception)) {
    errors.push(`osv-scanner.toml: ${id} exception must have an expiration date`);
  }
  if (!/^reason\s*=\s*".{20,}"\s*$/m.test(exception)) {
    errors.push(`osv-scanner.toml: ${id} exception must have a specific review reason`);
  }
}

for (const relativePath of ["backend/requirements.txt", "backend/requirements-windows.lock"]) {
  const content = fs.readFileSync(path.join(ROOT, relativePath), "utf8");
  if (!/^--require-hashes$/m.test(content)) {
    errors.push(`${relativePath}: missing --require-hashes`);
  }
  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || trimmed.startsWith("--hash=sha256:")) continue;
    if (trimmed === "--require-hashes") continue;
    if (relativePath === "backend/requirements-windows.lock" && trimmed === "-r requirements.txt") continue;
    if (trimmed.startsWith("-") || trimmed.startsWith("\\")) {
      errors.push(`${relativePath}: unsupported requirement option: ${trimmed}`);
      continue;
    }
    if (!/^[A-Za-z0-9_.-]+==[^\s\\]+(?:\s+\\)?$/.test(trimmed)) {
      errors.push(`${relativePath}: dependency is not exactly pinned: ${trimmed}`);
    }
  }
}

if (errors.length) {
  throw new Error(`Supply-chain pin check failed:\n- ${errors.join("\n- ")}`);
}

console.log("Supply-chain pin check passed: actions and Python artifacts are immutable.");
