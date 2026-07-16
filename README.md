# MutinyChat

MutinyChat is a retro-styled desktop chat app inspired by AOL and MSN, built with Tauri, Svelte, Python, and Tor.

It supports direct room sharing over Tor onion services with ephemeral chat behavior and encrypted message transport. This remains an actively developed MVP/prototype, not a professionally audited or production-grade secure messenger.

## Current project status

Implemented:

- Tauri v2 desktop shell
- Svelte 5 frontend
- Python stdio JSON backend
- Tor onion-service hosting and SOCKS connections through Stem and PySocks
- PyNaCl public-key session handshake and encrypted messages
- One host and one guest per room
- Windows and macOS packaging work

## Windows downloads

Tagged releases are built by GitHub Actions on `windows-latest` for `x86_64-pc-windows-msvc`.

Release artifacts include:

- An NSIS installer
- An MSI installer when Tauri produces one successfully
- A portable Windows ZIP
- `SHA256SUMS.txt`

The Windows package bundles the compiled MutinyChat application, a self-contained PyInstaller backend, and the official Tor Expert Bundle runtime. End users do not need Python, Tor Browser, Node.js, Rust, Git, or developer tools.

### Unsigned-build warning

Current Windows builds are unsigned. Microsoft Defender SmartScreen may warn that the publisher is unknown. Review the GitHub release, verify the SHA-256 checksum, and make an informed choice. Do not disable antivirus or Windows security protections.

### Installer

Download the NSIS `.exe` from the GitHub Release, verify its checksum, and run it. The installer uses current-user mode and does not require a machine-wide installation.

### Portable ZIP

Extract the portable ZIP as a complete folder and run `mutinychat.exe`. Keep `mutinychat-backend.exe`, the `tor` directory, and the `data` directory beside the application.

## Architecture

### Frontend

- SvelteKit and Vite
- SPA mode using `adapter-static`
- Bootstrap imported from npm
- Main UI in `src/App.svelte`

### Desktop shell

- Tauri v2 Rust host in `src-tauri`
- Static frontend assets in production
- One managed backend process over stdio JSON
- Release builds resolve the backend and Tor from Tauri's application resource directory
- Windows child processes are launched without persistent console windows

### Backend

- Python process in development, compiled PyInstaller sidecar in Windows releases
- Tor onion services and SOCKS connections through Stem and PySocks
- PyNaCl `Box` public-key handshake and encrypted messages
- Runtime Tor data stored in a temporary writable directory and removed during normal shutdown

## Repository layout

- `src/` — Svelte frontend
- `backend/` — Python backend, tests, and dependency files
- `scripts/build-backend-sidecar.sh` — macOS arm64 sidecar helper
- `scripts/build-backend-sidecar.ps1` — reproducible Windows PyInstaller build
- `scripts/prepare-tor-windows.ps1` — official Tor download, signature verification, and resource preparation
- `scripts/verify-windows-package.ps1` — installer/runtime verification and portable ZIP creation
- `src-tauri/` — Rust/Tauri application
- `.github/workflows/ci.yml` — normal Linux validation
- `.github/workflows/windows-release.yml` — Windows build and tagged-release pipeline

## Development requirements

- Node.js 20 or compatible
- Rust toolchain and Cargo
- Python 3.12 recommended
- Tor installed locally for development room testing

Install frontend dependencies:

```bash
npm ci
```

Create a Python environment and install backend dependencies:

```bash
python -m venv .venv
python -m pip install -r backend/requirements.txt
```

Run desktop development mode:

```bash
npm run tauri dev
```

## Windows build process

Run these commands from a Windows development machine with Node.js, Python, Rust, GnuPG, and Tauri's Windows prerequisites installed:

```powershell
npm ci
npm run check
npm run build
npm run build:backend:windows
npm run prepare:tor:windows
npx tauri build --target x86_64-pc-windows-msvc --bundles nsis,msi
npm run verify:package:windows
```

The backend build uses pinned packages from `backend/requirements-windows.lock` and produces:

`backend/dist/mutinychat-backend-x86_64-pc-windows-msvc.exe`

Tauri strips the target suffix in the packaged runtime and launches `mutinychat-backend.exe` from its resource directory.

## Tor source and verification

The Windows workflow pins the official Tor Project Expert Bundle associated with Tor Browser `15.0.18`:

`tor-expert-bundle-windows-x86_64-15.0.18.tar.gz`

The archive and detached signature are downloaded from the Tor Project archive. The build imports the pinned Tor Browser Developers signing fingerprint:

`EF6E286DDA85EA2A4BA7DE684E2C6E8793298290`

GnuPG must successfully verify the detached signature before packaging continues. The complete Tor executable directory, required DLLs, and GeoIP data are included. The repository does not commit downloaded Tor binaries.

## GitHub release behavior

Pull requests run the Windows build and upload temporary Actions artifacts for review. They do not publish GitHub Releases.

A tag matching `v*`, such as `v0.1.0`, runs the same verified build and publishes the resulting Windows artifacts through GitHub Releases. `SHA256SUMS.txt` is generated from the final files.

## Automated Windows checks

The Windows workflow checks:

- Frontend type checking and production build
- Python compilation and unit tests
- Self-contained backend CLI ping
- Backend stdio JSON ping
- Official Tor signature
- Tor executable, DLLs, GeoIP data, and version command
- Rust formatting, Clippy, and tests
- NSIS installer existence
- MSI existence when available
- Packaged application, backend, Tor, and data files
- Portable ZIP contents
- Absence of common development caches in the portable ZIP
- Brief packaged-app launch without immediate termination

A Tor version check does not prove that a real room can be created or joined.

## Clean-machine manual test checklist

These steps are required before calling a release fully verified. They are not marked as passed merely because CI succeeds.

1. Use a clean Windows machine or VM without Python or Tor installed.
2. Download MutinyChat from GitHub Releases without cloning the repository.
3. Verify the artifact against `SHA256SUMS.txt`.
4. Install or extract MutinyChat.
5. Launch it and confirm no console window remains open.
6. Create a room and confirm a v3 onion address appears.
7. Join from a second independent installation.
8. Exchange multiple messages in both directions.
9. Disconnect and reconnect where supported.
10. Close both applications and confirm no backend or Tor processes remain.
11. Confirm temporary Tor directories are cleaned after normal shutdown.
12. Reboot and launch again.
13. Uninstall and confirm normal application cleanup.

## Known limitations

- Windows builds are unsigned and may trigger SmartScreen.
- CI cannot prove two-peer Tor connectivity on separate machines.
- No user-verifiable safety-number or identity-verification UI exists yet.
- The cryptographic and networking design has not received an independent professional audit.
- Unexpected termination may leave temporary Tor data until the operating system cleans its temporary directory.
- The application remains a two-person prototype rather than a general-purpose group messenger.

## Security and privacy notes

- No central chat server is used by design.
- Do not treat prototype status as a guarantee of anonymity or security.
- Do not expose encryption material in logs or bug reports.
- Code signing can be added later using protected CI secrets; no private signing material belongs in the repository.

## License

MIT
