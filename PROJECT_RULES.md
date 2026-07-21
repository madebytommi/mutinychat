# MutinyChat Project Rules

## Purpose

This document defines the engineering and implementation rules for MutinyChat.

These rules exist to keep the project:

- Focused
- Private by design
- Secure by default
- Honest about its state
- Understandable
- Testable
- Maintainable
- Small enough to finish

They apply to human contributors, automated coding agents, Codex sessions, pull requests, build scripts, packaging workflows, and documentation changes.

MutinyChat should not become more complicated merely because a more complicated solution is available.

---

# Project Documents

The repository’s planning documents serve different purposes:

- `VISION.md` defines what MutinyChat is and where it may go.
- `DESIGN_SYSTEM.md` defines how the product should look, feel, and communicate.
- `MVP.md` defines what must exist in the first complete release.
- `IMPLEMENTATION_PLAN.md` defines the ordered work required to reach that release.
- `PROJECT_RULES.md` defines how the project must be engineered.

These documents must remain consistent.

When a proposed change conflicts with them, stop and resolve the conflict before implementing the change.

---

# Decision Priority

When requirements compete, use this order:

1. User safety and truthful security state
2. Privacy
3. Correctness
4. Reliability and cleanup
5. Accessibility
6. Simplicity
7. Maintainability
8. Performance
9. Visual polish
10. Feature expansion

A visually cleaner or more convenient behavior must not weaken security, privacy, cleanup, or state accuracy.

---

# Core Product Boundary

The MutinyChat MVP is:

- A Windows desktop application
- For one host and one guest
- With one active room per application instance
- Using an ephemeral Tor onion service
- Using end-to-end encrypted text messages
- Requiring participant safety-code verification
- Without accounts or central chat storage
- Without permanent message history

New work must support that experience.

Do not add unrelated product surface until the MVP is complete and validated.

---

# Explicit Non-Goals

Do not add any of the following during MVP development unless the project documents are intentionally revised first:

- User accounts
- Email or phone-number registration
- Persistent profiles
- Persistent contacts
- Group chat
- Multiple rooms
- File transfers
- Image sharing
- Voice or video
- Read receipts
- Typing indicators
- Message reactions
- Cloud message history
- Public room discovery
- Friend requests
- Push-notification services
- Analytics
- Telemetry
- Advertising
- Remote crash reporting
- Central coordination services
- Browser deployment
- Mobile applications
- Automatic updates
- Plugin systems
- Theme marketplaces
- AI features
- Blockchain or cryptocurrency features

Do not add features merely because mainstream messengers include them.

---

# Supported Platform Rules

## Windows

Windows 10 and Windows 11 on x86-64 are the supported MVP platform.

The supported Windows packages are:

- NSIS installer
- Portable ZIP

The packaged application must run without requiring the user to install:

- Python
- Node.js
- Rust
- Git
- Tor Browser
- Developer tools

## Deferred Platforms

The following are deferred:

- macOS
- Linux
- Android
- iOS
- Standalone browser use

Deferred platform code may remain only when it is:

- Clearly marked as incomplete
- Not packaged as a supported release
- Not dependent on stale tracked binaries
- Not allowed to weaken the Windows implementation

Do not claim platform support until its complete build, packaging, runtime, and cleanup path has been tested.

---

# Architecture Rules

## Approved Architecture

The MVP architecture is:

- Svelte frontend
- Tauri desktop shell
- Rust process and IPC layer
- Python backend
- Bundled Tor runtime
- PyNaCl authenticated encryption
- Direct two-person connection through a Tor onion service

Do not replace this architecture during the MVP polish phase without a documented technical reason and an explicit project decision.

## Architectural Simplicity

Prefer:

- Small modules
- Explicit state
- Clear data structures
- Typed protocol messages
- Direct control flow
- Standard library features
- Existing project dependencies

Avoid:

- Unnecessary service layers
- Dependency-injection frameworks
- Event buses
- Plugin architectures
- Generalized networking frameworks
- Large state-management libraries
- New databases
- Background services
- Microservices
- Premature abstractions

A helper function is preferable to a framework when it solves the problem clearly.

## One Source of Truth

Each important concept should have one authoritative implementation.

There must be:

- One invitation parser
- One handshake protocol
- One security-state model
- One active-room owner
- One backend process manager
- One release version
- One supported packaging path per platform

