import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const forbiddenDirectories = ["backend/build", "backend/dist"];
const result = spawnSync("git", ["ls-files", "-z", "--", ...forbiddenDirectories], {
  cwd: ROOT,
  encoding: "utf8",
});

if (result.error) {
  throw new Error(`Repository artifact check could not run Git: ${result.error.message}`);
}

if (result.status !== 0) {
  throw new Error(
    `Repository artifact check could not read tracked files:\n${result.stderr.trim()}`,
  );
}

const trackedArtifacts = result.stdout.split("\0").filter(Boolean);

if (trackedArtifacts.length > 0) {
  console.error("Repository artifact check failed: generated backend artifacts are tracked by Git:");
  for (const trackedPath of trackedArtifacts) {
    console.error(`- ${trackedPath}`);
  }
  console.error("Remove these paths from Git; local ignored build output may remain on disk.");
  process.exitCode = 1;
} else {
  console.log("Repository artifact check passed: no generated backend artifacts are tracked by Git.");
}
