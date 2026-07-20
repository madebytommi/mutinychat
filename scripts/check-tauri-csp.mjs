import { readFileSync } from "node:fs";
import { isDeepStrictEqual } from "node:util";

const configUrl = new URL("../src-tauri/tauri.conf.json", import.meta.url);
const config = JSON.parse(readFileSync(configUrl, "utf8"));
const security = config?.app?.security;

const productionPolicy = {
  "default-src": ["'none'"],
  "script-src": ["'self'"],
  "style-src": ["'self'"],
  "img-src": ["'self'"],
  "font-src": ["'self'"],
  "connect-src": ["ipc:", "http://ipc.localhost"],
  "media-src": ["'none'"],
  "object-src": ["'none'"],
  "frame-src": ["'none'"],
  "frame-ancestors": ["'none'"],
  "worker-src": ["'none'"],
  "base-uri": ["'none'"],
  "form-action": ["'none'"]
};

const developmentPolicy = {
  ...productionPolicy,
  "style-src": ["'self'", "'unsafe-inline'"],
  "connect-src": [
    "'self'",
    "ipc:",
    "http://ipc.localhost",
    "ws://127.0.0.1:1420"
  ]
};

if (!isDeepStrictEqual(security?.csp, productionPolicy)) {
  throw new Error("Tauri production CSP is missing or differs from the approved restrictive policy");
}

if (!isDeepStrictEqual(security?.devCsp, developmentPolicy)) {
  throw new Error("Tauri development CSP is missing or permits sources outside the approved loopback policy");
}

if (security?.dangerousDisableAssetCspModification !== false) {
  throw new Error("Tauri's build-time CSP nonce and hash injection must remain enabled");
}

console.log("Tauri CSP check passed: production resources are local-only and IPC is explicitly scoped.");
