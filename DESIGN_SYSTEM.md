# MutinyChat Design System

## Purpose

This design system defines how MutinyChat should look, feel, and communicate.

It exists to keep the interface consistent as the application grows and to give designers, developers, and coding agents a shared source of truth.

MutinyChat should feel like a polished messenger from an alternate version of the early internet—familiar, personal, slightly nostalgic, and built around privacy from the beginning.

The design should support trust and clarity without turning the application into a security dashboard.

---

## Design Goals

MutinyChat should feel:

- Warm
- Familiar
- Private
- Direct
- Lightweight
- Calm
- Purposeful
- Slightly nostalgic
- Easy to understand
- Honest about security state

The interface should never feel:

- Corporate
- Clinical
- Sterile
- Aggressively “cyberpunk”
- Like a developer console
- Like a parody of old software
- Crowded with technical status information
- Overloaded with warnings
- Visually chaotic
- Deceptively secure

---

## Core Design Principle

**Classic messenger personality with modern usability and truthful privacy signals.**

Retro styling gives MutinyChat its identity.

Modern interaction design makes it dependable.

Security state must always be accurate.

When these goals conflict, prioritize them in this order:

1. Truthful security state
2. Clear usability
3. Accessibility
4. Reliability
5. Visual nostalgia

---

## Visual Direction

MutinyChat takes inspiration from:

- AOL Instant Messenger
- MSN Messenger
- Windows XP-era desktop applications
- Early peer-to-peer utilities
- Classic buddy lists
- Compact desktop chat windows
- Soft blue desktop interfaces
- Slightly tactile buttons and panels

The goal is not to recreate one historical product exactly.

MutinyChat should feel like an original application that could have existed during that era, but with cleaner spacing, better accessibility, stronger hierarchy, and modern privacy protections.

---

## Overall Aesthetic

The visual style should combine:

- Blue and silver interface surfaces
- Soft gradients
- Light beveled borders
- Compact cards and panels
- Clear status indicators
- Familiar desktop-window structure
- Small amounts of playful retro detail
- Modern spacing and responsive behavior

The interface should feel tactile without becoming heavy.

Use depth sparingly:

- One primary outer-window shadow
- Subtle inset highlights on panels
- Light borders between interface regions
- Minimal decorative layering

Avoid excessive:

- Glow effects
- Neon gradients
- Glassmorphism
- Large rounded cards
- Oversized mobile-style controls
- Fake CRT distortion
- Scanlines over text
- Pixel fonts for body content
- Blinking animations
- Decorative clutter

---

# Color System

## Primary Palette

### Mutiny Blue

The primary brand and action color.

Use for:

- Primary buttons
- Title bars
- Active selections
- Key focus states
- Important links
- Strong visual anchors

Suggested range:

