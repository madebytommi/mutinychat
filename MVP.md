# MutinyChat MVP

## Purpose

This document defines the minimum complete version of MutinyChat.

The MVP is not the smallest possible chat prototype. Privacy, encryption, participant verification, and truthful security state are central to the product and therefore belong in the MVP.

The goal is a focused, dependable Windows desktop application that allows two people to create a temporary private room, verify each other, exchange encrypted text messages through Tor, and cleanly end the session.

The MVP should feel complete within this narrow purpose.

---

## MVP Statement

MutinyChat MVP is a two-person, temporary, end-to-end encrypted desktop messenger that connects participants through an ephemeral Tor onion service without requiring an account or central chat server.

A complete MVP allows two ordinary users to:

1. Install and open MutinyChat on Windows.
2. Choose temporary display names.
3. Create or join a private room.
4. Connect through the bundled Tor runtime.
5. Establish an authenticated encrypted channel.
6. Compare and mutually confirm a session safety code.
7. Exchange text messages in both directions.
8. Clearly understand the current connection and security state.
9. Close the room and stop its temporary networking processes.

---

# Supported Platform

## Primary MVP Platform

The MVP officially supports:

- Windows 10 and Windows 11
- 64-bit Windows systems
- NSIS installer
- Portable ZIP package

The packaged application must include everything required to run:

- MutinyChat desktop application
- Python backend compiled as a self-contained sidecar
- Tor runtime
- Required Tor data files

Users must not need to install:

- Python
- Node.js
- Rust
- Git
- Tor Browser
- Developer tools

## Deferred Platforms

The following are not part of the MVP:

- macOS
- Linux
- Android
- iOS
- Standalone browser deployment

Repository scaffolding for deferred platforms must not be presented as completed support.

---

# Core User Experience

## Creating a Room

The host should be able to:

1. Open MutinyChat.
2. Choose a temporary username.
3. Select **Create Room**.
4. Enter or generate a friendly room name.
5. Wait while MutinyChat starts Tor.
6. Wait while MutinyChat creates:
   - An ephemeral onion service
   - A local room listener
   - An authenticated invitation
7. See a clear **Room Ready** state only after the onion service and listener are both available.
8. Share the invitation by:
   - QR code
   - Explicit clipboard copy
9. Wait for one guest to connect.

Room creation must succeed or fail as one complete operation. A partial room must not be presented as ready.

## Joining a Room

The guest should be able to:

1. Open MutinyChat.
2. Choose a temporary username.
3. Select **Join Room**.
4. Paste the complete authenticated invitation.
5. Wait while MutinyChat:
   - Validates the invitation
   - Starts Tor
   - Connects to the onion service
   - Establishes the encrypted channel
6. See the safety-code verification screen.

The guest must not be shown as connected before the secure handshake completes.

## Participant Verification

After the encrypted channel is established:

1. Both participants see the same session-specific safety code.
2. Both are told to compare it through another trusted method.
3. Each participant explicitly confirms that the code matches.
4. Messaging remains disabled until both confirmations are received.
5. The interface then reports:
   - Encrypted channel confirmed
   - Participant verified for this session

Verification applies only to the current session. It does not establish a permanent identity.

## Messaging

After verification:

- Both participants can send and receive plain text.
- Messages are end-to-end encrypted before crossing the peer connection.
- Messages are displayed only after the backend confirms a successful send.
- Failed sends preserve the unsent draft.
- Peer messages, local messages, and system notices are visually distinct.
- Connection errors must never appear as though they were written by the peer.
- Message length, history, queues, and inbound rate are bounded.

## Ending a Session

The user can select **Close Room** or **Leave Room**.

The application must then:

1. Stop accepting or sending messages.
2. Close peer sockets.
3. Remove the ephemeral onion service.
4. Stop the bundled Tor process.
5. Stop the backend process when the application exits.
6. Clear visible room and message state.
7. Return the interface to a truthful lobby state.

The interface must not claim that the room closed unless backend closure or backend termination has been confirmed.

---

# Included MVP Features

## Privacy and Networking

- No central chat server
- No user account
- No phone number or email requirement
- No contact discovery
- Ephemeral Tor onion-service rooms
- Bundled Tor runtime
- Loopback-only Tor control and SOCKS ports
- Authenticated Tor control access
- Fresh SOCKS credentials for joined sessions
- No analytics or telemetry
- No third-party runtime assets
- No remote fonts, audio, images, scripts, or styles

## Encryption and Verification

- PyNaCl authenticated encryption
- Fresh ephemeral session keys
- Authenticated invitations that bind:
  - Protocol version
  - Onion address
  - Host session public key
- Protocol-version validation
- Encrypted challenge-response handshake
- Fresh connection nonces
- Handshake transcript binding
- Session-specific safety code
- Mutual safety-code confirmation
- Messaging disabled until verification completes
- Replay-resistant session establishment

## Interface

