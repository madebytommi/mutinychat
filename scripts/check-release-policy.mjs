import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const workflow = fs.readFileSync(path.join(ROOT, ".github", "workflows", "windows-release.yml"), "utf8");
const packageScript = fs.readFileSync(path.join(ROOT, "scripts", "verify-windows-package.ps1"), "utf8");
const errors = [];

if (/^\s*push:\s*$[\s\S]*?^\s*tags:/m.test(workflow)) {
  errors.push("release workflow must not publish in response to a pushed tag");
}
if (!/^\s*workflow_dispatch:\s*$/m.test(workflow)) {
  errors.push("release workflow must require an explicit manual dispatch");
}
if (!/^\s*environment:\s*release\s*$/m.test(workflow)) {
  errors.push("draft release creation must use the release environment");
}
if (!/^\s*--verify-tag\s*$/m.test(workflow) || !/^\s*--draft\s*$/m.test(workflow)) {
  errors.push("GitHub release creation must verify the existing tag and remain draft-only");
}
if (!/actions\/attest-build-provenance@[0-9a-f]{40}/.test(workflow)) {
  errors.push("tagged artifacts must receive an immutable build-provenance attestation");
}
if (/MutinyChat_0\.1\.0_windows/.test(packageScript)) {
  errors.push("portable artifact name must not contain a hardcoded application version");
}
if (!/MutinyChat_\$\{AppVersion\}_windows/.test(packageScript)) {
  errors.push("portable artifact name must be derived from the validated Tauri version");
}

if (errors.length) {
  throw new Error(`Release policy check failed:\n- ${errors.join("\n- ")}`);
}

console.log("Release policy check passed: publication is manual, attested, version-bound, and draft-only.");
