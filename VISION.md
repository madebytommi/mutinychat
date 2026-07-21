# MutinyChat Vision

## What MutinyChat Is

MutinyChat is a private, direct, temporary chat application inspired by the personality and simplicity of classic internet messengers.

It combines the approachable feel of AOL Instant Messenger, MSN Messenger, and early peer-to-peer software with modern privacy protections:

- End-to-end encrypted conversations
- Direct connections through Tor onion services
- No central chat server
- No required account
- No permanent message history
- Clear participant verification
- A desktop experience that feels friendly rather than clinical

MutinyChat is meant to feel like a small private room shared by two people—not a social network, collaboration platform, or cloud service.

The experience should be understandable to an ordinary person without requiring them to understand Tor, public-key cryptography, ports, servers, or command-line tools.

---

## Why MutinyChat Exists

Modern messaging applications are convenient, but that convenience often depends on centralized accounts, identity systems, cloud storage, metadata collection, phone numbers, analytics, and long-term platform trust.

Privacy-focused tools often move in the opposite direction but can feel intimidating, technical, visually sterile, or difficult to use correctly.

MutinyChat exists between those two extremes.

It should make a genuinely private conversation feel:

- Personal
- Familiar
- Lightweight
- Temporary
- Understandable
- A little nostalgic
- Safe without pretending to be infallible

The goal is not to build the largest messenger.

The goal is to build a small messenger people can understand and trust.

---

## Core Experience

A person opens MutinyChat, chooses a temporary username, and creates a private room.

MutinyChat starts its bundled Tor service, creates an ephemeral onion address, and produces a secure invitation that can be shared with one other person.

The second person opens MutinyChat, enters a temporary username, and joins using that invitation.

Both participants see the same session-specific safety code. They compare it using a separate trusted method, such as a phone call, an in-person conversation, or an already trusted messaging channel.

Only after both people confirm that the code matches does MutinyChat unlock messaging.

The conversation then behaves like a simple classic instant-message window:

- Messages appear immediately
- Both participants can clearly see connection status
- Security and Tor status are stated honestly
- No account or profile is created
- No central server stores the conversation
- Closing the room clears the visible session
- The application shuts down its temporary networking processes

The user should never need to wonder whether a button worked, whether Tor is still starting, whether a peer is actually connected, or whether a conversation has been verified.

---

## The Feeling MutinyChat Should Create

MutinyChat should feel like discovering a lost messenger application from an alternate version of the early internet—one in which privacy, direct connections, and user control became the default.

The interface should feel:

- Warm rather than corporate
- Retro without becoming a parody
- Playful without undermining trust
- Simple without hiding important security information
- Technical enough to be honest, but never overwhelming
- Polished enough to feel intentional rather than experimental

Security information should appear in plain language and only when it helps the user make a decision.

The interface should not resemble a developer console, security dashboard, or enterprise administration panel.

---

## Product Principles

### Privacy should be structural

Privacy should come from how MutinyChat is built, not from a privacy policy or a promise.

The application should avoid central services, tracking, analytics, advertising, unnecessary external requests, persistent accounts, and hidden data collection.

### Security should be truthful

MutinyChat must never claim that a session is encrypted, verified, connected, or routed through Tor unless the application has confirmed that state.

The interface should distinguish clearly between:

- Tor starting
- Tor running
- A room route being active
- A secure channel being established
- A participant being unverified
- A participant being verified

MutinyChat should explain important limitations without burying users in warnings.

### Simplicity is a security feature

Every additional feature creates more state, more attack surface, and more opportunities for confusion.

MutinyChat should prefer a small number of dependable features over a large collection of partially finished ones.

### The user should remain in control

Users should decide when to create a room, when to share an invitation, when to confirm another participant, and when to end the session.

MutinyChat should not silently create accounts, reconnect to people, retain conversations, upload data, or make security decisions on the user’s behalf.

### Failure should be obvious and recoverable

When something fails, the application should say what happened in understandable language and return the user to a safe state.

A failed operation must not leave the interface claiming success.

### Nostalgia should support usability

The retro design is part of MutinyChat’s identity, but clarity, accessibility, and reliability come first.

The application should evoke classic messengers without reproducing their confusing behavior, visual clutter, or insecure assumptions.

---

## Initial Direction

The first complete version of MutinyChat should remain focused on a dependable two-person desktop conversation.

The initial product direction is:

- Desktop-first
- Windows as the primary supported release platform
- One host and one guest
- One active room per application instance
- Temporary usernames
- Authenticated room invitations
- Session-specific participant safety codes
- End-to-end encrypted text messages
- Tor onion-service hosting and joining
- No central server
- No message persistence
- No file transfers
- No voice or video
- No public rooms
- No contact discovery
- No account system
- No analytics or telemetry
- No automatic software updater until update authenticity can be handled correctly

The priority is not adding more features.

The priority is making the existing experience reliable, coherent, polished, and difficult to misuse.

---

## What MutinyChat Is Not

MutinyChat is not intended to be:

- A replacement for every mainstream messenger
- A public social network
- A group collaboration platform
- A permanent archive
- A cloud-storage service
- An anonymous identity system
- A guarantee against a compromised operating system
- A guarantee of real-world identity
- A tool that makes every device or network activity invisible
- A professionally audited security product unless such an audit actually occurs

Tor and encryption improve privacy, but they do not make every threat disappear.

MutinyChat should communicate that honestly without making the product feel frightening or unusable.

---

## Longer-Term Direction

MutinyChat may grow after the core two-person experience is stable and trustworthy.

Possible long-term directions include:

- Reliable Windows, macOS, and Linux releases
- Better accessibility and keyboard navigation
- Easier QR-based invitations
- Optional trusted-contact verification for repeat conversations
- Improved reconnect and recovery behavior
- Optional Tor bridges or pluggable transports
- Multiple visual themes built around classic messenger eras
- Localization
- Carefully designed small-group rooms
- Mobile companion applications
- Reproducible and signed releases
- Independent security review

These are possibilities, not promises.

A feature should be added only when it:

1. Preserves the application’s privacy model
2. Does not make the core experience confusing
3. Can be tested and maintained properly
4. Does not require unnecessary central infrastructure
5. Provides clear value to the people using it

MutinyChat should remain recognizable as a direct, private, temporary messenger even as it grows.

---

## Definition of Success

MutinyChat succeeds when two ordinary people can:

1. Install it without developer tools
2. Create and join a room without technical knowledge
3. Understand whether Tor is working
4. Understand whether their connection is encrypted
5. Verify that they are speaking to the intended person
6. Exchange messages reliably in both directions
7. Close the room and trust that the visible session has ended
8. Understand the application’s limits without reading technical documentation

The application should feel small, focused, trustworthy, and finished.

It does not need to do everything.

It needs to do its chosen job exceptionally well.

---

## Guiding Statement

MutinyChat is a private doorway between two people: direct, temporary, human, and built in the spirit of the internet before every conversation became a platform.