- Retro desktop messenger aesthetic
- Temporary session-only username
- Friendly room name for the host
- Clear create and join flows
- QR invitation
- Explicit invitation-copy action
- Clipboard privacy warning
- Attempted clipboard clearing after a short period
- Accurate Tor status
- Accurate connection status
- Accurate encryption status
- Accurate participant-verification status
- Typed system notices
- Optional locally generated retro sounds
- Accessible keyboard and focus behavior
- Restrained diagnostic information

## Reliability and Safety

- One active room per application instance
- One host and one guest
- Prevention of duplicate or conflicting operations
- Bounded IPC requests and responses
- Bounded peer frames
- Bounded message queues
- Bounded visible history
- Inbound rate limits
- Malformed-message rejection
- Secure failure states
- Normal shutdown cleanup
- Clear recovery after failed create, join, send, or close operations

## Packaging

- Windows NSIS installer
- Windows portable ZIP
- Bundled backend
- Bundled Tor runtime
- Required Tor data files
- Version consistency across manifests
- SHA-256 checksum file
- GitHub build-provenance attestation for tagged artifacts
- Draft-only GitHub release process
- No automatic public release from a pushed tag

---

# Security-State Requirements

The interface must distinguish among:

- Tor off
- Tor starting
- Tor ready
- Room routed through Tor
- No secure channel
- Securing channel
- Secure channel confirmed
- Participant unverified
- Waiting for local or peer confirmation
- Participant verified for this session
- Peer disconnected
- Secure channel failed
- Backend unavailable

A successful-looking state must come from authoritative backend state.

The frontend must not infer success merely because:

- A button was clicked
- A socket was opened
- A public key was received
- Tor started previously
- A room object exists
- A request did not immediately throw an error

---

# Explicit Non-Goals

The following are not part of the MVP:

- Group chat
- Multiple rooms
- Multiple simultaneous peers
- Persistent accounts
- Persistent profiles
- Persistent contacts
- Automatic trusted-contact recognition
- Cloud synchronization
- Stored message history
- Message recovery after closing
- File transfer
- Image sharing
- Voice chat
- Video chat
- Reactions
- Stickers
- Typing indicators
- Read receipts
- Presence across sessions
- Public room discovery
- Friend requests
- Push notifications
- Multiple devices per user
- Automatic reconnect after restarting the app
- Automatic software updates
- Tor bridges
- Pluggable transports
- Mobile apps
- Browser deployment
- Theme marketplace
- Plugin system
- Analytics
- Crash-reporting service
- Central coordination service

Features outside the MVP must not be added merely because they are common in other messengers.

---

# Security Limitations

The MVP must state these limitations honestly:

- MutinyChat has not received an independent professional security audit.
- A safety code proves that both participants see the same current session, not a permanent real-world identity.
- Users must compare the code through a separate trusted channel.
- A compromised operating system may access messages, keys, or clipboard contents.
- Closing a room is not guaranteed secure erasure from memory, swap, or crash dumps.
- Direct Tor use may be visible to the network provider.
- Clipboard history or synchronization may retain copied invitations.
- Unsigned Windows builds may display SmartScreen warnings.
- Tor and encryption do not make the entire device anonymous.

---

# Definition of MVP Complete

MutinyChat is MVP-complete only when all of the following are true.

## Automated Validation

- Frontend type checks pass.
- Frontend production build passes.
- Frontend interaction tests pass.
- External frontend resource scan passes.
- Tauri CSP validation passes.
- Backend unit tests pass.
- Two-process encrypted-session tests pass.
- Invitation-substitution tests pass.
- Replay-resistance tests pass.
- Message and resource-limit tests pass.
- Rust formatting passes.
- Rust Clippy passes with warnings denied.
- Rust tests pass.
- Dependency audit passes.
- Supply-chain pin checks pass.
- Windows installer build passes.
- Portable-package verification passes.
- Packaged application launch test passes.

## Manual Windows Validation

- Install on a clean Windows machine or VM.
- Launch without Python, Tor Browser, Node.js, or Rust installed.
- Confirm offline sound effects work without external requests.
- Create a room.
- Join from a second independent MutinyChat installation.
- Confirm both participants see the same safety code.
- Confirm messaging is disabled before mutual verification.
- Confirm messaging unlocks after mutual verification.
- Exchange at least five messages in each direction.
- Confirm failed sends preserve the draft.
- Disconnect and confirm both interfaces update correctly.
- Create or join another room without restarting the app.
- Close both applications.
- Confirm no MutinyChat backend or Tor process remains.
- Confirm ordinary temporary Tor data is removed after normal shutdown.
- Reboot and launch again.
- Verify installer removal behaves normally.

## Release Boundary

Passing CI alone does not make the MVP complete.

The MVP is complete only after the packaged application passes the real two-installation Tor test and the results are recorded honestly.

---

# MVP Guiding Rule

Do not expand MutinyChat until the complete two-person Windows experience is reliable, understandable, and truthful from launch through shutdown.

The MVP is finished when it performs its narrow purpose exceptionally well—not when it contains the most features.
