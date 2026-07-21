MutinyChat Implementation Readiness Report
1. Repository snapshot
Item	Observed state
Branch	main, tracking origin/main
Commit	f9d5c0551f1101df9db4665b67b6fb3f098a661f
Working tree	Modified: .gitignore only
Local diff	Seven added lines ignore the five planning documents
Untracked files	None reported normally; the five authority documents are present but ignored
Ignored generated directories present	.svelte-kit, .venv-windows-build, artifacts, build, node_modules, src-tauri/target
Tracked generated artifacts	41 files under backend/build/ and backend/dist/, totaling 47,351,497 bytes
Default remote branch	origin/main at the same commit
Tags	None in the fetched repository
Current application version	0.1.0 across the checked manifests
Protocol version	3
The stack is Svelte 5/SvelteKit/Vite with Bootstrap and local QR generation; Tauri 2 and Rust for desktop process management and IPC; Python 3.12 with Stem, PySocks, and PyNaCl; and a bundled Tor Expert Bundle for Windows packaging.
The intended supported path is Windows 10/11 x86-64 through an NSIS installer and portable ZIP. The current workflow also attempts an optional MSI.
Validation evidence is mixed:
•	The exact main commit passed the Linux frontend, backend, rust, and dependency-audit jobs in GitHub Actions run 29797371690.
•	The Windows package job for the code merged as PR 19 failed before Python installation because pinned Python 3.12.13 was unavailable on windows-2022. See failed Windows job 88530686268.
•	No local tests or builds were run during this review because they could create caches or generated artifacts.
•	No real Tor room, two-device connection, clean-machine installation, packaged-process cleanup, or runtime network-leakage test was performed.
•	No files were changed during this review. The existing .gitignore modification was preserved.
2. Project understanding
MutinyChat is intended to be a deliberately narrow desktop messenger: one host, one guest, one temporary room, text only, no accounts, no central message server, and no persistent conversation history. Windows is the sole MVP release platform; macOS, Linux, mobile, and browser deployment are deferred.
The promised journey is linear:
1.	Choose a temporary display name.
2.	Create an ephemeral Tor onion room or paste an authenticated invitation.
3.	Establish a mutually confirmed encrypted channel.
4.	Compare a session-specific safety code through a separate trusted method.
5.	Require both participants to confirm that code before messaging.
6.	Exchange bounded encrypted text.
7.	Close the room and truthfully report the resulting cleanup state.
The security model separates three claims that the interface must not conflate:
•	Tor runtime or current-room routing
•	Cryptographically confirmed encrypted channel
•	Participant verified for this session through mutual safety-code confirmation
It does not claim permanent identity, whole-device anonymity, secure memory erasure, protection from a compromised operating system, or a professional security audit.
The design direction is a compact, warm, retro Windows messenger—not a security dashboard or cyberpunk tool. Nostalgia is subordinate to truthful state, accessibility, reliability, and clear recovery. The visual implementation broadly follows the intended blue/silver classic-messenger personality, but several interaction details do not yet meet the design authority.
Engineering is expected to stay small, explicit, bounded, and testable. Framework expansion, central services, databases, telemetry, persistent accounts, multiple rooms, groups, media transfer, auto-updates, and plugin systems are prohibited during the MVP pass. The definition of success includes real packaged Windows validation; passing CI alone is explicitly insufficient.
3. Current architecture
State ownership
State	Intended/current owner	Current frontend behavior
Tor process and controller	Python backend	Polled every 250 ms and mapped fail-closed
Onion service and room mode	Python backend	Partially represented; room mode/listener readiness are missing from snapshots
Listener and peer socket	Python backend	Peer count and channel state are polled
Channel keys and handshake	Python backend	Frontend maps backend channel_status and encrypted together
Participant verification	Python backend	Polled, although immediate command responses also update UI state
Pending peer events	Python backend bounded deque	Polled in batches
Visible history and draft	Svelte frontend	Bounded visible history; draft is currently lost after failed sends
Backend process and IPC	Rust/Tauri	One child process, one bounded worker queue, bounded output, class-specific timeouts
Release version	Five manifests/locks	Checked by a release-policy script
Frontend
[src/App.svelte (line 30)](D:/From Mac Desktop/GitHub/mutinychat/src/App.svelte:30) is a single large component containing lobby, room-sharing, verification, messaging, diagnostics, clipboard behavior, polling, and most operation state.
Security, Tor, connection, event, history, clipboard, and username behavior have been extracted into small helpers under [src/lib](D:/From Mac Desktop/GitHub/mutinychat/src/lib). The frontend polls poll_messages every 250 ms and treats Rust’s {status:"busy"} as a non-destructive skipped poll.
Tauri/Rust host
[src-tauri/src/lib.rs (line 13)](D:/From Mac Desktop/GitHub/mutinychat/src-tauri/src/lib.rs:13) launches one Python sidecar and sends newline-delimited JSON over stdio.
Implemented safeguards include:
•	512 KiB bounded backend output lines
•	At most 20 invalid output lines
•	A one-entry request queue
•	Five-, fifteen-, and ninety-second response-timeout classes
•	Immediate busy responses instead of accumulating polls
•	No automatic replay after uncertain command failure
•	A bounded graceful-close attempt followed by child termination
The exposed backend_ipc command still accepts arbitrary command strings and unbounded string arguments before validation.
Python backend and Tor
[backend/main.py (line 46)](D:/From Mac Desktop/GitHub/mutinychat/backend/main.py:46) owns process-level room, Tor, peer, cryptographic, verification, and queue state.
Tor is started with:
•	Loopback control and SOCKS ports
•	CookieAuthentication
•	IsolateSOCKSAuth
•	A temporary data directory
•	Bundled-path enforcement in packaged builds
•	Fresh SOCKS credentials for each join
The host currently creates an onion service first, returns the invitation, and relies on a second frontend command to start the listener. That is the principal lifecycle defect.
Invitation and encrypted-channel protocol
[backend/participant_auth.py (line 13)](D:/From Mac Desktop/GitHub/mutinychat/backend/participant_auth.py:13) defines protocol version 3.
Invitations bind:
•	Protocol version
•	v3 onion address
•	Host ephemeral public key
The handshake in [`_perform_handshake()` (line 568)](D:/From Mac Desktop/GitHub/mutinychat/backend/main.py:568) exchanges role-tagged keys and fresh nonces, derives a transcript containing the onion, roles, keys, and nonces, and performs mutual encrypted challenge-response. Only then does it install the Box, set the channel to confirmed, and expose the safety code.
Manual verification uses encrypted, role- and transcript-bound confirmation payloads. Messaging is rejected on both send and receive until both confirmations are complete.
Messaging and polling
Peer messages are bounded to 16 KiB UTF-8. Frames, rate, queue count, queue bytes, poll batches, poll bytes, and rendered history are bounded.
The backend emits typed chat and control events, but connection-failure messages are still incorrectly emitted as chat events. The frontend only adds local bubbles after status: sent, but clears the draft regardless of send success.
Cleanup
Python close_room() closes sockets, listener, onion service, Tor controller/process, temporary Tor directory, cryptographic state, and queued events. Many failures are swallowed and the function always returns {"status":"closed"}.
Rust attempts graceful close and then kills the backend if necessary. Its application-exit callback silently returns when the session mutex is busy.
Packaging and CI
The Windows workflow builds:
•	Frontend
•	Python sidecar
•	Verified Tor runtime
•	Rust/Tauri application
•	NSIS and optional MSI
•	Portable ZIP
•	Checksums and optional provenance attestations
Release creation is manual, tag-bound, attested, and draft-only. Dependencies and GitHub Actions are strongly pinned. However, the latest Windows build did not progress past Python setup.
4. Alignment with project documents
Authority	Assessment	Evidence
VISION.md	Partial alignment	The narrow two-person Tor/E2EE product exists, but “a failed operation must not leave the interface claiming success” is contradicted by close-room handling. See [VISION.md (line 123)](D:/From Mac Desktop/GitHub/mutinychat/VISION.md:123) and [`closeRoomFromFrontend()` (line 259)](D:/From Mac Desktop/GitHub/mutinychat/src/App.svelte:259).
DESIGN_SYSTEM.md	Partial alignment with clear contradictions	The retro visual personality is present. Channel/Tor/verification wording is materially improved. Contradictions remain: backend controls are primary UI, failed sends erase drafts, system errors look like peer messages, modals lack required focus handling, and emoji are used for core state despite the design warning. See [DESIGN_SYSTEM.md (line 578)](D:/From Mac Desktop/GitHub/mutinychat/DESIGN_SYSTEM.md:578), [DESIGN_SYSTEM.md (line 594)](D:/From Mac Desktop/GitHub/mutinychat/DESIGN_SYSTEM.md:594), and [DESIGN_SYSTEM.md (line 1062)](D:/From Mac Desktop/GitHub/mutinychat/DESIGN_SYSTEM.md:1062).
MVP.md	Partial alignment; release boundary unmet	Cryptographic confirmation, safety-code gating, queue limits, restrictive CSP, local assets, and Windows packaging code exist. Atomic room creation, authoritative close, frontend interaction tests, current Windows packaging, clean-machine validation, and two-installation Tor validation do not. See [MVP.md (line 89)](D:/From Mac Desktop/GitHub/mutinychat/MVP.md:89), [MVP.md (line 154)](D:/From Mac Desktop/GitHub/mutinychat/MVP.md:154), and [MVP.md (line 331)](D:/From Mac Desktop/GitHub/mutinychat/MVP.md:331).
PROJECT_RULES.md	Strong security-core alignment, multiple lifecycle/process contradictions	One shared handshake, backend authority, no blind replay, bounded messaging, pinning, and CSP align. Tracked build outputs, silent room replacement, conflicting operations, unbounded IPC inputs, cleanup skipped on mutex contention, and developer UI conflict directly with the rules. See [PROJECT_RULES.md (line 433)](D:/From Mac Desktop/GitHub/mutinychat/PROJECT_RULES.md:433), [PROJECT_RULES.md (line 447)](D:/From Mac Desktop/GitHub/mutinychat/PROJECT_RULES.md:447), [PROJECT_RULES.md (line 453)](D:/From Mac Desktop/GitHub/mutinychat/PROJECT_RULES.md:453), and [PROJECT_RULES.md (line 498)](D:/From Mac Desktop/GitHub/mutinychat/PROJECT_RULES.md:498).
A governance contradiction also exists: all five authority documents are ignored and untracked, while PROJECT_RULES.md requires clean-clone contributors and agents to read them.
5. Implementation-plan status matrix
Plan item	Status	Evidence and remaining work	Disposition / dependencies
Phase 1 — Freeze scope	MOSTLY COMPLETE	The four authority documents agree; README still advertises “Windows and macOS packaging work.”	Retain; revise README and decide how authority docs are distributed.
2.1 Remove tracked artifacts	NOT STARTED	41 tracked files, 47.35 MB, remain under ignored backend/build and backend/dist.	Retain unchanged; depends only on restoring a usable Windows check.
2.2 Defer macOS	PARTIAL	README calls other platforms unsupported, but macOS spec, build/test scripts, binaries, and package scripts remain.	Retain and remove stale packaging surface.
2.3 Remove developer UI	NOT STARTED	Backend panel, Start Tor, Ping, raw status, and development empty-state copy remain in App.svelte.	Retain; split from artifact deletion for reviewability.
2.4 Remove obsolete paths	PARTIAL	Shared main.py and one invitation parser exist; _extract_onion_host, _room_onion_address, sendToBackend, and starter assets are dead.	Retain. Preserve explicit v2 rejection messages.
2.5 Unsupported-platform signals	PARTIAL	macOS helper silently exits successfully without building; mobile annotation and all-target bundling remain.	Retain; remove or make clearly non-release.
3.1 Atomic creation	NOT STARTED	create_room and start_listening remain separate operations.	Retain as a dedicated security/lifecycle PR.
3.2 Authoritative close	NOT STARTED	Frontend clears state after any close result; Python always returns closed.	Retain but explicitly require Python cleanup outcome reporting.
3.3 Conflicting operations	PARTIAL	Individual create/join booleans exist; no single operation state or cross-operation exclusion exists.	Retain; coordinate with 3.1/3.2.
3.4 Explicit room replacement	NOT STARTED	Backend create and valid join silently call close_room().	Retain; backend rejection is required in addition to disabled buttons.
3.5 Application exit	PARTIAL	Rust has bounded graceful/forced shutdown, but exit silently skips when the mutex is busy.	Retain; add contention and real-child tests.
4.1 Typed system events	PARTIAL	Control events are typed, but connection failures are queued as chat.	Retain; extend event model rather than replacing it.
4.2 Preserve drafts	PARTIAL	Local bubble waits for backend success; draft still clears after failure and duplicate sends are not locked.	Retain.
4.3 Input limits	PARTIAL	Chat, invite, peer-frame, queues, and username control are bounded. Room name, IPC command, total IPC payload, backend input line, and strict field handling are incomplete.	Retain; split UI/IPC and protocol parser work if needed.
5.1 Backend state authority	PARTIAL	Tor, peer count, channel, and verification are polled. Room mode, listener status, operation status, and sanitized error code are absent.	Retain after lifecycle operations are repaired.
5.2 Remove placeholders	NOT STARTED	sunset-chat-394 remains default and is not replaced for guests.	Retain; small UI cleanup.
5.3 Progress phases	PARTIAL	Generic statuses exist, but no backend-authored phase model exists.	Retain after atomic operations establish real phases.
5.4 User-facing copy	PARTIAL	Security copy is improved; raw backend errors, developer wording, and diagnostics remain.	Retain.
Phase 6 — Accessibility	PARTIAL	Labels, native controls, wrapping, and some live regions exist. Focus trap, focus return, Escape, reduced motion, operation-safe dismissal, and global focus-visible behavior are absent.	Retain as a focused post-lifecycle PR.
7.1 Frontend interaction tests	NOT STARTED	Tests cover pure helpers only; App.svelte is not rendered and Tauri invoke is not mocked through workflows.	Retain; prerequisite for claiming lifecycle repairs complete.
7.2 Backend tests	MOSTLY COMPLETE	Strong coverage exists for handshake, replay, ownership, queues, rate, Tor liveness, and verification. Atomic creation, strict inputs, cleanup outcomes, and typed system events remain.	Retain the missing cases only.
7.3 Rust IPC tests	PARTIAL	Timeout, output bounds, no replay, and graceful close are tested. Busy exit, payload rejection, forced child termination, and child cleanup are not.	Retain.
7.4 Packaging checks	BLOCKED	Workflow contains most checks but currently fails at Python setup; it also omits check:tauri-csp and rendered interaction tests.	Revise and restore green before other PRs depend on it.
Phase 8 — Documentation	PARTIAL	README is candid about many limitations, but macOS/MSI wording conflicts with the MVP and no license file accompanies the MIT claim.	Retain; update alongside behavioral changes.
Phase 9 — Manual validation	NOT STARTED	No recorded clean-machine or real two-installation result was found.	Retain exactly; perform only after a green current package.
Phase 10 — Release decision	BLOCKED	Windows packaging, manual tests, artifact cleanup, and lifecycle fixes remain.	Retain.
Plan work order	NEEDS REVISION	It omits the already-failing Windows Python pin, so every release-relevant PR would begin with a known red job.	Add a preliminary build-gate repair before artifact removal.
6. Confirmed remaining findings
MR-01 — P1 — Build/release — Confirmed
•	Location: [`PYTHON_VERSION` (line 33)](D:/From Mac Desktop/GitHub/mutinychat/.github/workflows/windows-release.yml:33) and Windows setup-python at [line 117 (line 117)](D:/From Mac Desktop/GitHub/mutinychat/.github/workflows/windows-release.yml:117).
•	Problem: Python 3.12.13 is pinned, but that exact build was unavailable for windows-2022.
•	Failure: The latest Windows job stopped before backend installation, sidecar compilation, Tor verification, Rust checks, installers, portable ZIP, or launch testing.
•	Impact/blocker: Blocks controlled package evidence, clean-machine testing, MVP completion, beta, and release.
•	Smallest repair: Select one exact Python 3.12 patch available on both supported CI runners and keep CI/release pins consistent.
•	Tests: Full Windows workflow; backend installation with --require-hashes; sidecar CLI/stdio smoke tests; installer and portable verification.
•	Dependencies: None. This is the prerequisite for subsequent repair PRs.
MR-02 — P1 — Repository hygiene/provenance — Confirmed
•	Location: [backend/build](D:/From Mac Desktop/GitHub/mutinychat/backend/build) and [backend/dist](D:/From Mac Desktop/GitHub/mutinychat/backend/dist); both are already ignored at [.gitignore lines 18–19 (line 18)](D:/From Mac Desktop/GitHub/mutinychat/.gitignore:18).
•	Problem: Git still tracks 41 generated PyInstaller reports, archives, bytecode, packages, and two compiled macOS executables totaling about 47.35 MB.
•	Failure: Clean clones contain stale binaries and build products unrelated to the reviewed source.
•	Impact/blocker: Violates repository and MVP completion rules, weakens source-to-binary clarity, and creates unsupported-platform packaging risk.
•	Smallest repair: Remove generated files from Git, retain ignore rules, and add a CI check rejecting tracked artifacts/binaries in forbidden paths.
•	Tests: git ls-files forbidden-path check; clean-clone Windows sidecar build; package-content verification.
•	Dependencies: MR-01 so the cleanup PR can obtain a meaningful green Windows check.
MR-03 — P1 — Lifecycle/state truth — Confirmed
•	Location: [`create_hidden_service()` (line 1172)](D:/From Mac Desktop/GitHub/mutinychat/backend/main.py:1172), [`start_listening()` (line 1185)](D:/From Mac Desktop/GitHub/mutinychat/backend/main.py:1185), [`build_room_response()` (line 1397)](D:/From Mac Desktop/GitHub/mutinychat/backend/main.py:1397), [`createRoomFromFrontend()` (line 307)](D:/From Mac Desktop/GitHub/mutinychat/src/App.svelte:307), and [`poll_messages()` (line 1422)](D:/From Mac Desktop/GitHub/mutinychat/backend/main.py:1422).
•	Problem: Onion creation and listener startup are separate commands. The backend exposes room metadata and invitation before listener success. tor_route_active does not require a live listener.
•	Failure: A listener bind/thread failure leaves a hidden service and room state active while the UI reports only “could not create room”; a poll can call it “Room via Tor.”
•	Impact/blocker: Privacy-state and room-readiness integrity; blocks trustworthy controlled testing and MVP completion.
•	Smallest repair: One backend create transaction that binds the listener first, creates the onion mapping, starts/verifies the listener, and returns the invitation only after full success. Roll back every partial resource on failure.
•	Tests: Bind failure, listener-thread failure, onion publication failure, rollback, no invitation on failure, and tor_route_active requiring listener ownership.
•	Dependencies: MR-05’s active-room guard should be designed at the same boundary.
MR-04 — P1 — Closure/cleanup truth — Confirmed
•	Location: [`closeRoomFromFrontend()` (line 259)](D:/From Mac Desktop/GitHub/mutinychat/src/App.svelte:259), [`close_room()` (line 1343)](D:/From Mac Desktop/GitHub/mutinychat/backend/main.py:1343), and Rust busy handling in [`run_backend_command()` (line 396)](D:/From Mac Desktop/GitHub/mutinychat/src-tauri/src/lib.rs:396).
•	Problem: The frontend clears all state and sets “Room closed” even if invoke failed. Python suppresses removal, controller, process, and filesystem errors and always reports closed.
•	Failure: Clicking Close during a busy create/join can return a Rust busy error while the UI returns to the lobby and the backend operation continues. Tor or a room may remain active behind a false success state.
•	Impact/blocker: Privacy, connection integrity, cleanup reliability, and user trust; blocks MVP completion.
•	Smallest repair: Introduce explicit closing, closed, and close_failed/uncertain states. Return a structured backend cleanup result; accept closure only after authoritative empty state or confirmed backend termination.
•	Tests: Close success, backend busy, lost response, Tor removal failure, process termination failure, close during start/create/join, repeated Close.
•	Dependencies: MR-03 and MR-05 operation ownership; MR-06 Rust exit handling.
MR-05 — P1 — Operation ownership/room replacement — Confirmed
•	Location: close_room() at the start of [`build_room_response()` (line 1397)](D:/From Mac Desktop/GitHub/mutinychat/backend/main.py:1397) and valid [`join_room()` (line 1218)](D:/From Mac Desktop/GitHub/mutinychat/backend/main.py:1218); independent frontend flags at [App.svelte lines 49–50 (line 49)](D:/From Mac Desktop/GitHub/mutinychat/src/App.svelte:49).
•	Problem: Creating or validly joining a new room silently closes the current one. Create, Join, Close, Start Tor, and Ping lack a shared operation lock.
•	Failure: A user can replace an active room or race lifecycle commands without a deliberate close transition.
•	Impact/blocker: Conversation availability and lifecycle predictability; blocks MVP completion.
•	Smallest repair: Backend rejects create/join while a room or lifecycle operation is active. Frontend uses one operation enum and disables every conflicting control.
•	Tests: Create-vs-join, double create, double join, active-room replacement, close-vs-create, and backend enforcement when frontend controls are bypassed.
•	Dependencies: MR-03 and MR-04.
MR-06 — P1 — Process cleanup — Likely
•	Location: [`stop_backend_session()` (line 288)](D:/From Mac Desktop/GitHub/mutinychat/src-tauri/src/lib.rs:288) returns immediately on TryLockError::WouldBlock; it is called during app exit.
•	Problem: The normal Rust shutdown coordinator can be skipped while another command holds the backend-session mutex.
•	Failure: Parent exit may leave cleanup to pipe closure, Python finalization, Tor ownership, or OS process cleanup rather than the bounded Rust shutdown path.
•	Impact/blocker: Shutdown privacy and process hygiene; blocks release until tested.
•	Smallest repair: Add bounded lock acquisition/cancellation and guaranteed child termination after the wait. Do not block application exit indefinitely.
•	Tests: Exit while idle, polling, Tor startup, create, join, and a deliberately stuck command; assert child termination.
•	Dependencies: MR-04’s authoritative shutdown state.
MR-07 — P1 — Messaging reliability — Confirmed
•	Location: [`sendMessage()` (line 169)](D:/From Mac Desktop/GitHub/mutinychat/src/App.svelte:169), with unconditional draft clearing at [line 204 (line 204)](D:/From Mac Desktop/GitHub/mutinychat/src/App.svelte:204).
•	Problem: The draft is cleared after success, backend-declared failure, JSON failure, or IPC exception.
•	Failure: Users lose unsent text during ordinary network/backend failure.
•	Impact/blocker: Core message reliability and explicit MVP acceptance criteria.
•	Smallest repair: Clear only after status === "sent" and add an isSending guard.
•	Tests: Successful send, backend error, busy IPC, timeout/lost response, duplicate submit, and draft retained byte-for-byte on failure.
•	Dependencies: Frontend interaction-test harness from MR-09.
MR-08 — P1 — Release gating — Confirmed
•	Location: Windows workflow triggers at [lines 3–24 (line 3)](D:/From Mac Desktop/GitHub/mutinychat/.github/workflows/windows-release.yml:3); CSP is checked only by [CI (line 40)](D:/From Mac Desktop/GitHub/mutinychat/.github/workflows/ci.yml:40).
•	Problem: The Windows job runs for selected PR paths or manual dispatch, not on merged main. PR 19’s Windows job failed but was nevertheless merged. The release workflow also omits its own CSP check.
•	Failure: Exact default-branch code can be green in normal CI without current Windows package evidence.
•	Impact/blocker: Packaging and release trust; blocks beta/release.
•	Smallest repair: Make the Windows build a required merge check for release-relevant changes, rerun on main or require a successful exact-commit/manual release-candidate run, and add CSP validation.
•	Tests: Demonstrate a successful exact-commit Windows run and verify required-check configuration separately.
•	Dependencies: MR-01 first; MR-09 before release readiness.
MR-09 — P1 — Test coverage/evidence — Confirmed
•	Location: [`test:frontend` (line 16)](D:/From Mac Desktop/GitHub/mutinychat/package.json:16) runs plain Node helper tests only; App.svelte lifecycle handlers are unrendered.
•	Problem: No component test exercises actual buttons, modal state, mocked Tauri IPC, polling, draft preservation, or lifecycle conflicts.
•	Failure: Pure mapping tests can pass while the integrated frontend still falsely reports close success or loses drafts.
•	Impact/blocker: Blocks MVP completion and trustworthy Windows validation.
•	Smallest repair: Add a small rendered-component test harness with mocked invoke; do not introduce a full browser E2E framework unless necessary.
•	Tests: The scenarios already listed in implementation-plan section 7.1.
•	Dependencies: Introduce the harness alongside the first frontend lifecycle fix, not as a separate speculative framework project.
MR-10 — P2 — Event/UI integrity — Confirmed
•	Location: Error handling in [`_read_socket_messages()` (line 977)](D:/From Mac Desktop/GitHub/mutinychat/backend/main.py:977) queues “Secure connection closed” as chat at [lines 1030–1032 (line 1030)](D:/From Mac Desktop/GitHub/mutinychat/backend/main.py:1030); failed host handshakes do the same at [line 1058 (line 1058)](D:/From Mac Desktop/GitHub/mutinychat/backend/main.py:1058).
•	Problem: Locally generated system failures and peer-supplied error text enter the same frontend type as peer chat.
•	Failure: A connection error appears under the peer’s name and visual bubble style.
•	Impact/blocker: Conversation/UI integrity; important but not equivalent to the previously fixed control-message impersonation.
•	Smallest repair: Add typed system/warning/error events with stable sanitized codes and distinct rendering.
•	Tests: Peer error frame, malformed ciphertext, rate limit, handshake failure, and proof that none render as peer chat.
•	Dependencies: MR-09.
MR-11 — P2 — IPC/input boundaries — Confirmed
•	Location: [`backend_ipc` (line 298)](D:/From Mac Desktop/GitHub/mutinychat/src-tauri/src/lib.rs:298), [`run_backend_command()` (line 396)](D:/From Mac Desktop/GitHub/mutinychat/src-tauri/src/lib.rs:396), and [`handle_json_command()` (line 1482)](D:/From Mac Desktop/GitHub/mutinychat/backend/main.py:1482).
•	Problem: Rust accepts arbitrary command names and unbounded message/room strings. Python retains unused echo/get_peer_count commands and does not validate friendly room-name size or control characters.
•	Failure: A compromised WebView or erroneous caller can allocate oversized IPC payloads, kill an otherwise healthy backend through oversized responses, or invoke internal commands outside the intended UI.
•	Impact/blocker: Availability, narrow IPC surface, and maintenance.
•	Smallest repair: Rust allowlist plus command-specific request structs and byte limits; matching Python validation before Tor work; frontend maxlength and UTF-8 checks.
•	Tests: Boundary and boundary-plus-one tests for Unicode room names, invites, messages, command names, and aggregate IPC payloads.
•	Dependencies: Coordinate constants with MR-03; no protocol-version change is needed for local IPC limits.
MR-12 — P2 — Protocol strictness — Confirmed behavior; exploitation theoretical
•	Location: JSON parsing in [`_receive_handshake_frame()` (line 468)](D:/From Mac Desktop/GitHub/mutinychat/backend/main.py:468) and [`_process_peer_frame()` (line 932)](D:/From Mac Desktop/GitHub/mutinychat/backend/main.py:932).
•	Problem: Python’s standard JSON loader accepts duplicate keys. Post-handshake verification, message, disconnect, and error frames do not enforce exact field sets.
•	Failure: Malformed or ambiguous frames can be interpreted according to last-key-wins behavior rather than being rejected as required by project rules.
•	Impact/blocker: Protocol clarity, parser consistency, and future interoperability; no direct cryptographic bypass was identified.
•	Smallest repair: Duplicate-key rejecting JSON loader and exact schema validation for every frame type.
•	Tests: Duplicate type, v, role, ciphertext, and unexpected-field cases.
•	Dependencies: Consider whether the stricter parser warrants a protocol version change; rejecting malformed frames should normally remain compatible with valid v3 peers.
MR-13 — P2 — Product-state/copy consistency — Confirmed
•	Location: Default room name at [App.svelte line 36 (line 36)](D:/From Mac Desktop/GitHub/mutinychat/src/App.svelte:36), backend panel at [line 854 (line 854)](D:/From Mac Desktop/GitHub/mutinychat/src/App.svelte:854), and development empty-state copy at [line 998 (line 998)](D:/From Mac Desktop/GitHub/mutinychat/src/App.svelte:998).
•	Problem: Guests retain a fake room name, developer controls occupy primary UI, and raw backend status strings remain user-facing.
•	Failure: The interface looks like a prototype/debug console and can present placeholder metadata as real.
•	Impact/blocker: Trust, product clarity, and design-system compliance.
•	Smallest repair: Neutral inactive room text, remove primary backend controls, and expose only sanitized optional diagnostics.
•	Tests: Host, guest, lobby, failed backend, and no-room presentations.
•	Dependencies: Lifecycle state work should land first.
MR-14 — P2 — Accessibility/interaction — Confirmed
•	Location: Modal markup at [App.svelte line 1053 (line 1053)](D:/From Mac Desktop/GitHub/mutinychat/src/App.svelte:1053) and [line 1085 (line 1085)](D:/From Mac Desktop/GitHub/mutinychat/src/App.svelte:1085).
•	Problem: Dialogs do not set initial focus, trap focus, restore focus, support Escape, or prevent backdrop dismissal during active operations. No reduced-motion rule or global :focus-visible treatment is present.
•	Failure: Keyboard and assistive-technology users can lose navigation context; ongoing operations can be visually dismissed.
•	Impact/blocker: Accessibility and interaction reliability.
•	Smallest repair: Focus-managed modal helper/action, Escape handling, operation-aware dismissal, strong focus styling, and reduced-motion CSS.
•	Tests: Keyboard focus order, Escape, focus restoration, active-operation dismissal, and manual screen-reader/reduced-motion checks.
•	Dependencies: Shared frontend operation state from MR-05.
MR-15 — P2 — Documentation/governance — Confirmed
•	Location: Local .gitignore additions at [line 32 (line 32)](D:/From Mac Desktop/GitHub/mutinychat/.gitignore:32), README’s macOS claim at [line 20 (line 20)](D:/From Mac Desktop/GitHub/mutinychat/README.md:20), optional MSI claim at [line 29 (line 29)](D:/From Mac Desktop/GitHub/mutinychat/README.md:29), and MIT declaration at [line 255 (line 255)](D:/From Mac Desktop/GitHub/mutinychat/README.md:255).
•	Problem: Authority documents are absent from Git and deliberately ignored, although project rules require contributors and agents to read them. README implies macOS packaging and an extra installer outside the MVP. No tracked LICENSE file exists.
•	Failure: Clean clones do not carry the project authority used for review; contributors can unknowingly diverge; distribution terms and platform claims are incomplete.
•	Impact/blocker: Governance, maintenance, and public-release clarity.
•	Smallest repair: Decide whether authority docs must be tracked; align README with Windows-only NSIS/portable scope; add the actual MIT license text if MIT remains intended.
•	Tests: Documentation/link check and clean-clone confirmation that required contributor instructions are available.
•	Dependencies: MR-02’s repository cleanup.
MR-16 — P3 — Dead/obsolete surface — Confirmed
•	Location: [`_room_onion_address()` (line 354)](D:/From Mac Desktop/GitHub/mutinychat/backend/main.py:354), [`_extract_onion_host()` (line 1211)](D:/From Mac Desktop/GitHub/mutinychat/backend/main.py:1211), dead sendToBackend() at [App.svelte line 208 (line 208)](D:/From Mac Desktop/GitHub/mutinychat/src/App.svelte:208), starter SVG files, macOS scripts/spec, and mobile_entry_point.
•	Problem: These paths are unused by the MVP or represent deferred scaffolding.
•	Failure: They add misleading surface and maintenance burden.
•	Impact/blocker: Cleanup only; not a current security vulnerability.
•	Smallest repair: Remove after confirming no supported build references them. Preserve protocol v2 rejection text.
•	Tests: Static reference search and clean Windows build.
•	Dependencies: MR-02.
MR-17 — P3 — Development configuration — Confirmed
•	Location: Vite HMR uses port 1421 at [vite.config.js line 18 (line 18)](D:/From Mac Desktop/GitHub/mutinychat/vite.config.js:18), while development CSP permits WebSocket port 1420 at [tauri.conf.json line 46 (line 46)](D:/From Mac Desktop/GitHub/mutinychat/src-tauri/tauri.conf.json:46).
•	Problem: The configured HMR WebSocket origin is not included in devCsp.
•	Failure: Tauri development hot reload may be blocked by CSP.
•	Impact/blocker: Local developer convenience; production CSP is unaffected.
•	Smallest repair: Align the loopback HMR port and extend the CSP checker to compare configuration.
•	Tests: Tauri dev launch with CSP console inspection; static config test.
•	Dependencies: None.
7. Items already solved
The following work should not be redone:
•	Mutual cryptographic channel confirmation: Transcript-bound encrypted challenge-response, private-key possession, role binding, nonce freshness, replay resistance, reflection rejection, and one-sided timeout handling exist in [`_perform_handshake()` (line 568)](D:/From Mac Desktop/GitHub/mutinychat/backend/main.py:568) and [handshake tests (line 207)](D:/From Mac Desktop/GitHub/mutinychat/backend/test_participant_handshake.py:207).
•	Authenticated invitation and host-key binding: Version 3 invitations require an exact scheme, v3 onion, host key, and canonical encoding in [`parse_invite()` (line 74)](D:/From Mac Desktop/GitHub/mutinychat/backend/participant_auth.py:74). Version 2 fails without downgrade.
•	Session safety code and mutual verification: The code is transcript/session-bound, confirmation frames are encrypted and role-bound, and chat is blocked until both sides confirm. Tests cover reflection and message gating in [test_main.py (line 483)](D:/From Mac Desktop/GitHub/mutinychat/backend/test_main.py:483).
•	Stale connection ownership: Socket-plus-generation ownership prevents old connection threads from clearing or promoting newer sessions. The dedicated race tests are in [test_connection_ownership.py (line 89)](D:/From Mac Desktop/GitHub/mutinychat/backend/test_connection_ownership.py:89).
•	Remote resource exhaustion controls: Peer frames, handshake frames, message bytes, rate, backend queue, poll batch, Rust response lines, request queue, and visible history are bounded. Tests cover these limits in [test_main.py (line 761)](D:/From Mac Desktop/GitHub/mutinychat/backend/test_main.py:761) and [messageHistory.test.js (line 31)](D:/From Mac Desktop/GitHub/mutinychat/tests/frontend/messageHistory.test.js:31).
•	Chat/control namespace separation: Peer plaintext is always a chat event rather than being interpreted as room_deleted or another internal sentinel. Typed control parsing is covered in [frontendEvents.test.js (line 25)](D:/From Mac Desktop/GitHub/mutinychat/tests/frontend/frontendEvents.test.js:25). MR-10 is a narrower remaining system-event classification issue.
•	Restrictive CSP and local runtime assets: Production CSP is local-only and checked by [check-tauri-csp.mjs (line 1)](D:/From Mac Desktop/GitHub/mutinychat/scripts/check-tauri-csp.mjs:1). Retro sounds are generated locally.
•	Tor status improvements: The backend verifies both process and controller liveness, binds room routing to the current Tor generation, uses SAFECOOKIE, loopback ports, and fresh IsolateSOCKSAuth credentials. Relevant tests begin at [test_main.py line 130 (line 130)](D:/From Mac Desktop/GitHub/mutinychat/backend/test_main.py:130).
•	Host connection truthfulness: Peer count advances to two only after handshake success; frontend presentation requires peer count plus confirmed encryption.
•	IPC timeout, output bounding, and no blind replay: Rust stops the uncertain backend session instead of repeating state-changing commands. Tests are embedded in [src-tauri/src/lib.rs (line 469)](D:/From Mac Desktop/GitHub/mutinychat/src-tauri/src/lib.rs:469).
•	Username and clipboard hardening: Username is session-only, legacy persistence is removed, clipboard copying is explicit and warned, and exact-value clearing is attempted after 60 seconds or room close.
•	Dependency/release hardening: Actions are commit-pinned, Python requirements are hash-locked, Cargo/npm locks exist, OSV scanning has expiring exceptions, Tor is signature-verified, tags do not auto-publish, and release creation is draft-only with provenance attestation.
•	Unused privileged/native dependencies removed: The opener plugin/capability and Python cryptography runtime dependency are absent, with packaging regression tests.
These conclusions are supported by source and tests plus the successful exact-HEAD Linux CI run. They are not evidence that a real Tor or packaged Windows session succeeded.
8. Work that should be removed or scaled back
•	Remove all tracked contents of backend/build/ and backend/dist/. Repairing or curating old generated output is less safe than rebuilding it from reviewed source.
•	Remove the macOS PyInstaller spec, helper, packaged test script, package scripts, and tracked binaries from the MVP branch. Platform-neutral code should remain. macOS can return later with a fresh, tested packaging design.
•	Drop optional MSI production scope unless the authority documents are intentionally expanded. NSIS plus portable ZIP already satisfy the defined MVP and reduce packaging/test surface.
•	Remove the permanent Backend/Ping/Start Tor panel. Tor startup should happen through create/join; ping remains useful only as a packaging smoke command.
•	Remove dead sendToBackend, _room_onion_address, _extract_onion_host, unused starter SVGs, and obsolete tests that exist only for those dead helpers.
•	Replace sunset-chat-394 as an application-state default with neutral inactive text. Keep generated names only within the create-room flow.
•	Remove echo and get_peer_count from the production IPC surface if no restrained diagnostics view needs them.
•	Scale README back to Windows-only support. Do not spend time repairing deferred macOS packaging.
•	Do not remove encrypted challenge-response, host-key binding, explicit v2 rejection, verification gating, CSP, Tor isolation, dependency auditing, queue bounds, or connection-generation ownership.
9. Missing work not covered by the implementation plan
The plan is strong but should add:
1.	Restore the currently broken Windows Python pin before Phase 2.
2.	Require successful Windows packaging for release-relevant merges and ensure an exact default-branch/release-tag run exists.
3.	Run CSP validation in the Windows release workflow, not only general CI.
4.	Make Python cleanup outcomes explicit in Phase 3.2; frontend authority is meaningless if the backend always reports closed.
5.	Explicitly reject duplicate JSON keys and extra application-frame fields.
6.	Resolve how authority documents reach clean-clone contributors and Codex sessions.
7.	Add the actual MIT license file if public distribution remains MIT.
8.	Align development HMR and CSP ports.
9.	Define where manual release-candidate results are recorded so future sessions can distinguish evidence from claims.
10. Revised execution order
Phase 0 — Restore the Windows validation gate
•	Goal: Obtain a green, trustworthy Windows build before asking later PRs to satisfy it.
•	Findings: MR-01, part of MR-08.
•	Why now: Every release-relevant change currently inherits a known red Windows job.
•	Areas: Windows and CI workflows; supply-chain checks if required.
•	Acceptance: Exact pinned Python exists on Linux and Windows; full Windows package workflow succeeds.
•	Automated tests: Backend, frontend, Rust, sidecar, Tor verification, installers, portable ZIP, package launch.
•	Manual validation: None beyond inspecting produced Actions artifacts.
•	Do not change: Product code, cryptography, UI, protocol, or dependencies unrelated to the runtime pin.
Phase 1 — Remove unsupported and generated surface
•	Goal: Establish a source-only Windows MVP repository.
•	Findings: MR-02, MR-15, MR-16.
•	Why now: Avoid repairing or testing code and binaries that should not remain.
•	Areas: backend/build, backend/dist, macOS scripts/spec/tests, package scripts, README, optional MSI scope, dead assets/helpers.
•	Acceptance: No tracked build output; no stale macOS package path; Windows build creates every required artifact from source.
•	Automated tests: Forbidden tracked-path check, release-policy checks, full Windows build.
•	Manual validation: Inspect GitHub artifact contents.
•	Do not change: Shared backend behavior or the security protocol.
Phase 2 — Make room ownership and creation atomic
•	Goal: One backend-owned create transaction and explicit active-room rejection.
•	Findings: MR-03, MR-05.
•	Why now: Later UI state and cleanup depend on a coherent room lifecycle.
•	Areas: backend/main.py, backend lifecycle tests, thin frontend create/join calls.
•	Acceptance: No invitation or route-active claim without a live listener; all partial failures roll back; active rooms cannot be silently replaced.
•	Automated tests: Bind/thread/onion failures, replacement attempts, duplicate operations, authoritative snapshot.
•	Manual validation: Simulated Tor unavailable/listener conflict.
•	Do not change: Protocol v3 handshake, safety-code derivation, message framing.
Phase 3 — Make close and application exit authoritative
•	Goal: Truthful closure with bounded forced cleanup.
•	Findings: MR-04, MR-06.
•	Why now: Uses the room ownership model from Phase 2.
•	Areas: Python cleanup result, Rust process manager, frontend close state.
•	Acceptance: UI never reports closed without backend empty state or confirmed process termination; exit cannot skip cleanup because a mutex is busy.
•	Automated tests: Busy/lost close, cleanup failures, lock contention, forced child termination.
•	Manual validation: Task Manager and temporary-directory inspection during normal and interrupted closes.
•	Do not change: Creation UX or messaging protocol.
Phase 4 — Repair message, event, IPC, and protocol integrity
•	Goal: Preserve user content and enforce strict boundaries.
•	Findings: MR-07, MR-10, MR-11, MR-12.
•	Why now: Lifecycle authority is stable enough for error and retry behavior.
•	Areas: Message send handler, typed frontend events, Rust IPC schema, Python validation, peer-frame parser.
•	Acceptance: Failed drafts remain; system events never render as peer chat; all request/frame types have exact limits and schemas.
•	Automated tests: Component send failures, typed errors, IPC boundaries, Unicode limits, duplicate keys, extra fields.
•	Manual validation: Failed send/retry and readable system notices.
•	Do not change: Cryptographic transcript or invitation format unless strict parser compatibility proves a version change necessary.
Phase 5 — Finish authoritative UI and accessibility
•	Goal: Product-facing state that is clear, keyboard accessible, and free of developer scaffolding.
•	Findings: MR-09, MR-13, MR-14, MR-17.
•	Why now: UI should reflect repaired backend operations rather than inventing interim models.
•	Areas: App.svelte, state helpers, rendered interaction tests, CSS, dev CSP.
•	Acceptance: One operation state; accurate phases; neutral placeholders; no primary backend panel; accessible modals; reduced motion.
•	Automated tests: Rendered create/join/verify/send/close/poll scenarios and keyboard modal tests.
•	Manual validation: Keyboard-only flow, screen reader, zoom, reduced motion, minimum window size.
•	Do not change: Overall retro design language or add new product features.
Phase 6 — Close release and documentation gaps
•	Goal: Make CI, packaging, governance, and documentation describe the same product.
•	Findings: Remaining MR-08, MR-09, MR-15.
•	Why now: Documentation and gates should reflect stable final behavior.
•	Areas: Workflows, README, authority-document distribution, LICENSE, validation-record format.
•	Acceptance: All required checks run; Windows is the only claimed MVP platform; clean clones contain or can reliably obtain project instructions.
•	Automated tests: Release policy, CSP, dependency audit, version checks, full Windows package workflow.
•	Manual validation: Artifact review.
•	Do not change: Runtime behavior except defects discovered by final validation.
Phase 7 — Real release-candidate validation
•	Goal: Determine whether the product actually satisfies the MVP promise.
•	Findings: Release evidence portion of MR-09.
•	Why last: Manual results are meaningful only for the final packaged candidate.
•	Areas: Clean Windows VM/machines and recorded validation results.
•	Acceptance: Complete Phase 9 checklist from the implementation plan, including two independent installations and real Tor messaging.
•	Automated tests: Re-run all checks on the exact candidate commit/tag.
•	Manual validation: Installer, portable ZIP, five messages each direction, verification gating, reconnect/new session, shutdown, reboot, uninstall.
•	Do not change: Code during the test. Any discovered defect returns to a new focused repair PR.
11. Recommended pull-request breakdown
Proposed PR	Scope / findings	Dependencies	Required tests	Explicitly out of scope
Restore Windows Python build compatibility	MR-01, prerequisite portion of MR-08	None	Full Windows workflow	Product/runtime changes
Remove tracked build output and defer macOS packaging	MR-02, macOS part of MR-15/MR-16	PR 1	Forbidden-path check, clean Windows package	Backend behavior
Remove developer UI and obsolete MVP scaffolding	MR-13, MR-16, optional MSI cleanup	PR 2	Frontend check/build, reference scan	Visual redesign
Make room creation atomic and reject room replacement	MR-03, MR-05	PR 1; preferably PR 2	Backend rollback/ownership tests, component create tests	Close/exit rewrite
Make room close and backend exit authoritative	MR-04, MR-06	Atomic ownership PR	Rust contention/termination tests, frontend close tests	Messaging protocol
Preserve failed drafts and add typed system events	MR-07, MR-10	Component harness may be introduced here	Rendered send/error tests, backend event tests	IPC redesign
Bound IPC inputs and strictly parse protocol frames	MR-11, MR-12	Atomic room API stable	Rust/Python boundary tests, duplicate-key tests	Cryptographic redesign
Complete authoritative UI interaction and accessibility	MR-09, MR-13, MR-14, MR-17	Lifecycle and message PRs	Full rendered-component suite, keyboard tests	New themes/features
Align release gates, documentation, and licensing	MR-08, MR-15	Behavioral PRs complete	CI policy/CSP/version/audit checks	Runtime feature changes
Record Windows release-candidate validation	Manual evidence gap	All prior PRs	Exact-candidate CI rerun	Fixes discovered during testing; those require separate PRs
12. Recommended first task
The next Codex session should do exactly one task:
Restore Windows Python build compatibility and obtain a green full Windows workflow.
Why first:
•	The latest Windows build is already red.
•	Every later release-relevant PR depends on that job for meaningful validation.
•	It is small, isolated, and does not touch security-sensitive runtime behavior.
It should:
•	Check the setup-python manifest for an exact Python 3.12 patch available on both Ubuntu 22.04 and Windows 2022.
•	Update the Linux and Windows workflow pins consistently.
•	Preserve hash-required Python installation.
•	Run the complete Windows package workflow, not merely backend unit tests.
It must not change:
•	Application code
•	Protocol version or cryptography
•	Dependency versions or hashes unless genuinely required by the selected Python patch
•	UI, packaging scope, or project documentation unrelated to the pin
Acceptance criteria:
•	Supply-chain pin validation passes.
•	Backend requirements install with hashes on both platforms.
•	Linux CI remains green.
•	Windows sidecar builds and passes CLI/stdio smoke tests.
•	Tor verification, Rust checks, NSIS/portable packaging, package verification, and brief launch all complete successfully.
•	The PR remains unmerged until the Windows check is green.
13. MVP readiness verdict
Target	Verdict	Reason
Local development	READY WITH NAMED LIMITATIONS	The source builds and tests successfully in exact-HEAD Linux CI, and the local checkout has dependencies/build output available. Lifecycle truth bugs remain; this review did not launch Tauri or Tor.
Controlled Windows testing	NOT READY	The current Windows workflow is red and room create/close behavior can leave misleading state.
Clean-machine Windows testing	NOT READY	No current package was produced by the latest workflow and no clean-machine result is recorded.
Public beta	NOT READY	P1 lifecycle, packaging, interaction-test, and repository-hygiene findings remain.
Public release	NOT READY	No current green Windows candidate, clean-machine test, real two-installation Tor test, or shutdown-cleanup evidence exists.
Sensitive real-world use	NOT READY	The project remains unaudited, lifecycle truth is incomplete, and packaged real-network behavior is unverified.
macOS or other deferred platforms	NOT READY	Explicitly outside the MVP; existing artifacts/scripts are stale scaffolding, not support evidence.
14. Open questions requiring a project decision
1.	Should the five project-authority documents be version-controlled? They are required reading for contributors and Codex sessions, but the current local .gitignore deliberately excludes them. If they must remain private/local, PROJECT_RULES.md needs an explicit, reliable external distribution mechanism; otherwise clean clones cannot follow the project’s stated engineering authority.

