# MutinyChat MVP Implementation Plan

## Purpose

This plan defines how the current MutinyChat repository will be reduced to a focused MVP and then repaired, tested, and polished.

The objective is not to rewrite the application or weaken its security model.

The objective is to:

1. Remove unsupported, obsolete, and distracting project surface.
2. Freeze the MVP feature set.
3. Repair lifecycle and state-consistency bugs.
4. Improve focused usability.
5. Add tests around the remaining fragile behavior.
6. Produce one dependable Windows release candidate.

---

# Implementation Principles

All work under this plan must follow these principles:

- Preserve the existing privacy and cryptographic protections.
- Prefer removal over adding abstractions.
- Do not add new product features.
- Keep Windows as the sole MVP release platform.
- Do not claim success based only on unit tests.
- Make backend state authoritative.
- Do not allow the frontend to manufacture successful states.
- Every operation must either complete fully or return to a safe, truthful state.
- Avoid central services, accounts, databases, telemetry, and cloud infrastructure.
- Keep the interface friendly and compact.
- Do not turn the application into a technical dashboard.
- Keep changes small, reviewable, and covered by tests.
- Do not merge a repair branch until its automated checks pass.
- Do not create a public release until manual packaged testing passes.

---

# Target End State

At the end of this plan, MutinyChat should contain:

- One supported Windows desktop product
- One shared backend implementation
- One two-person room flow
- One authenticated invitation format
- One security-state model
- One dependable shutdown path
- One clean Windows build pipeline
- Focused tests for the complete user journey
- Documentation that matches the implementation

The repository may retain future-platform planning documents, but it must not retain stale binaries or imply unsupported platforms are ready.

---

# Phase 1 — Freeze the MVP Scope

## Goal

Prevent further feature expansion while the core product is stabilized.

## Actions

- Treat `VISION.md` as the product direction.
- Treat `DESIGN_SYSTEM.md` as the interface source of truth.
- Treat `MVP.md` as the feature boundary.
- Treat `PROJECT_RULES.md` as the implementation authority.
- Reject additions outside the MVP unless they are required to:
  - Fix a bug
  - Fix a security issue
  - Improve accessibility
  - Support testing
  - Support Windows packaging

## Do Not Add

- Accounts
- Contacts
- Group chat
- File transfer
- Media messages
- Message persistence
- Auto-update
- Mobile support
- Browser support
- New themes
- Plugin systems
- Analytics
- Cloud services
- Public room discovery

## Completion Criteria

- The four project documents agree.
- README does not contradict them.
- Future work is clearly marked as deferred.

---

# Phase 2 — Remove and Scale Back

## 2.1 Remove Tracked Build Artifacts

Remove from version control:

- `backend/build/`
- `backend/dist/`
- PyInstaller `.toc` files
- PyInstaller warning reports
- Previously compiled macOS backend binaries
- Duplicate build outputs
- Local developer paths
- Generated caches
- Temporary package contents

Keep appropriate `.gitignore` rules so they are not recommitted.

### Acceptance Criteria

- No compiled backend binary is stored in Git.
- No build report contains a developer’s absolute local path.
- A clean clone builds artifacts from source.
- CI rejects accidentally committed build outputs where practical.

---

## 2.2 Defer macOS Support

For the MVP:

- State that macOS is planned but unsupported.
- Remove or archive stale macOS packaging scripts and specifications that appear production-ready.
- Remove macOS-specific claims from the primary setup and download instructions.
- Do not package a tracked macOS binary.
- Keep platform-neutral application code where practical.

Do not remove future macOS support from the long-term vision.

### Acceptance Criteria

- README identifies Windows as the MVP platform.
- No macOS download or clean-machine support is implied.
- No stale macOS executable can enter a Windows or future macOS package.
- Deferred macOS work is listed separately from MVP work.

---

## 2.3 Remove Developer Scaffolding from the Main Interface

Remove or hide:

- Backend Ping button
- Raw backend response controls
- Unused `sendToBackend` helper
- Developer-oriented empty-state wording
- Permanent diagnostic panel in the main sidebar
- Decorative indicators that resemble security status
- Raw internal error strings shown without translation

Retain a compact optional Diagnostics view only when useful.

Possible diagnostic fields:

- Application version
- Protocol version
- Backend availability
- Tor runtime state
- Sanitized error code

Never expose:

- Private keys
- Public-key material
- Nonces
- Ciphertext
- Message contents
- Full sensitive logs

### Acceptance Criteria

- Normal users see product actions, not backend controls.
- Debug information does not dominate the primary layout.
- Support information remains available in a restrained form.

---

## 2.4 Remove Obsolete Code Paths

Review and remove:

- Loose onion-only invitation parsing
- Obsolete `_extract_onion_host` behavior and tests
- Compatibility wrappers no longer used by packaging
- Dead frontend functions
- Duplicate security-state logic
- Old protocol-version branches no longer needed for safe error reporting
- Comments describing behavior that no longer exists
- Placeholder values that look like real room information

Do not remove compatibility rejection messages when they help users understand that an update is required.

### Acceptance Criteria

- There is one production invitation parser.
- There is one production handshake implementation.
- Windows development, tests, and packaging use the same backend entrypoint.
- Dead code checks or manual searches find no known obsolete path.

---

## 2.5 Simplify Unsupported Platform Signals

Review:

- Tauri mobile entry annotations
- Browser-specific assumptions
- Platform claims in package metadata
- Scripts that silently skip essential builds

Remove or clearly mark unsupported paths.

An essential packaging step must fail rather than silently succeed without producing its artifact.

### Acceptance Criteria

- Unsupported platforms are not presented as working.
- Required build steps fail closed.
- No release can silently reuse a stale binary.

---

# Phase 3 — Fix Release-Blocking Lifecycle Bugs

## 3.1 Make Room Creation Atomic

### Current Risk

Creating the onion service and starting the room listener are separate frontend/backend operations. One can succeed while the other fails.

### Required Behavior

One backend operation must:

1. Validate the room name.
2. Start or verify Tor.
3. Select and bind the local listener.
4. Create the ephemeral onion service pointing to that listener.
5. Start the listener thread.
6. Confirm the listener is alive.
7. Create the authenticated invitation.
8. Return the complete ready state.

If any step fails:

- Close the listener
- Remove the onion service
- Reset room state
- Preserve a usable Tor runtime only when intentionally designed
- Return a typed failure
- Do not expose an invitation

### Acceptance Criteria

- `Room Ready` is impossible without a live listener.
- `tor_route_active` for a host requires a live listener.
- Failure leaves no partial room.
- Automated tests cover listener-bind and thread-start failure.

---

## 3.2 Make Close Room Authoritative

### Current Risk

The frontend can reset itself and say “Room closed” even when the backend never accepted the close command.

### Required Behavior

The frontend should only show a completed close after:

- Backend returns a successful closed state, or
- Rust confirms the backend process was terminated

If the result is uncertain:

- Show a clear shutdown-in-progress or shutdown-uncertain state
- Disable Create and Join
- Poll or restart the backend
- Confirm that peer, room, and Tor state are gone
- Then return to the lobby

### Acceptance Criteria

- Close failure cannot be displayed as success.
- Backend busy state is handled.
- Repeated Close clicks are harmless.
- Closing during Tor startup is tested.
- Closing during room creation is tested.
- Closing during join is tested.

---

## 3.3 Prevent Conflicting Operations

Create a single frontend operation state, such as:

- `idle`
- `starting-tor`
- `creating-room`
- `joining-room`
- `confirming-verification`
- `sending-message`
- `closing-room`

While an operation is active:

- Disable conflicting actions.
- Prevent double clicks.
- Preserve user-entered data.
- Display the current phase.
- Allow only safe cancellation.

### Acceptance Criteria

- Start Tor cannot be submitted twice.
- Create Room cannot be submitted twice.
- Join Room cannot be submitted twice.
- Create and Join cannot run at the same time.
- Close cannot be visually completed while another lifecycle operation is unresolved.