Do not create parallel implementations that can drift apart.

---

# Security Model Rules

## Security Is Part of the MVP

Do not remove or bypass existing security controls to simplify development.

The MVP must retain:

- Authenticated invitations
- Host-key binding
- Fresh session keys
- Fresh handshake nonces
- Encrypted challenge-response confirmation
- Transcript binding
- Session safety codes
- Mutual verification
- Replay resistance
- Message authentication
- Frame-size limits
- Message-size limits
- Queue limits
- Rate limits
- Restrictive CSP
- Tor stream isolation
- Dependency scanning
- Release provenance checks

Tests must adapt to security controls. Security controls must not be weakened merely to make tests easier.

## No Custom Cryptography

Do not invent:

- Encryption algorithms
- Hash functions
- Key-derivation schemes
- Random-number generators
- Authentication modes
- Message-padding systems

Use established cryptographic libraries and documented primitives.

Any protocol change must clearly document:

- What is changing
- Why it is changing
- Which security property it provides
- Which messages or values it binds
- Whether it changes compatibility
- Whether the protocol version must change

## Protocol Versioning

Change the protocol version when a change affects:

- Invitation format
- Handshake fields
- Cryptographic transcript
- Role handling
- Verification payloads
- Message framing
- Compatibility between peers

Do not silently accept incompatible protocol behavior.

Unsupported protocol versions must fail clearly and safely.

## Participant Authentication

MutinyChat must not claim permanent identity verification.

The application may truthfully report:

- Secure channel confirmed
- Participant unverified
- Participant verified for this session

It must not report:

- Real identity verified
- Trusted contact
- Fully authenticated person

Messaging remains unavailable until both participants confirm the same session safety code.

## Security-State Truthfulness

The interface must never claim:

- Tor is active when Tor is unavailable
- A room is routed through Tor when no current route exists
- A room is ready when the listener is unavailable
- A peer is connected before the handshake completes
- A channel is encrypted before cryptographic confirmation
- A participant is verified before mutual confirmation
- A message was sent before backend confirmation
- A room is closed before cleanup is confirmed

Security state must come from authoritative backend data.

Frontend button clicks are not proof of successful state.

---

# Tor and Networking Rules

## Tor-Only Peer Networking

Peer chat connections must use the bundled Tor runtime.

Do not add:

- Clearnet fallback
- Direct-IP fallback
- WebSocket relay fallback
- Public coordination server
- Automatic proxy bypass

A failed Tor path must fail closed.

## Loopback Binding

Tor control ports, SOCKS ports, local listeners, and internal services must bind only to loopback unless an explicit reviewed change requires otherwise.

Use:

- `127.0.0.1`
- Appropriate loopback-only equivalents

Do not bind internal services to:

- `0.0.0.0`
- Public interfaces
- Local-area-network interfaces

## Tor Authentication and Isolation

Maintain:

- Authenticated Tor control access
- Bundled-Tor path enforcement in packaged builds
- Fresh SOCKS credentials for joined sessions
- Stream isolation where supported
- Ephemeral onion services
- Temporary Tor data directories

Do not depend on an existing Tor Browser installation in packaged releases.

## External Requests

The installed frontend must not load runtime content from:

- CDNs
- Remote font services
- Remote audio services
- Image hosts
- Analytics services
- Tracking services
- Remote JavaScript
- Remote stylesheets
- Remote configuration endpoints

All visual and audio resources must be:

- Local
- Generated locally
- Bundled with the app

Build-time downloads must be:

- Necessary
- Version-pinned
- Integrity-checked
- Separated from runtime behavior

The frontend external-resource scanner must remain enforced.

---

# State Management Rules

## Backend Authority

The Python backend owns authoritative state for:

- Tor runtime
- Room mode
- Onion service
- Listener availability
- Peer connection
- Cryptographic channel
- Verification
- Message delivery
- Room shutdown

The frontend may display temporary progress states, but it must reconcile them with backend truth.

## Explicit States

Do not use vague booleans when a multi-stage operation needs an explicit state.

Prefer values such as:

- `idle`
- `starting`
- `ready`
- `connecting`
- `pending`
- `confirmed`
- `verified`
- `closing`
- `failed`
- `disconnected`

State transitions must be intentional and testable.

## Atomic Operations

Operations that form one user-visible action must succeed or fail together.

Room creation must not expose a ready invitation unless all required parts exist:

- Tor runtime
- Local listener
- Onion service
- Session key
- Authenticated invitation

On failure, partial state must be cleaned up.

## No Silent State Replacement

Do not silently destroy an active room because the user attempted to create or join another one.

The MVP should require the existing room to be closed first.

## Operation Locking

Conflicting operations must not run simultaneously.

Protect at least:

- Starting Tor
- Creating a room
- Joining a room
- Confirming verification
- Sending a message
- Closing a room
- Application shutdown

Buttons and handlers must prevent repeated submission.

Backend and Rust protections must exist even when frontend controls are disabled.

---

# IPC Rules

## Narrow IPC Surface

Expose only the commands required by the product.

Do not expose:

- Arbitrary shell execution
- File-system browsing
- General process launching
- Raw Python evaluation
- Arbitrary backend method invocation
- Unrestricted URLs
- Debug commands in production without a clear reason

Every IPC command must have:

- A known command name
- A defined request shape
- A defined response shape
- Input limits
- Error behavior
- A timeout category

## Bounded IPC

Limit:

- Command-name length
- Message length
- Room-name length
- Invitation length
- Total serialized payload size
- Backend output-line size
- Response wait time
- Request queue depth

Reject oversized input before expensive operations.

## No Blind Replay

Do not automatically repeat a state-changing backend command after an uncertain IPC failure.

Commands such as these must not be blindly retried:

- Create room
- Join room
- Send message
- Confirm verification

When the result is uncertain:

- Stop or reset the backend session
- Obtain a fresh authoritative state
- Tell the user that the operation result could not be confirmed

Idempotent status queries may be retried when safe.

## Sanitized Errors

Frontend errors must be concise and actionable.

Do not expose ordinary users to:

- Python tracebacks
- Rust panic output
- Absolute file paths
- Private keys
- Nonces
- Ciphertext
- Full invitations
- Message content
- Internal environment variables

Detailed errors may be available in a sanitized diagnostics view.

---

# Input Validation Rules

Validate input at every trust boundary:

1. Frontend
2. Rust IPC boundary
3. Python command handler
4. Peer protocol parser

Frontend validation improves usability but does not replace backend validation.

## Required Limits

Use one shared, documented limit for each type of input.

At minimum:

- Username
- Friendly room name
- Invitation
- Chat message
- Peer frame
- Handshake frame
- IPC request
- Backend response
- Frontend event
- Message history

## Unicode

Support normal Unicode text.

Limits that protect memory or protocol size should be measured in UTF-8 bytes where relevant.

Reject or normalize:

- Null bytes
- Unwanted control characters
- Excessive newlines in single-line fields
- Invalid encodings
- Malformed base64
- Noncanonical encoded cryptographic values

Do not reject ordinary international names solely for containing non-ASCII characters.

## Strict Protocol Parsing

Protocol frames should reject:

- Unknown required fields
- Missing required fields
- Duplicate fields where parsing permits them
- Unexpected frame types
- Invalid roles
- Unsupported versions
- Malformed ciphertext
- Oversized values
- Noncanonical encodings

Fail closed on malformed peer input.

---

# Messaging Rules

## Verification Requirement

Chat messages must not be sent or accepted before participant verification is complete.

Enforce this in:

- Frontend controls
- Backend send path
- Backend receive path

## Message Types

Keep these types separate:

- Local user message
- Peer message
- System notice
- Warning
- Error
- Security event

System notices must never appear as though written by the peer.

Peer-provided text must never be interpreted as a local control event.

## Send Confirmation

Do not display a local message bubble until the backend confirms that the frame was sent.

On failed send:

- Preserve the draft
- Show an error
- Allow the user to retry when the session recovers

## Message Persistence

Do not write chat messages to:

- Disk
- Browser local storage
- Databases
- Log files
- Analytics
- Crash reports

Messages may remain temporarily in process memory.

Closing a room clears visible and application-held session state, but documentation must not claim guaranteed secure erasure from memory, swap, or crash dumps.

---

# Logging Rules

## Default Logging

Production logging must be minimal.

Do not log:

- Message plaintext
- Message ciphertext
- Private keys
- Public keys when unnecessary
- Full invitations
- Onion addresses unless specifically required for a temporary diagnostic
- Safety codes
- Handshake nonces
- SOCKS credentials
- Clipboard contents
- Raw protocol frames