```css
--blue-900: #0b2f6b;
--blue-800: #0f3f9e;
--blue-700: #1454bd;
--blue-600: #256acb;
--blue-500: #3f82d8;
--blue-300: #8bb8ed;
--blue-100: #dceaff;

Window Silver

The primary application surface family.

Use for:

Window chrome
Sidebars
Cards
Toolbars
Form panels
Dividers

Suggested range:

--silver-900: #53647f;
--silver-700: #7d91b0;
--silver-500: #a9bcda;
--silver-300: #c9d8ef;
--silver-200: #dce6f5;
--silver-100: #f3f7fc;
--surface-white: #ffffff;
Background Sky

Use behind the main messenger window.

Suggested treatment:

background:
  linear-gradient(
    180deg,
    #0f3f9d 0%,
    #3f88dd 45%,
    #89baf0 100%
  );

Subtle abstract shapes or gradients may be used, but they must not interfere with readability.

Semantic Colors
Success

Use only for confirmed success.

Examples:

Tor route active
Participant verified
Message sent
Completed action
--success-700: #17633c;
--success-500: #2c8b59;
--success-100: #dcf6e7;
Warning

Use for states requiring user attention but not indicating failure.

Examples:

Participant unverified
Waiting for peer confirmation
Clipboard privacy warning
Tor running without an active room route
--warning-700: #7a5415;
--warning-500: #c28a26;
--warning-100: #fff0c9;
Danger

Use for confirmed failure, loss of connection, or unsafe state.

Examples:

Secure channel failed
Tor unavailable
Invalid invitation
Backend unavailable
--danger-700: #7d2424;
--danger-500: #b84444;
--danger-100: #fde4e4;
Informational

Use for neutral explanations and active progress.

--info-700: #155580;
--info-500: #3687b7;
--info-100: #e1f3fc;
Color Rules
Do not communicate security state by color alone.
Every colored state must include text or a recognizable symbol.
Green must mean something has actually been confirmed.
Red must represent a real failure, not ordinary waiting.
Yellow should indicate caution or unfinished verification.
Blue should represent neutral progress, navigation, or primary action.
Avoid bright red and green combinations without text because of color-vision accessibility.
Maintain readable contrast against every surface.
Typography
Primary Font Stack

Use system fonts that feel appropriate for a desktop messenger and require no network request.

font-family:
  Tahoma,
  "MS Sans Serif",
  Geneva,
  Verdana,
  Arial,
  sans-serif;

Preferred use:

Tahoma for most interface text
Verdana as a readable fallback
System monospace fonts for onion addresses, safety codes, and diagnostic identifiers
font-family:
  "Cascadia Mono",
  "SFMono-Regular",
  Consolas,
  "Liberation Mono",
  monospace;

Do not load remote fonts.

Type Scale

The interface should remain compact but readable.

Suggested scale:

--text-xs: 0.72rem;
--text-sm: 0.82rem;
--text-md: 0.95rem;
--text-lg: 1.1rem;
--text-xl: 1.35rem;
--text-title: 1.55rem;

Use:

text-xs for secondary metadata
text-sm for labels, badges, and status notes
text-md for ordinary interface text
text-lg for section headings
text-xl for major room states
text-title sparingly for empty-state headings
Typography Rules
Use sentence case.
Avoid all-caps labels except where historically appropriate and highly readable.
Do not use pixel fonts for messages, forms, or security information.
Keep line lengths short in warnings and explanations.
Use bold text for hierarchy, not decoration.
Use monospace only for values users may compare or copy.
Safety codes must be large, grouped, and easy to read aloud.

Example:

48291 03754 11826 64073
Layout
Main Window Structure

The desktop application should use a classic messenger-window layout:

Title bar
Status and action toolbar
Left buddy/status sidebar
Main room or conversation area
Message composer
Compact version or build information

The main window should feel like one cohesive application, not a collection of floating cards.

Desktop Layout

Recommended proportions:

Window width: approximately 900–1080px
Window height: approximately 620–760px
Sidebar width: approximately 210–260px
Main conversation area: flexible
Minimum useful size: approximately 550 × 480px

The app should open at a size that displays the entire primary workflow without requiring immediate resizing.

Spacing Scale

Use a restrained spacing system.

--space-1: 0.25rem;
--space-2: 0.5rem;
--space-3: 0.75rem;
--space-4: 1rem;
--space-5: 1.5rem;
--space-6: 2rem;

Rules:

Use compact spacing in controls and toolbars.
Use more breathing room around room creation and verification steps.
Avoid stacking many full-width alert boxes.
Related information should visually group together.
Security explanations should not crowd the chat area.
Responsive Behavior

MutinyChat is desktop-first, but smaller windows must remain usable.

At narrower widths:

Collapse the sidebar into a compact status strip or drawer.
Keep security and Tor state visible.
Allow buttons to wrap.
Avoid horizontal scrolling.
Keep the message composer reachable.
Hide decorative details before hiding functional information.
Do not reduce touch targets below accessible sizes.

Responsive design must not create a second, unrelated visual system.

Window Chrome
Title Bar

The title bar should contain:

MutinyChat name
Encryption status
Tor status
Current room label when useful
Close-room action
Native window controls where applicable

The title bar may use a dark blue gradient with light text.

It should feel like classic desktop software while remaining readable and uncluttered.

Do not show a green system indicator unless it represents a real state.

Decorative indicators must be visually distinguishable from security indicators.

Window Borders

Use:

A dark outer border
A light inner highlight
One soft application shadow
Small border radii, generally 2–4px

Avoid large modern card radii.

The app should feel like a window, not a mobile dashboard.

Components
Buttons
Primary Button

Use for the next safe, recommended action.

Examples:

Create Room
Join Room
Confirm Safety Code
Send

Appearance:

Mutiny blue background
White text
Clear border
Slight vertical gradient allowed
Strong visible focus state
Secondary Button

Use for optional or reversible actions.

Examples:

Cancel
Randomize
Copy Invitation
Test Sounds
Destructive Button

Use for actions that end or discard state.

Examples:

Close Room
Leave Room

Destructive buttons should be visually distinct but not alarmingly large.

Button Rules
Buttons must use action-oriented labels.
Avoid vague labels such as “OK” when a specific action is possible.
Disable buttons during in-flight operations.
Disabled controls must remain readable.
A disabled control should not appear selected or successful.
Do not use buttons as decorative tabs.
Avoid exposing developer actions in the primary interface.
Prevent double submission.

Examples:

Good:

Create Room
Join Room
Start Tor
Compare and Confirm
Leave Room

Avoid:

Execute
Submit
Go
Process
Run Backend Command
Inputs

Inputs should use:

White or near-white background
Dark readable text
Blue focus border
Clear label above the field
Compact but comfortable height
Small border radius

Every input must have:

A visible label
An appropriate maximum length
Clear validation feedback
Safe handling of pasted content
Disabled state when the related operation is in progress

Placeholder text must not replace a label.

Modal Dialogs

Use modals only for focused decisions:

Create Room
Join Room
Confirm leaving an active room
Displaying advanced diagnostics when requested

Modal requirements:

Clear heading
Short explanation
One primary action
One cancel action
Escape-key support
Backdrop dismissal only when safe
Focus moved into the dialog
Focus returned after closing
No hidden operation continuing after cancellation unless clearly stated

Avoid nested modals.

Cards and Panels

Panels should organize related information, not decorate empty space.

Useful panels include:

Identity
Participant status
Sound preferences
Safety-code verification
Room invitation

Avoid turning every line of information into a separate card.

Use border, spacing, and headings before adding more containers.

Buddy List

The buddy-list concept is part of the retro identity, even though the MVP supports only two people.

The sidebar should show:

The current user
The peer or waiting state
Connection state
Verification state

Do not imply that a contact has a persistent account or identity.

Use labels such as:

You
Peer
Waiting for peer
Participant verified

Avoid suggesting permanent contacts until that feature actually exists.

Chat Messages

Message bubbles should be simple and readable.

Local messages:

Right aligned
Mutiny blue or light-blue surface
Clear contrast

Peer messages:

Left aligned
Light neutral surface
Distinct border

System notices:

Centered or full-width
Visually different from chat bubbles
Never presented as though written by the peer

Messages must preserve line breaks where supported and wrap long text safely.

The UI must distinguish:

User-authored messages
Peer-authored messages
Local application notices
Connection errors
Security events

Do not display technical errors as peer chat messages.

Message Composer

The composer should include:

One primary text field
One Send button
Clear disabled state when messaging is unavailable
A concise reason when disabled

Examples:

Verify the safety code before messaging.
Waiting for the secure channel.

Do not allow typing into a composer that cannot possibly send unless the draft will be preserved.

Failed sends must not erase the draft.

Security and Privacy Status Design

Security state is a core part of the interface.

It must be accurate, restrained, and easy to understand.

Security State Model

The interface should distinguish these states:

No Secure Channel

Use when:

No peer is connected
Handshake has not started
Handshake failed
Backend state is unavailable

Suggested label:

No E2EE channel
Securing Channel

Use while:

Onion connection is established
Key exchange is in progress
Cryptographic confirmation is incomplete

Suggested label:

Securing channel…
Encrypted but Unverified

Use after:

The encrypted channel has been confirmed
The participant safety code has not been mutually confirmed

Suggested label:

E2EE channel confirmed
Participant not yet verified
Participant Verified

Use only after:

The secure channel is confirmed
Both participants confirm the same current-session safety code

Suggested label:

Participant verified for this session

Do not shorten this to “Verified identity,” because MutinyChat does not prove a permanent real-world identity.

Security Badge Rules

Badges should:

Use plain language
Reflect authoritative backend state
Change immediately when the state becomes invalid
Include a tooltip or explanation when useful
Avoid absolute claims

Good:

Tor ready
Room via Tor
Securing channel…
E2EE channel confirmed
Participant verified for this session

Avoid:

100% Secure
Anonymous
Untraceable
Identity Verified
Military-Grade Encryption
Completely Private
Tor Status Design

Tor status should describe what the application actually knows.

Tor Off
Tor off
Tor Starting
Tor starting…
Tor Ready

Tor is running, but no current room route has been confirmed.

Tor ready
Room Route Active

The current room’s network route is active through Tor.

Room via Tor
Tor Failed
Tor unavailable

Do not use one generic “Tor” badge for all these conditions.

Do not imply that every operating-system or application network request is automatically proxied through Tor.

Room Creation Flow

The room-creation experience should be linear and obvious.

Recommended sequence:

User chooses or generates a room name.
User selects Create Room.
MutinyChat starts Tor if needed.
MutinyChat creates the onion service and local listener.
The backend confirms that the room is ready.
The invitation and QR code appear.
The host waits for the guest.
The secure channel is established.
Both participants compare the safety code.
Messaging unlocks.

The interface must not display “Room Ready” before the onion service and listener are both available.

Join Flow

Recommended sequence:

User selects Join Room.
User pastes the complete authenticated invitation.
MutinyChat validates the invitation locally.
MutinyChat starts Tor if needed.
MutinyChat connects to the onion service.
The secure channel is established.
The safety code is displayed.
Both participants compare and confirm it.
Messaging unlocks.

Each phase should have a concise visible status.

Example progression:

Validating invitation…
Starting Tor…
Connecting through Tor…
Establishing secure channel…
Ready for participant verification

Avoid showing a single indefinite “Joining…” message for the entire process.

Participant Verification

The verification panel should be prominent but calm.

It should include:

A clear heading
The grouped safety code
A short explanation
Local confirmation state
Peer confirmation state
One confirmation button

Recommended copy:

Compare this code with the other person by voice, in person, or through another trusted channel.

Do not compare it only through the same message that carried the invitation.

Confirmation button:

I compared it and it matches

After local confirmation:

Waiting for the other participant

After both confirmations:

Participant verified for this session

Never auto-confirm.

Never hide the unverified state behind a green encryption badge.

Invitations and QR Codes

The room invitation is a sensitive access capability.

The interface should:

Present the QR code prominently
Offer copying as an explicit action
Warn that clipboard contents may be visible to other apps
Attempt to clear the exact copied value after a short period
State that clipboard history may retain it
Avoid copying automatically
Avoid displaying unnecessary raw cryptographic detail

Recommended notice:

Anyone with this invitation may attempt to join the room. Prefer the QR code when practical.

The full invitation may be displayed in monospace, but should wrap safely and not dominate the screen.

Alerts, Toasts, and System Notices
Toasts

Use for brief, noncritical confirmation.

Examples:

Username updated
Invitation copied
Participant verified
Peer connected

Toasts should disappear automatically and should not contain critical information.

Alerts

Use for problems that require attention.

Examples:

Tor failed to start
Invitation invalid
Secure channel failed
Message could not be sent

Alerts should explain the immediate next action.

System Notices

Use inside the conversation timeline for lifecycle events.

Examples:

Peer joined
Peer disconnected
Room closed
Secure session ended

System notices must not look like peer messages.

Error Writing

Errors should be:

Plainspoken
Specific enough to act on
Short
Non-accusatory
Free of sensitive internal detail

Good:

Tor could not start. Close any other MutinyChat instances and try again.
This invitation is invalid or belongs to an incompatible version of MutinyChat.
The secure connection timed out. The room may no longer be available.

Avoid:

SocketError 10061 in peer_worker thread.
Unknown cryptographic failure.
Something went wrong.

Technical diagnostics may be available in an advanced panel, but should not replace user-facing explanations.

Motion

Motion should be minimal.

Allowed:

Subtle button press
Short modal fade
Gentle status-dot pulse while connecting
Brief toast entrance
Smooth message insertion
Small progress indicator

Avoid:

Constant pulsing after success
Blinking badges
Large loading animations
Decorative movement
Long transitions
Motion that delays interaction

Respect reduced-motion settings.

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
Sound

Retro sounds are optional personality, not essential feedback.

Sound rules:

Generate sounds locally.
Do not download audio at runtime.
Do not use a CDN.
Do not initialize audio until needed.
Respect the user’s sound preference.
Never make chat functionality depend on audio.
Keep sounds short and quiet.
Use different tones for message and peer connection.
Do not play repetitive sounds during connection attempts.
Provide a Test Sounds control in settings or an advanced panel.

Important states must always have visual feedback as well.

Accessibility

MutinyChat should meet modern accessibility expectations despite its retro appearance.

Required Practices
Full keyboard navigation
Visible focus indicators
Semantic headings
Correct form labels
Appropriate button elements
Dialog focus management
aria-live for status changes
Sufficient color contrast
Text alternatives for meaningful icons
No color-only communication
Reduced-motion support
Minimum practical target size of approximately 40 × 40px
Zoom support without breaking layout
Long invitations and messages must wrap
Safety codes must be screen-reader friendly
Focus Style

The focus indicator should be obvious.

Example:

:focus-visible {
  outline: 2px solid #ffd35a;
  outline-offset: 2px;
}

Do not remove outlines without providing a stronger replacement.

Content Style

MutinyChat’s writing voice should be:

Friendly
Direct
Calm
Honest
Human
Reassuring without making promises
Technically accurate without jargon

Use:

Waiting for your peer

Instead of:

Awaiting remote endpoint negotiation

Use:

Compare the safety code before messaging

Instead of:

Complete identity attestation

Avoid fear-heavy language.

The application should help users make good decisions without making ordinary use feel dangerous.

Icons

Use icons only when they improve recognition.

Preferred approach:

Simple local SVG or text symbols
Consistent stroke weight
Small number of meaningful icons
Text labels beside unfamiliar icons

Possible symbols:

Lock for encrypted channel
Shield or onion for Tor routing
Checkmark for completed confirmation
Warning triangle for caution
Broken link or X for failure
Copy symbol for clipboard action
QR symbol for invitation scanning

Do not depend on emoji for core state because rendering differs across platforms.

Emoji may be used sparingly as decorative personality.

Loading and Progress States

Every operation expected to take more than a moment should show progress.

Operations include:

Starting Tor
Creating a room
Publishing an onion service
Joining a room
Securing the channel
Closing a room

During progress:

Disable conflicting actions.
Preserve user input.
Show the current phase.
Prevent duplicate requests.
Allow cancellation only when cleanup can be handled safely.

Avoid fake progress percentages unless the backend provides meaningful progress.

Empty States

Empty states should be welcoming and useful.

Lobby example:

Create a private room or join one with an invitation.

Empty conversation example:

No messages yet.

Waiting example:

Your room is ready. Share the invitation with one person.

Avoid developer-oriented empty-state copy such as:

Type below to test local send logging.
Diagnostics

Diagnostics should be available without dominating the product.

Recommended approach:

Hide advanced information behind a small “Details” or “Diagnostics” action.
Show app version, protocol version, backend status, and sanitized error codes.
Never show private keys, full message contents, encryption nonces, or sensitive logs.
Do not expose Ping and raw backend controls as primary user actions.
Make diagnostic text easy to copy for bug reports.

The normal interface should remain simple.

Platform Consistency

Windows is the primary MVP platform.

Where other platforms are supported:

Preserve the same hierarchy and state language.
Use native window behavior where practical.
Keep the security model identical.
Do not create platform-specific shortcuts that weaken privacy.
Do not claim support until packaging and runtime behavior are tested.

Visual differences caused by native fonts or WebView rendering are acceptable.

Functional and security-state differences are not.

Design Tokens

Recommended base tokens:

:root {
  --color-blue-900: #0b2f6b;
  --color-blue-800: #0f3f9e;
  --color-blue-700: #1454bd;
  --color-blue-600: #256acb;
  --color-blue-300: #8bb8ed;
  --color-blue-100: #dceaff;

  --color-silver-700: #7d91b0;
  --color-silver-500: #a9bcda;
  --color-silver-300: #c9d8ef;
  --color-silver-200: #dce6f5;
  --color-silver-100: #f3f7fc;

  --color-success: #2c8b59;
  --color-warning: #c28a26;
  --color-danger: #b84444;
  --color-info: #3687b7;

  --text-primary: #15233a;
  --text-secondary: #50617a;
  --text-on-dark: #f7fbff;

  --border-dark: #0f2e66;
  --border-medium: #7d96bf;
  --border-light: #d9e4f4;

  --radius-sm: 2px;
  --radius-md: 4px;
  --radius-lg: 6px;

  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-5: 1.5rem;
  --space-6: 2rem;

  --shadow-window: 0 16px 40px rgba(6, 20, 52, 0.42);
  --shadow-inset: inset 1px 1px 0 rgba(255, 255, 255, 0.75);

  --transition-fast: 120ms ease;
  --transition-normal: 180ms ease;
}

These values are a starting point.

Changes should preserve the overall visual identity rather than treating every value as immutable.

Design Do and Don’t
Do
Keep the interface compact and readable.
Show security state honestly.
Preserve user drafts during recoverable failures.
Use typed system notices.
Disable conflicting actions.
Keep retro details subtle.
Use local assets and system fonts.
Make room creation and joining feel linear.
Use clear labels.
Keep the most important action visually obvious.
Don’t
Do not add analytics.
Do not load remote fonts or decorative assets.
Do not use green before a state is confirmed.
Do not call a participant verified before mutual confirmation.
Do not display backend errors as peer messages.
Do not expose raw technical controls in the normal workflow.
Do not create multiple competing status indicators for the same state.
Do not use giant cards and excessive whitespace.
Do not use security theater language.
Do not sacrifice accessibility for nostalgia.
Do not turn MutinyChat into a dashboard.
UI Review Checklist

Before merging a user-interface change, verify:

Does the change match the retro messenger identity?
Is the security state accurate?
Does the interface fail closed?
Are loading and failure states handled?
Are conflicting actions disabled?
Does the operation preserve important user input?
Is keyboard navigation intact?
Is the focus state visible?
Does the layout work at the minimum window size?
Are long values safely wrapped?
Does the change introduce a remote resource?
Does it add unnecessary technical language?
Does it add visual clutter?
Does it create a new state that the backend does not authoritatively report?
Is the behavior tested?
Guiding Design Statement

MutinyChat should look like a beloved classic messenger rebuilt by people who learned from the privacy, accessibility, and usability failures of the old internet.