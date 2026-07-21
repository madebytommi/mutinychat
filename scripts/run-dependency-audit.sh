#!/usr/bin/env bash
set -euo pipefail

OSV_VERSION="2.3.8"
OSV_SHA256="bc98e15319ed0d515e3f9235287ba53cdc5535d576d24fd573978ecfe9ab92dc"
OSV_ASSET="osv-scanner_linux_amd64"
OSV_URL="https://github.com/google/osv-scanner/releases/download/v${OSV_VERSION}/${OSV_ASSET}"
SCANNER_DIRECTORY="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/mutinychat-osv-scanner-${OSV_VERSION}"
SCANNER_PATH="${SCANNER_DIRECTORY}/${OSV_ASSET}"

mkdir -p "${SCANNER_DIRECTORY}"
curl --fail --location --proto '=https' --tlsv1.2 "${OSV_URL}" --output "${SCANNER_PATH}"
printf '%s  %s\n' "${OSV_SHA256}" "${SCANNER_PATH}" | sha256sum --check --strict
chmod +x "${SCANNER_PATH}"

"${SCANNER_PATH}" scan source \
  --config=osv-scanner.toml \
  --lockfile=package-lock.json \
  --lockfile=src-tauri/Cargo.lock \
  --lockfile=requirements.txt:backend/requirements.txt \
  --lockfile=requirements.txt:backend/requirements-windows.lock