## Error Logging

Prefer:

- Stable error categories
- Sanitized descriptions
- Protocol phase
- Application version
- Protocol version

Do not include user secrets in error messages.

## Debugging

Temporary debug logging must be:

- Clearly marked
- Removed before merge
- Disabled in production
- Reviewed for sensitive data

Never commit captured private conversations or live invitations as test fixtures.

---

# Temporary Data and Cleanup Rules

## Runtime Data

Use operating-system temporary or application-specific writable directories for runtime data.

Do not write runtime state into:

- Installation directories
- Source directories
- Bundled resources
- Repository directories

## Shutdown

Normal shutdown should attempt to:

1. Stop messaging
2. Close peer sockets
3. Stop the room listener
4. Remove the ephemeral onion service
5. Close the Tor controller
6. Terminate Tor
7. Remove the temporary Tor directory
8. Stop the backend
9. Clear frontend session state

Shutdown must be bounded. The app must not hang indefinitely.

If graceful shutdown fails, terminate the child process safely.

## Unexpected Exit

Document that unexpected termination may leave temporary operating-system data.

Do not claim secure deletion.

---

# Frontend Rules

## Product Interface

The normal interface must focus on:

- Create Room
- Join Room
- Invitation sharing
- Connection progress
- Participant verification
- Messaging
- Closing the room

Developer controls must not dominate the primary interface.

## Diagnostics

Diagnostics should be:

- Optional
- Compact
- Sanitized
- Clearly separate from the main workflow

Do not expose raw command execution.

## UI Consistency

Follow `DESIGN_SYSTEM.md`.

Do not introduce:

- A conflicting visual theme
- Remote fonts
- Large dashboard-style layouts
- Excessive cards
- Security-theater wording
- Decorative status indicators that resemble real state

## Accessibility

Every user-facing change must preserve:

- Keyboard access
- Visible focus
- Semantic labels
- Screen-reader announcements
- Sufficient contrast
- Reduced-motion behavior
- Safe text wrapping
- Clear disabled states

Do not remove native focus outlines without providing a stronger replacement.

## Forms and Modals

Modals must:

- Move focus inside
- Trap focus where practical
- Support Escape when cancellation is safe
- Return focus after closing
- Prevent duplicate submission
- Avoid backdrop dismissal during active operations

Inputs must have:

- Labels
- Limits
- Validation
- Clear error feedback

---

# Rust and Process-Management Rules

The Rust layer is responsible for:

- Starting the backend
- Resolving packaged resources
- Enforcing bundled executable paths
- Bounding IPC
- Managing command timeouts
- Handling backend failure
- Coordinating shutdown

## Process Rules

- Release builds must use packaged sidecars.
- Debug builds must use a fixed known checkout path.
- Do not search arbitrary working directories for executables.
- Do not fall back to a different Tor executable when bundled Tor is required.
- Do not leave child processes running after normal exit.
- Do not rely solely on frontend unload events for cleanup.

## Mutex and Concurrency Rules

Do not silently skip shutdown because a mutex is busy.

Use:

- Bounded waits
- Explicit cancellation
- Safe forced termination

Avoid holding global locks during unnecessarily long work.

Lock ordering must remain consistent to prevent deadlocks.

---

# Python Backend Rules

The backend must:

- Own authoritative room and security state
- Validate every command
- Validate every peer frame
- Bound all queues and buffers
- Use timeouts for network operations
- Fail closed on cryptographic errors
- Clean up partial operations
- Avoid leaking exceptions directly to users
- Maintain one active peer
- Maintain one active room

## Global State

The current MVP may use process-level state, but changes must:

- Protect shared state with locks
- Avoid stale thread updates
- Use connection ownership or generation identifiers
- Ensure old sessions cannot mutate a newer session
- Clear state consistently

Do not introduce multiple independent sources of room state.

## Threading

Every background thread must have:

- A clear owner
- A clear exit condition
- Bounded blocking operations
- Cleanup behavior
- Protection against stale-session updates

Do not create unbounded threads per attacker-controlled event.

---

# Dependency Rules

## Minimize Dependencies

Before adding a dependency, confirm:

- The existing stack cannot solve the problem simply
- The dependency is maintained
- Its license is compatible
- Its runtime behavior is understood
- It does not introduce remote services
- It does not significantly expand attack surface
- It can be pinned and audited