---

## 3.4 Handle Room Replacement Explicitly

Creating or joining another room while one is active must require a deliberate transition.

Preferred MVP behavior:

- Disable Create and Join while a room is active.
- Require the user to close the existing room first.

A confirmation dialog is acceptable, but the simpler MVP behavior is preferred.

### Acceptance Criteria

- An invalid new invitation cannot silently destroy an active chat.
- The user cannot accidentally replace a room.
- Stale metadata from the previous room cannot remain on screen.

---

## 3.5 Coordinate Application Exit

### Required Behavior

When the application exits:

1. Attempt a graceful `close_room`.
2. Wait for a short bounded period.
3. Close backend stdin.
4. Wait for backend exit.
5. Kill the backend if necessary.
6. Ensure child Tor is terminated.
7. Do not block application exit indefinitely.

Rust must not silently skip cleanup merely because the session mutex is temporarily busy.

### Acceptance Criteria

- Exit during idle state leaves no children.
- Exit during Tor startup leaves no children after the bounded timeout.
- Exit while hosting leaves no children.
- Exit while joined leaves no children.
- Tests cover lock contention and forced termination.
- Manual Task Manager validation passes.

---

# Phase 4 — Fix Message and Event Integrity

## 4.1 Add Typed System Events

All frontend timeline entries must be one of:

- Local user message
- Peer message
- Local system notice
- Warning or error
- Security event

Connection failures must not be queued as chat text.

Peer-provided error text must not be displayed as though it came from the peer.

### Acceptance Criteria

- Connection errors use a typed system event.
- System notices have distinct styling.
- Peer messages cannot imitate a system event merely by matching text.
- Tests verify event parsing and rendering.

---

## 4.2 Preserve Failed Message Drafts

Only clear the message draft after the backend returns `status: sent`.

On failure:

- Keep the draft
- Show a short error
- Allow retry after the state recovers

### Acceptance Criteria

- Failed sends never erase the draft.
- Duplicate sends are prevented while a send is in progress.
- The frontend never displays a local bubble before backend send confirmation.

---

## 4.3 Add Practical Input Limits

Apply consistent limits at:

- Frontend controls
- Rust IPC boundary
- Python backend
- Protocol parser

Suggested limits:

- Username: 32 Unicode characters and a reasonable UTF-8 byte limit
- Friendly room name: 80 characters or 128 UTF-8 bytes
- Authenticated invitation: 512 characters
- Chat message: existing 16 KiB UTF-8 limit
- Backend command name: small fixed limit
- General IPC payload: bounded before forwarding to Python

Normalize or reject:

- Empty values
- Control characters
- Newline-heavy names
- Unexpected null bytes
- Excessively long Unicode sequences

Do not unnecessarily restrict ordinary international names.

### Acceptance Criteria

- Oversized input is rejected before expensive Tor operations.
- Frontend and backend agree on limits.
- Error messages state the relevant limit.
- Unicode boundary tests pass.

---

# Phase 5 — Improve Truthful UI State

## 5.1 Use Authoritative Backend State

The frontend should derive state from one backend snapshot wherever possible.

The snapshot should include:

- Tor runtime status
- Room route status
- Room mode
- Listener status
- Peer count
- Channel status
- Encryption status
- Verification status
- Local confirmation
- Peer confirmation
- Sanitized error state
- Protocol version

Frontend actions may show temporary progress, but completed states must come from the backend.

### Acceptance Criteria

- The frontend cannot show `Room via Tor` without an active room route.
- The host cannot show connected before handshake confirmation.
- Verified status disappears immediately when the peer disconnects.
- Backend unavailability fails closed.

---

## 5.2 Replace Fake or Misleading Placeholders

Remove the default room value `sunset-chat-394` from states where no such room exists.

Use neutral text:

- `No active room`
- `Private room`
- `Waiting for room`
- Actual host-provided room name when authoritative

For the guest MVP, either:

- Display `Private room`, or
- Include the friendly display name in the authenticated invitation without treating it as a security property

### Acceptance Criteria

- Guests never see a random room name presented as real.
- Empty states do not look like active state.

---

## 5.3 Show Clear Progress Phases

Use concise phases such as:

- Validating invitation
- Starting Tor
- Creating private room
- Publishing onion service
- Starting room listener
- Connecting through Tor
- Establishing secure channel
- Waiting for participant verification
- Closing room

Do not use fake percentages.

### Acceptance Criteria

- Long operations never leave the user with only an indefinite generic status.
- Error states identify which phase failed.
- Conflicting controls remain disabled during progress.

---

## 5.4 Clean Up User-Facing Copy

Replace development copy such as:

- `Type below to test local send logging`

With product copy such as:

- `No messages yet.`

Avoid exposing:

- Thread names
- Socket errors
- Python exceptions
- Rust errors
- Raw JSON
- Internal paths

Keep sanitized diagnostics available separately.

### Acceptance Criteria

- Main-interface copy follows `DESIGN_SYSTEM.md`.
- Errors provide one useful next action.
- No security theater language is introduced.

---

# Phase 6 — Accessibility and Interaction Polish

## Required Improvements

- Add proper modal focus trapping.
- Return focus after closing a modal.
- Support Escape to close safe dialogs.
- Do not dismiss a modal through the backdrop while an operation is active.
- Add visible global `:focus-visible` styling.
- Respect `prefers-reduced-motion`.
- Ensure state is not communicated by color alone.
- Confirm minimum window layout remains usable.
- Ensure long invitations and messages wrap.
- Make the safety code easy to read and announce.
- Ensure disabled controls explain why the action is unavailable.
- Remove decorative status elements that can be mistaken for real state.

### Acceptance Criteria

- Primary flow can be completed with a keyboard.
- Screen readers receive meaningful status changes.
- Reduced-motion behavior is tested manually.
- Minimum supported window size remains usable.

---

# Phase 7 — Testing Improvements

## 7.1 Frontend Interaction Tests

Add focused rendered-component tests with a mocked Tauri `invoke`.

Required scenarios:

- Successful room creation
- Onion creation succeeds but listener fails
- Close succeeds
- Close returns busy
- Close response is lost
- Join succeeds
- Join fails while no room is active
- Create and Join are blocked during active room
- Double-click prevention
- Backend poll failure
- Peer disconnect
- Verification transition
- Failed send preserves the draft
- System errors render as system notices
- Oversized inputs are rejected

Avoid building a large end-to-end framework when a small component test can prove the behavior.

---

## 7.2 Backend Tests

Required scenarios:

- Atomic room creation rollback
- Listener ownership
- Hidden-service cleanup
- Tor process death
- Host and guest state cleanup
- Malformed frames
- Oversized frames
- Rate limiting
- Queue overflow
- Replay rejection
- Host-key mismatch
- Protocol-version mismatch
- Verification required before messaging
- Reconnection after failed handshake
- Strict input limits
- Typed system-event generation

---

## 7.3 Rust IPC Tests

Required scenarios:

- Backend response timeout
- Bounded output
- Busy request behavior
- No command replay
- Graceful close
- Exit while lock is busy
- Forced backend termination
- Payload-size rejection
- Child process cleanup

---

## 7.4 Packaging Checks

The Windows workflow must verify:

- Frontend checks
- Frontend interaction tests
- Frontend production build
- External-resource scan
- CSP check
- Release-policy check
- Supply-chain pin check
- Dependency audit
- Backend compilation
- Backend tests
- Backend sidecar build
- Backend command and stdio smoke tests
- Tor signature verification
- Rust formatting
- Rust Clippy
- Rust tests
- Installer creation
- Portable package creation
- Required package contents
- Absence of development artifacts
- Brief packaged-app launch
- Artifact checksums

---

# Phase 8 — Documentation Alignment

Review and align:

- `README.md`
- `VISION.md`
- `DESIGN_SYSTEM.md`
- `MVP.md`
- `PROJECT_RULES.md`
- `IMPLEMENTATION_PLAN.md`

## Required Documentation State

The documents must agree that:

- Windows is the MVP platform.
- macOS and other platforms are deferred.
- The app is a two-person messenger.
- Messages are temporary but not securely erased from all memory.
- Safety-code comparison is required.
- The application is not professionally audited.
- Tor use may be visible.
- Unsigned Windows builds may warn.
- CI is not equivalent to a real two-device test.
- No unsupported feature is described as complete.

### Acceptance Criteria

- No contradictory platform claims.
- No outdated protocol description.
- No manual test is called passed without evidence.
- No absolute anonymity or security claim appears.

---

# Phase 9 — Manual Release-Candidate Validation

## Clean-Machine Test

Use a Windows machine or VM without:

- Python
- Tor Browser
- Node.js
- Rust
- Repository checkout

Test both:

- NSIS installer
- Portable ZIP

## Two-Installation Test

Use two independent installations, preferably on separate machines or VMs.

Required flow:

1. Launch both apps.
2. Confirm separate backend processes.
3. Create a room.
4. Join with the authenticated invitation.
5. Confirm both display the same safety code.
6. Attempt to send before verification and confirm it is blocked.
7. Confirm the code on one side only and verify messaging remains blocked.
8. Confirm the code on the second side.
9. Verify both show participant verified for this session.
10. Send at least five messages in each direction.
11. Test long and Unicode messages.
12. Disconnect the guest.
13. Confirm the host updates immediately.
14. Create a fresh session.
15. Confirm the new session has a new safety code.
16. Close both apps.
17. Confirm no backend or Tor processes remain.
18. Confirm normal temporary Tor directories are removed.
19. Relaunch after reboot.
20. Uninstall and inspect ordinary cleanup.

## Negative Tests

Also verify:

- Invalid invitation
- Modified host key
- Unsupported protocol version
- Room no longer available
- Tor unavailable
- Connection timeout
- Closing during startup
- Repeated button clicks
- Oversized room name
- Oversized invitation
- Failed send with draft preservation

---

# Phase 10 — MVP Release Decision

MutinyChat may be called MVP-complete only when:

- All release-blocking findings are fixed.
- Automated validation is green.
- Windows packaging succeeds.
- Clean-machine testing succeeds.
- Real two-installation Tor messaging succeeds.
- Shutdown cleanup succeeds.
- Documentation matches reality.
- No tracked build artifacts remain.
- No unsupported platform is represented as complete.
- Remaining limitations are documented.

A public release should remain a draft until these checks are recorded.

---

# Work Order

Use this order to avoid repairing code that should first be removed:

1. Freeze the MVP boundary.
2. Remove tracked build artifacts.
3. Defer and clean up macOS support.
4. Remove developer UI and obsolete code.
5. Make room creation atomic.
6. Make closure and replacement authoritative.
7. Prevent conflicting operations.
8. Add typed system events and input limits.
9. Improve shutdown coordination.
10. Polish progress, copy, and accessibility.
11. Add focused frontend, backend, and Rust tests.
12. Align documentation.
13. Build a Windows release candidate.
14. Perform clean-machine and two-installation testing.
15. Decide whether the MVP is ready.

---

# Codex Execution Rules

When Codex works from this plan:

- Inspect the relevant code before editing it.
- Work on one phase or tightly related group at a time.
- Use a dedicated branch.
- Keep pull requests narrowly scoped.
- Do not merge automatically.
- Do not publish releases.
- Do not expand the product.
- Do not remove security controls to simplify tests.
- Add a regression test for every fixed bug.
- Report commands and exact results.
- Separate automated proof from manual testing.
- State remaining uncertainty honestly.
- Stop when a requirement conflicts with `VISION.md`, `MVP.md`, `DESIGN_SYSTEM.md`, or `PROJECT_RULES.md`.

---

# Guiding Implementation Statement

Preserve the secure core, remove unsupported surface area, and make every visible state tell the truth.