A dependency must not be added solely to avoid writing a small clear helper.

## Pinning

Release inputs must remain reproducible.

Maintain:

- `package-lock.json`
- `Cargo.lock`
- Hash-locked Python requirements
- Exact runtime versions in CI
- Full commit-SHA GitHub Action pins
- Checksum-pinned external build tools
- Signed or checksum-verified Tor packages

Do not use mutable release dependencies such as:

- Unpinned `latest`
- Floating GitHub Action tags
- Unlocked Python packages
- Implicit `npx` downloads during release builds

## Vulnerability Auditing

Dependency scanning must remain part of:

- Normal CI
- Windows release verification

Exceptions must:

- Name the advisory
- Explain why it is unavoidable or unreachable
- Include an expiration date
- Be revisited before expiration

Do not suppress a fixable advisory merely to make CI pass.

---

# Build and Packaging Rules

## Build from Source

Release artifacts must be built from reviewed source during the release workflow.

Do not package:

- Tracked compiled binaries
- Old local build outputs
- Cached executables of unknown provenance
- Developer virtual environments
- Repository build directories

Essential build steps must fail closed.

Do not silently skip a required build and continue packaging.

## Repository Hygiene

Do not commit:

- `backend/build/`
- `backend/dist/`
- PyInstaller temporary files
- Virtual environments
- Tor archives
- Extracted Tor runtime files
- Installer outputs
- Portable ZIP outputs
- Generated target directories
- Local logs
- Absolute developer paths
- Secret files

## Package Verification

Windows packaging must verify:

- Application executable
- Backend executable
- Tor executable
- Required Tor data files
- Installer output
- Portable ZIP contents
- Backend command-line ping
- Backend stdio communication
- Tor version execution
- Absence of development files
- Artifact checksums

A launch smoke test proves only that the process remains open briefly. It does not prove that real Tor messaging works.

---

# Versioning Rules

The application version must match across:

- `package.json`
- `package-lock.json`
- `src-tauri/Cargo.toml`
- `src-tauri/Cargo.lock`
- `src-tauri/tauri.conf.json`

Release tags must match the version exactly:

```text
vX.Y.Z

Do not reuse a version for materially different release artifacts.

Protocol version and application version are separate concepts.

Change the protocol version only when peer compatibility changes.

Release Rules
No Automatic Public Release

A pushed tag must not automatically publish a release.

The release process must require:

Explicit manual workflow dispatch
Existing matching tag
Version validation
Successful automated checks
Artifact checksum verification
Provenance attestation
Draft release creation
Human review before publication
Signing

Unsigned Windows builds must be described honestly.

Do not tell users to disable:

SmartScreen
Defender
Antivirus
Windows security controls

Code signing may be added later, but private signing keys must never be committed to the repository.

Release Claims

Do not call a release verified based solely on CI.

A release candidate must complete:

Clean-machine installation
Two independent app installations
Real Tor room creation and joining
Safety-code comparison
Bidirectional messaging
Disconnect behavior
Shutdown cleanup

Manual results must be recorded accurately.

Testing Rules
Regression Tests

Every confirmed bug fix should include a regression test unless the behavior cannot reasonably be automated.

When automation is impractical, document the manual validation procedure.

Required Test Layers
Frontend

Test:

State presentation
Disabled controls
Create/join/close transitions
Verification flow
Failed sends
System notices
Input limits
Poll failures
Duplicate-operation prevention
Backend

Test:

Invitation parsing
Host-key mismatch
Protocol mismatch
Replay resistance
Challenge-response handshake
Message encryption
Verification gating
Frame limits
Queue limits
Rate limits
Connection ownership
Atomic room rollback
Cleanup
Rust

Test:

Backend startup
IPC bounds
Timeouts
Busy behavior
No unsafe replay
Shutdown while busy
Forced termination
Resource-path resolution
Packaging

Test:

Packaged sidecar
Packaged Tor
Installer output
Portable output
Required files
Development-file exclusion
Brief launch
Test Honesty

Do not describe a manual test as passed unless it was actually performed.

Do not substitute mocks for claims about:

Real Tor connectivity
Clean-machine packaging
Process cleanup
Cross-machine messaging
Runtime network leakage
CI Rules

The default branch must remain protected by automated validation.

Required checks should include:

Frontend type checking
Frontend tests
Frontend production build
External-resource scan
CSP validation
Release-version validation
Supply-chain pin validation
Dependency audit
Python compilation
Backend tests
Rust formatting
Rust Clippy with warnings denied
Rust tests
Windows package build for release-relevant changes

Do not make CI green by:

Disabling tests
Swallowing exit codes
Broadly ignoring warnings
Marking security checks optional
Adding permanent exemptions without explanation
Documentation Rules

Documentation must describe the implementation that exists now.

Do not describe:

Planned features as implemented
Deferred platforms as supported
CI checks as manual verification
Encryption as identity verification
Visible-history clearing as secure deletion
Tor as whole-device anonymity
A launch test as full runtime validation

Security claims must be narrow and supportable.

When implementation changes, update the relevant project documents in the same pull request.

Pull Request Rules

Each pull request should:

Have one clear purpose
Avoid unrelated refactoring
Explain the user-visible effect
Explain security implications
List files changed
List tests added
Report exact validation commands
State what was not tested
Remain unmerged until checks pass

Do not mix:

Security protocol changes
Major UI redesign
Packaging overhaul
New features

into one oversized pull request unless they are technically inseparable.

Coding Agent and Codex Rules

Before changing code, Codex or another coding agent must read:

VISION.md
MVP.md
DESIGN_SYSTEM.md
PROJECT_RULES.md
IMPLEMENTATION_PLAN.md
Relevant source and tests

The agent must not rely solely on an issue description or prior summary.

Required Agent Behavior

The agent must:

Inspect the current default branch
Confirm current implementation before editing
Work from a dedicated branch
Keep changes scoped
Preserve the security model
Add regression tests
Run relevant validation
Report exact results
State uncertainties
Leave the pull request unmerged unless explicitly instructed otherwise
Prohibited Agent Behavior

The agent must not:

Publish a release
Merge automatically
Delete security controls to simplify implementation
Add accounts, servers, databases, telemetry, or analytics
Introduce a large framework without approval
Claim manual testing was performed when it was not
Replace a narrow fix with a broad rewrite
Commit generated binaries
Commit secrets
Disable Windows security
Hide failing checks
Change project scope without calling it out
Stop Conditions

The agent must stop and request direction when:

Project documents conflict
A requested change weakens privacy
A change requires a new central service
A protocol change lacks a clear security design
The change substantially expands MVP scope
Required testing cannot be performed
A release would contain unverified or stale artifacts
A security claim cannot be supported
Code Quality Rules

Prefer code that is:

Clear
Explicit
Small
Bounded
Testable
Easy to remove
Easy to review

Avoid cleverness.

Use comments to explain:

Security boundaries
Non-obvious invariants
Lock ordering
Protocol decisions
Reasons for unusual limits
Why a fallback is intentionally forbidden

Do not use comments to restate obvious code.

Remove unused code, imports, dependencies, and stale comments.

Warnings should be treated as defects unless clearly documented otherwise.

Bug-Fix Rules

When repairing a bug:

Reproduce or clearly identify the failure.
Determine the real source of truth.
Fix the narrowest underlying cause.
Clean up partial state.
Add a regression test.
Validate surrounding state transitions.
Update documentation when behavior changes.
Avoid unrelated modernization.

Do not fix only the visible symptom when the underlying state remains inconsistent.

Security-Review Rules

Security-sensitive changes require extra scrutiny when they affect:

Invitations
Key exchange
Transcript construction
Safety-code derivation
Verification
Message encryption
Tor configuration
Process execution
CSP
Tauri capabilities
IPC
Build dependencies
Release publication
Logging
Clipboard behavior

For these changes, the pull request must state:

Threat being addressed
Security property expected
Failure behavior
Tests proving the behavior
Remaining limitations

Do not call code secure merely because it uses Tor, PyNaCl, CSP, or pinned dependencies.

Definition of Done for a Change

A change is complete only when:

The implementation is present
Relevant tests pass
No unrelated behavior regressed
Error and cleanup paths are handled
Documentation is accurate
CI checks pass
Manual requirements are listed honestly
No generated or sensitive files were committed
The pull request remains within MVP scope

Passing compilation alone is not completion.

Final Engineering Principle

MutinyChat should be engineered as the smallest complete system that can truthfully provide a private, temporary, verified two-person conversation.

Preserve the secure core.

Remove unnecessary surface area.

Make failure safe.

Make every visible state tell the truth.