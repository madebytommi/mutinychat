<script>
  import { invoke } from "@tauri-apps/api/core";
  import { onMount } from "svelte";
  import packageMetadata from "../package.json";
  import {
    channelBadgeText,
    mapBackendSecurityState,
    peerVerifiedMarkerEffect
  } from "./lib/channelStatus.js";
  import { deriveConnectionPresentation } from "./lib/connectionStatus.js";
  import { isBackendPollBusy } from "./lib/backendPoll.js";
  import {
    appendBoundedMessages,
    MAX_CHAT_MESSAGE_BYTES,
    MAX_POLL_MESSAGES,
    utf8ByteLength
  } from "./lib/messageHistory.js";
  import { FRONTEND_CONTROL_EVENTS, parseFrontendEvent } from "./lib/frontendEvents.js";
  import {
    INVITATION_CLIPBOARD_TTL_MS,
    clearInvitationFromClipboard,
    writeInvitationToClipboard
  } from "./lib/invitationClipboard.js";
  import { clearLegacyUsernamePreference } from "./lib/usernamePrivacy.js";
  import { closeRetroAudio, playRetroTone } from "./lib/retroAudio.js";
  import { mapBackendTorState, torBadgeDescription, torBadgeText } from "./lib/torStatus.js";

  /** @typedef {{ id: number, text: string, isMine: boolean, sender: string }} ChatMessage */

  const APP_VERSION = packageMetadata.version;

  let friendName = $state("Friend Name");
  let myUsername = $state("You");
  let usernameDraft = $state("You");
  let draft = $state("");
  let roomName = $state("sunset-chat-394");
  let onionAddress = $state("");
  let retroSoundsEnabled = $state(true);
  let backendStatus = $state("Idle");
  let currentView = $state("lobby");
  let shareLink = $state("");
  let copyNotice = $state("");
  let qrError = $state("");
  let showCreateModal = $state(false);
  let showJoinModal = $state(false);
  let roomDraftName = $state("");
  let joinLinkDraft = $state("");
  let isGeneratingName = $state(false);
  let isCreatingRoom = $state(false);
  let isJoiningRoom = $state(false);
  let qrCanvas = $state();
  let chatAreaEl = $state();
  /** @type {ChatMessage[]} */
  let messages = $state([]);
  let discardedMessageCount = $state(0);
  let nextMessageId = 1;
  let toastMessage = $state("");
  let toastVisible = $state(false);
  let isEncrypted = $state(false);
  let channelStatus = $state("disconnected");
  let channelError = $state("");
  let torState = $state(mapBackendTorState({ tor_status: "stopped" }));
  let isPeerVerified = $state(false);
  let identityStatus = $state("unavailable");
  let verificationCode = $state("");
  let verificationLocalConfirmed = $state(false);
  let verificationPeerConfirmed = $state(false);
  let peerCount = $state(0);
  let alertMessage = $state("");
  let alertVisible = $state(false);
  let shutdownRequested = $state(false);
  let backendAvailable = $state(true);
  /** @type {number | null} */
  let invitationClipboardTimer = null;
  let copiedInvitation = "";
  /** @type {Promise<boolean>} */
  let invitationClipboardCleanup = Promise.resolve(false);
  let connectionPresentation = $derived(
    deriveConnectionPresentation({
      backendAvailable,
      currentView,
      peerCount,
      channelStatus,
      isEncrypted,
      identityStatus
    })
  );

  const RETRO_SOUND_PREF_KEY = "mutinychat-retro-sounds-enabled";

  /** @param {string} message */
  function showToast(message) {
    toastMessage = message;
    toastVisible = true;
    setTimeout(() => {
      toastVisible = false;
    }, 3000);
  }

  /** @param {string} message */
  function showAlert(message) {
    alertMessage = message;
    alertVisible = true;
    window.setTimeout(() => {
      alertVisible = false;
    }, 3200);
  }

  /** @param {Record<string, unknown> | null | undefined} payload */
  function applySecurityState(payload) {
    const security = mapBackendSecurityState(payload);
    channelStatus = security.channelStatus;
    channelError = security.channelError;
    isEncrypted = security.isEncrypted;
    identityStatus = security.identityStatus;
    isPeerVerified = security.isPeerVerified;
    verificationCode = security.verificationCode;
    verificationLocalConfirmed = security.verificationLocalConfirmed;
    verificationPeerConfirmed = security.verificationPeerConfirmed;
  }

  /** @param {Record<string, unknown> | null | undefined} payload */
  function applyTorState(payload) {
    torState = mapBackendTorState(payload);
  }

  function clearMessageHistory() {
    messages = [];
    discardedMessageCount = 0;
  }

  async function clearCopiedInvitation() {
    if (invitationClipboardTimer !== null && typeof window !== "undefined") {
      window.clearTimeout(invitationClipboardTimer);
      invitationClipboardTimer = null;
    }
    const invitation = copiedInvitation;
    copiedInvitation = "";
    if (!invitation || typeof navigator === "undefined") return invitationClipboardCleanup;
    invitationClipboardCleanup = clearInvitationFromClipboard(navigator.clipboard, invitation);
    return invitationClipboardCleanup;
  }

  /** @param {string} text @param {boolean} isMine @param {string} [sender] */
  function addMessage(text, isMine, sender) {
    const cleanText = String(text).trim();
    if (!cleanText) return false;
    const normalizedSender = (String(sender || (isMine ? myUsername : friendName)).trim() || (isMine ? "You" : "Friend")).slice(0, 80);
    const result = appendBoundedMessages(messages, [
      {
        id: nextMessageId++,
        text: cleanText,
        isMine,
        sender: normalizedSender
      }
    ]);
    messages = result.messages;
    discardedMessageCount += result.removedCount + result.rejectedCount;
    if (result.rejectedCount > 0) return false;

    queueMicrotask(() => {
      if (chatAreaEl) {
        chatAreaEl.scrollTop = chatAreaEl.scrollHeight;
      }
    });
    return true;
  }

  async function sendMessage() {
    if (currentView !== "chat") {
      return;
    }

    if (!isPeerVerified) {
      showAlert("Compare and confirm the safety code before messaging.");
      return;
    }

    const text = draft.trim();
    if (!text) return;
    if (utf8ByteLength(text) > MAX_CHAT_MESSAGE_BYTES) {
      showAlert(`Messages are limited to ${MAX_CHAT_MESSAGE_BYTES / 1024} KiB.`);
      return;
    }

    try {
      const result = await invoke("backend_ipc", {
        command: "send_message",
        message: text,
        roomName: null
      });
      const parsed = JSON.parse(String(result));
      if (parsed.status === "sent") {
        addMessage(text, true);
      } else {
        backendStatus = `Backend error: ${parsed.error || "send failed"}`;
        showAlert("Message failed to send.");
      }
    } catch (error) {
      backendStatus = `Backend error: ${String(error)}`;
      showAlert("Message failed to send.");
    }

    draft = "";
  }

  /** @param {string} message */
  async function sendToBackend(message) {
    try {
      backendStatus = "Contacting backend...";
      const cmd = message ? "echo" : "ping";
      const response = await invoke("backend_ipc", {
        command: cmd,
        message: message || null,
        roomName: null
      });
      backendStatus = "Backend connected";

      addMessage(String(response), false);
    } catch (error) {
      backendStatus = `Backend error: ${String(error)}`;
    }
  }

  async function startTorFromFrontend() {
    try {
      backendStatus = "Starting Tor...";
      torState = { status: "starting", routeActive: false, error: "" };
      const response = await invoke("backend_ipc", {
        command: "start_tor",
        message: null,
        roomName: null
      });
      const parsed = JSON.parse(String(response));
      applyTorState(parsed);
      backendStatus = parsed.tor_status === "ready" ? "Tor ready" : "Tor unavailable";
    } catch (error) {
      backendStatus = `Backend error: ${String(error)}`;
      torState = { status: "failed", routeActive: false, error: String(error) };
      showAlert("Tor failed to start. Try again.");
    }
  }

  async function pingBackend() {
    try {
      backendStatus = "Pinging backend...";
      const response = await invoke("backend_ipc", {
        command: "ping",
        message: null,
        roomName: null
      });
      backendStatus = String(response);
    } catch (error) {
      backendStatus = `Backend error: ${String(error)}`;
      showAlert("Could not ping backend.");
    }
  }

  async function closeRoomFromFrontend() {
    void clearCopiedInvitation();
    try {
      backendStatus = "Closing room...";
      await invoke("backend_ipc", {
        command: "close_room",
        message: null,
        roomName: null
      });
    } catch (error) {
      backendStatus = `Backend error: ${String(error)}`;
    }

    roomName = "sunset-chat-394";
    onionAddress = "";
    friendName = "Friend Name";
    shareLink = "";
    clearMessageHistory();
    draft = "";
    roomDraftName = "";
    copyNotice = "";
    qrError = "";
    showCreateModal = false;
    showJoinModal = false;
    joinLinkDraft = "";
    applySecurityState({ channel_status: "disconnected" });
    applyTorState({ tor_status: "stopped" });
    peerCount = 0;
    shutdownRequested = false;
    currentView = "lobby";
    backendStatus = "Room closed";
  }

  async function requestGracefulShutdown() {
    if (shutdownRequested) return;
    shutdownRequested = true;
    void clearCopiedInvitation();
    try {
      await invoke("backend_ipc", {
        command: "close_room",
        message: null,
        roomName: null
      });
    } catch {
      // Ignore shutdown failures during app close.
    }
  }

  async function createRoomFromFrontend() {
    const finalName = roomDraftName.trim() || roomName;

    try {
      await clearCopiedInvitation();
      isCreatingRoom = true;
      backendStatus = "Creating room...";
      const response = await invoke("backend_ipc", {
        command: "create_room",
        message: null,
        roomName: finalName
      });

      const parsed = JSON.parse(String(response));
      roomName = String(parsed.friendly_name || finalName);
      onionAddress = String(parsed.onion_address || "");
      shareLink = String(parsed.share_link || (onionAddress ? `Join ${roomName} -> ${onionAddress}` : ""));

      await invoke("backend_ipc", {
        command: "start_listening",
        message: null,
        roomName: null
      });

      backendStatus = "Room ready";
      applySecurityState({ channel_status: "disconnected" });
      currentView = "room-ready";
      copyNotice = "";
      showCreateModal = false;
    } catch (error) {
      backendStatus = `Backend error: ${String(error)}`;
      showAlert("Could not create room. Try again.");
    } finally {
      isCreatingRoom = false;
    }
  }

  async function generateRandomRoomName() {
    try {
      isGeneratingName = true;
      backendStatus = "Generating room name...";
      const response = await invoke("backend_ipc", {
        command: "generate_random_room_name",
        message: null,
        roomName: null
      });
      const parsed = JSON.parse(String(response));
      roomDraftName = String(parsed.friendly_name || "");
      backendStatus = "Name ready";
    } catch (error) {
      backendStatus = `Backend error: ${String(error)}`;
      showAlert("Could not generate room name.");
    } finally {
      isGeneratingName = false;
    }
  }

  async function openCreateRoomModal() {
    showCreateModal = true;
    if (!roomDraftName) {
      await generateRandomRoomName();
    }
  }

  function openJoinRoomModal() {
    showJoinModal = true;
  }

  /** @param {string} input */
  function normalizeAuthenticatedInvite(input) {
    const raw = String(input || "").trim();
    if (!raw.toLowerCase().startsWith("mutinychat://join?")) {
      throw new Error("Paste the complete authenticated MutinyChat invitation");
    }
    return raw;
  }

  async function joinRoomFromFrontend() {
    let invitation;
    try {
      invitation = normalizeAuthenticatedInvite(joinLinkDraft);
    } catch (error) {
      backendStatus = `Backend error: ${String(error)}`;
      showAlert("Invalid share link.");
      return;
    }

    try {
      isJoiningRoom = true;
      backendStatus = "Joining room...";
      applySecurityState({ channel_status: "pending" });
      const response = await invoke("backend_ipc", {
        command: "join_room",
        message: invitation,
        roomName: null
      });
      const parsed = JSON.parse(String(response));
      if (parsed.status !== "connected") {
        throw new Error(parsed.error || "Failed to join room");
      }

      onionAddress = String(parsed.onion_address || "");
      friendName = "Peer";
      clearMessageHistory();
      draft = "";
      applySecurityState(parsed);
      peerCount = 2;
      currentView = "chat";
      showJoinModal = false;
      backendStatus = "E2EE channel confirmed — compare the safety code";
      playRetroSound("door");
    } catch (error) {
      backendStatus = `Backend error: ${String(error)}`;
      applySecurityState({
        channel_status: "failed",
        channel_error: String(error)
      });
      showAlert("Could not join room. Check the link and try again.");
    } finally {
      isJoiningRoom = false;
    }
  }


  async function confirmSafetyCode() {
    if (!verificationCode || verificationLocalConfirmed) return;
    try {
      const response = await invoke("backend_ipc", {
        command: "confirm_verification",
        message: null,
        roomName: null
      });
      const parsed = JSON.parse(String(response));
      if (parsed.status === "error") {
        throw new Error(parsed.error || "Verification confirmation failed");
      }
      verificationLocalConfirmed = true;
      isPeerVerified = Boolean(parsed.verified);
      identityStatus = isPeerVerified ? "verified" : "pending";
      backendStatus = isPeerVerified
        ? "Participant verified for this session"
        : "Your confirmation was sent — waiting for your peer";
    } catch (error) {
      backendStatus = `Backend error: ${String(error)}`;
      showAlert("Could not confirm the safety code.");
    }
  }

  /** @param {KeyboardEvent} event */
  function handleInputKeydown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  }

  /** @param {"ding" | "door"} kind */
  function playRetroSound(kind) {
    if (!retroSoundsEnabled || typeof window === "undefined") {
      return;
    }

    void playRetroTone(kind).catch(() => {
      // Audio is optional and must never interrupt chat behavior.
    });
  }

  function testRetroSounds() {
    playRetroSound("door");
    window.setTimeout(() => playRetroSound("ding"), 180);
  }

  function applyUsername() {
    const normalized = usernameDraft.trim();
    myUsername = normalized || "You";
    usernameDraft = myUsername;
    backendStatus = `Username confirmed: ${myUsername}`;
    showToast(`Username set to ${myUsername}`);
  }

  /** @param {SubmitEvent} event */
  function handleUsernameSubmit(event) {
    event.preventDefault();
    applyUsername();
  }

  /** @param {KeyboardEvent} event */
  function handleUsernameKeydown(event) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    applyUsername();
    if (event.currentTarget instanceof HTMLInputElement) {
      event.currentTarget.blur();
    }
  }

  async function copyShareLink() {
    if (!shareLink) return;

    try {
      await clearCopiedInvitation();
      const invitation = await writeInvitationToClipboard(navigator.clipboard, shareLink);
      copiedInvitation = invitation;
      invitationClipboardTimer = window.setTimeout(() => {
        invitationClipboardTimer = null;
        if (copiedInvitation !== invitation) return;
        copiedInvitation = "";
        invitationClipboardCleanup = clearInvitationFromClipboard(navigator.clipboard, invitation);
        void invitationClipboardCleanup.then((cleared) => {
          if (cleared) copyNotice = "Invitation removed from the clipboard";
        });
      }, INVITATION_CLIPBOARD_TTL_MS);
      copyNotice = "Invitation copied; MutinyChat will try to clear it after 60 seconds";
    } catch (error) {
      copyNotice = `Copy failed: ${String(error)}`;
    }
  }

  function startChatting() {
    if (!connectionPresentation.canHostEnterChat) {
      backendStatus = "Waiting for a peer and confirmed secure channel";
      return;
    }
    clearMessageHistory();
    friendName = "Peer";
    backendStatus = "E2EE channel confirmed — compare the safety code";
    currentView = "chat";
  }

  /** @param {MouseEvent} event */
  function closeCreateModalOnBackdropClick(event) {
    if (event.target === event.currentTarget) {
      showCreateModal = false;
    }
  }

  /** @param {MouseEvent} event */
  function closeJoinModalOnBackdropClick(event) {
    if (event.target === event.currentTarget) {
      showJoinModal = false;
    }
  }

  onMount(() => {
    let isPolling = false;
    let pollAgainRequested = false;
    /** @type {number | null} */
    let pollTimer = null;

    const handleBeforeUnload = () => {
      void requestGracefulShutdown();
    };

    const handlePageHide = () => {
      void requestGracefulShutdown();
    };


    try {
      const saved = window.localStorage.getItem(RETRO_SOUND_PREF_KEY);
      if (saved !== null) {
        retroSoundsEnabled = saved === "true";
      }
    } catch {
      // Ignore localStorage availability issues.
    }

    try {
      clearLegacyUsernamePreference(window.localStorage);
    } catch {
      // Legacy username cleanup is best-effort when storage is unavailable.
    }

    const pollMessages = async () => {
      if (isPolling) return;
      isPolling = true;
      try {
        const response = await invoke("backend_ipc", {
          command: "poll_messages",
          message: null,
          roomName: null
        });
        const parsed = JSON.parse(String(response));
        if (isBackendPollBusy(parsed)) return;
        backendAvailable = true;
        applySecurityState(parsed);
        applyTorState(parsed);
        peerCount = Number(parsed.peer_count || 0);
        const receivedEvents = Array.isArray(parsed.events) ? parsed.events : [];
        const events = receivedEvents.slice(0, MAX_POLL_MESSAGES);
        discardedMessageCount += Math.max(0, receivedEvents.length - events.length);
        for (const rawEvent of events) {
          const event = parseFrontendEvent(rawEvent);
          if (!event) continue;
          if (event.kind === "chat") {
            if (addMessage(event.text, false)) {
              playRetroSound("ding");
            }
            continue;
          }

          if (event.event === FRONTEND_CONTROL_EVENTS.ROOM_DELETED) {
            if (channelStatus !== "disconnected" || peerCount !== 0) continue;
            clearMessageHistory();
            currentView = "lobby";
            showToast("Room closed – visible chat history cleared");
            continue;
          }

          if (event.event === FRONTEND_CONTROL_EVENTS.PEER_JOINED) {
            if (channelStatus !== "confirmed" || peerCount < 2) continue;
            playRetroSound("door");
            continue;
          }

          if (event.event === FRONTEND_CONTROL_EVENTS.PEER_VERIFIED) {
            const effect = peerVerifiedMarkerEffect({
              channelStatus,
              identityStatus,
              isPeerVerified
            });
            pollAgainRequested = effect.requestPoll;
            if (effect.showNotification) {
              showToast("Participant verified for this session");
            }
            continue;
          }

          if (event.event === FRONTEND_CONTROL_EVENTS.PEER_LEFT) {
            if (channelStatus !== "disconnected" || peerCount > 1) continue;
            showToast("Peer disconnected");
            continue;
          }

          if (event.event === FRONTEND_CONTROL_EVENTS.CHANNEL_FAILED) {
            if (channelStatus !== "failed") continue;
            showAlert("Secure channel failed. Reconnect to try again.");
            continue;
          }

        }
      } catch {
        backendAvailable = false;
        applySecurityState({
          channel_status: "failed",
          channel_error: "Backend connection unavailable"
        });
        torState = {
          status: "failed",
          routeActive: false,
          error: "Backend connection unavailable"
        };
        peerCount = 0;
      } finally {
        isPolling = false;
        if (pollAgainRequested) {
          pollAgainRequested = false;
          void pollMessages();
        }
      }
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    window.addEventListener("pagehide", handlePageHide);
    pollTimer = window.setInterval(() => {
      void pollMessages();
    }, 250);
    void pollMessages();

    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
      window.removeEventListener("pagehide", handlePageHide);
      void requestGracefulShutdown();
      void clearCopiedInvitation();
      if (pollTimer !== null) {
        window.clearInterval(pollTimer);
      }
      void closeRetroAudio().catch(() => {
        // Audio cleanup is best-effort during component teardown.
      });
    };
  });

  $effect(() => {
    if (typeof window === "undefined") {
      return;
    }

    try {
      window.localStorage.setItem(RETRO_SOUND_PREF_KEY, String(retroSoundsEnabled));
    } catch {
      // Ignore localStorage availability issues.
    }
  });

  $effect(() => {
    if (currentView !== "chat" || !chatAreaEl) {
      return;
    }

    messages.length;
    queueMicrotask(() => {
      if (chatAreaEl) {
        chatAreaEl.scrollTop = chatAreaEl.scrollHeight;
      }
    });
  });

  $effect(() => {
    if (currentView !== "room-ready" || !qrCanvas || !shareLink) {
      return;
    }

    void import("qrcode")
      .then(({ toCanvas }) =>
        toCanvas(qrCanvas, shareLink, {
          width: 220,
          margin: 2,
          color: {
            dark: "#103a70",
            light: "#ffffff"
          }
        })
      )
      .then(() => {
        qrError = "";
      })
      .catch((/** @type {unknown} */ error) => {
        qrError = `QR error: ${String(error)}`;
      });
  });
</script>

<!-- Main desktop container with retro background -->
<div class="desktop-bg d-flex align-items-center justify-content-center min-vh-100">
  <!-- Messenger window: main application container -->
  <section class="messenger-window shadow-lg d-flex flex-column position-relative" aria-label="MutinyChat main window">
    
    <!-- Title bar with retro gradient -->
    <header class="title-bar d-flex align-items-center justify-content-between flex-wrap gap-2 px-2 py-0">
      <!-- Left side: branding and status indicators -->
      <div class="title-left d-flex align-items-center gap-2 flex-wrap">
        <!-- System dot indicator -->
        <span class="window-dot flex-shrink-0" aria-hidden="true"></span>
        <!-- Title -->
        <span class="title-text text-nowrap">MutinyChat</span>
        <!-- E2EE encryption badge -->
        <span class:encrypted={isEncrypted} class="encryption-badge d-inline-block flex-shrink-0" aria-live="polite">
          {channelBadgeText(channelStatus)}
        </span>
        <!-- Current Tor runtime and room-routing status -->
        <span
          class:active={torState.routeActive}
          class:ready={torState.status === "ready" && !torState.routeActive}
          class:failed={torState.status === "failed"}
          class="tor-badge d-inline-block flex-shrink-0"
          aria-live="polite"
          title={torBadgeDescription(torState)}
        >
          🛡 {torBadgeText(torState)}
        </span>
        <!-- Room name display -->
        <span class="room-name d-none d-sm-inline-block text-truncate flex-shrink-0">{roomName}</span>
        <!-- Onion indicator -->
        <span class="onion-badge d-none d-md-inline-block flex-shrink-0">.onion</span>
      </div>
      
      <!-- Right side: close button and window controls -->
      <div class="title-right d-flex align-items-center gap-2">
        <button class="close-room-btn btn btn-sm text-nowrap" type="button" onclick={closeRoomFromFrontend}>
          Close Room
        </button>
        <!-- System window buttons -->
        <div class="window-buttons d-none d-lg-flex gap-1" aria-hidden="true">
          <span class="window-btn">_</span>
          <span class="window-btn">[]</span>
          <span class="window-btn">X</span>
        </div>
      </div>
    </header>

    <!-- Main window body: two-column responsive layout -->
    <div class="window-body flex-grow-1 d-flex overflow-hidden">
      
      <!-- Left sidebar: buddy list and controls -->
      <aside class="buddy-sidebar d-flex flex-column overflow-auto flex-shrink-0" aria-label="Buddy list">
        <!-- Sidebar heading -->
        <h2 class="buddy-heading text-truncate mb-2">Buddy List</h2>
        
        <!-- User identity panel -->
        <section class="identity-panel card card-sm flex-shrink-0 mb-2" aria-label="Profile identity">
          <form onsubmit={handleUsernameSubmit}>
            <label class="identity-label form-label mb-1" for="username-input">Your Username</label>
            <input
              id="username-input"
              class="identity-input form-control form-control-sm"
              type="text"
              maxlength="32"
              bind:value={usernameDraft}
              onkeydown={handleUsernameKeydown}
            />
            <button class="btn btn-sm btn-primary mt-2 w-100" type="submit">
              Confirm Username
            </button>
          </form>
        </section>

        <!-- Buddy card showing current connection status -->
        <div class="buddy-card card card-sm flex-shrink-0 mb-2">
          <div class="card-body p-2 d-flex align-items-center gap-2">
            <span class:status-online={connectionPresentation.confirmedPeer} class="status-dot flex-shrink-0" aria-hidden="true"></span>
            <span class="buddy-text text-truncate">{friendName}</span>
          </div>
        </div>

        <!-- Connection status indicator -->
        <p class="connection-label mb-2 small text-nowrap d-flex align-items-center gap-1">
          Status:
          <span class:status-connected={connectionPresentation.verifiedPeer} class="connection-state fw-bold flex-shrink-0">
            {connectionPresentation.statusText}
          </span>
        </p>

        <!-- Room lifecycle status -->
        <p class="room-lifecycle-status small mb-2 p-2 text-center">
          {connectionPresentation.occupancyText}
        </p>

        <!-- Ephemeral messages note -->
        <p class="ephemeral-note small mb-2 p-2 text-center fst-italic">
          Closing the room clears messages from the app; secure deletion from device memory is not guaranteed.
        </p>

        <!-- Sound effects control panel -->
        <section class="sound-panel card card-sm flex-shrink-0 mb-2" aria-label="Sound effects">
          <div class="card-body p-2">
            <h3 class="sound-heading small mb-2">Sounds</h3>
            <label class="sound-toggle form-check d-flex align-items-center gap-2 mb-2">
              <input type="checkbox" class="form-check-input" bind:checked={retroSoundsEnabled} />
              <span class="form-check-label small mb-0">Play retro sounds</span>
            </label>
            <button class="sound-test btn btn-sm btn-outline-secondary w-100" type="button" onclick={testRetroSounds}>
              Test Sounds
            </button>
          </div>
        </section>

        <!-- Backend IPC control panel -->
        <section class="backend-panel card card-sm flex-shrink-0 mb-2" aria-label="Backend IPC">
          <div class="card-body p-2">
            <h3 class="sound-heading small mb-2">Backend</h3>
            <p class="backend-status small mb-2 text-truncate">{backendStatus}</p>
            <div class="d-grid gap-1">
              <button class="sound-test btn btn-sm btn-outline-secondary" type="button" onclick={startTorFromFrontend}>
                Start Tor
              </button>
              <button class="sound-test btn btn-sm btn-outline-secondary" type="button" onclick={pingBackend}>
                Ping
              </button>
            </div>
          </div>
        </section>

        <!-- Alert messages -->
        {#if alertVisible}
          <p class="retro-alert alert alert-danger small mb-0" role="status" aria-live="polite">
            {alertMessage}
          </p>
        {/if}
      </aside>

      <!-- Main chat column: content area -->
      <main class="chat-column flex-grow-1 d-flex flex-column overflow-hidden">
        <!-- Chat toolbar with action buttons -->
        <div class="chat-toolbar d-flex align-items-center justify-content-between gap-2 p-2 flex-wrap">
          <div class="toolbar-actions d-flex gap-2 flex-grow-1 flex-wrap">
            <button class="create-room-main btn btn-sm btn-primary text-nowrap" type="button" onclick={openCreateRoomModal}>
              Create Room
            </button>
            <button class="join-room-main btn btn-sm btn-secondary text-nowrap" type="button" onclick={openJoinRoomModal}>
              Join Room
            </button>
          </div>
          <!-- Display current onion address, responsive -->
          <div class="onion-display d-flex align-items-center rounded px-2 py-1 text-truncate small flex-grow-1 flex-lg-grow-0">
            <code class="text-truncate">{onionAddress || "No active onion"}</code>
          </div>
        </div>

        <!-- Conditional content areas: Lobby, Room Ready, or Chat -->
        {#if currentView === "lobby"}
          <!-- Lobby: Create or Join options -->
          <section class="lobby-panel flex-grow-1 d-flex flex-column align-items-center justify-content-center p-4 text-center overflow-auto">
            <h2 class="room-ready-title mb-3">Create or Join</h2>
            <p class="room-note mb-4">Start a private room or use a shared link to join one.</p>
            <div class="room-ready-actions d-flex gap-2 flex-wrap justify-content-center">
              <button class="modal-btn btn btn-primary" type="button" onclick={openCreateRoomModal}>Create Room</button>
              <button class="modal-btn btn btn-secondary" type="button" onclick={openJoinRoomModal}>Join Room</button>
            </div>
          </section>

        {:else if currentView === "room-ready"}
          <!-- Room Ready: Display share QR code and link -->
          <section class="room-ready-panel flex-grow-1 d-flex flex-column align-items-center justify-content-center p-3 overflow-auto">
            <h2 class="room-ready-title mb-3">Room Ready</h2>
            <p class="room-ready-name mb-3 text-center text-break">{roomName}</p>

            <!-- Display the capability without making the whole surface an accidental copy target. -->
            <div class="share-link-big border rounded w-100 mb-2 p-2 text-break" aria-label="Room invitation">
              <code class="text-break">{shareLink}</code>
            </div>

            <p class="room-note alert alert-warning small mb-3">
              This invitation grants room access. Other apps, clipboard managers, or synced devices may read copied content. Prefer the QR code when practical.
            </p>

            <!-- QR Code canvas with border -->
            <div class="qr-wrap border p-2 mb-3 rounded">
              <canvas bind:this={qrCanvas} width="220" height="220" class="d-block" aria-label="Room share QR code"></canvas>
            </div>

            <!-- Status messages -->
            {#if qrError}
              <p class="room-note alert alert-warning small mb-2">{qrError}</p>
            {/if}
            {#if copyNotice}
              <p class="room-note alert alert-success small mb-2">{copyNotice}</p>
            {/if}

            <p class="room-note alert alert-info small mb-2" aria-live="polite">
              {connectionPresentation.occupancyText}
            </p>

            <!-- Action buttons -->
            <div class="room-ready-actions d-flex gap-2 flex-wrap justify-content-center w-100">
              <button class="modal-btn btn btn-secondary" type="button" onclick={copyShareLink}>
                Copy invitation (60-second auto-clear attempt)
              </button>
              <button
                class="modal-btn btn btn-primary"
                type="button"
                onclick={startChatting}
                disabled={!connectionPresentation.canHostEnterChat}
              >
                {connectionPresentation.canHostEnterChat ? "Continue to verification" : "Waiting for peer..."}
              </button>
            </div>
          </section>

        {:else}
          <!-- Chat view: Messages and input -->
          <section class="verification-panel alert {isPeerVerified ? 'alert-success' : 'alert-warning'} m-2 mb-0" aria-live="polite">
            {#if channelStatus === "failed"}
              <p class="fw-bold mb-1">Secure channel failed</p>
              <p class="small mb-0">{channelError || "Reconnect to establish a new secure session."}</p>
            {:else if channelStatus === "pending"}
              <p class="fw-bold mb-1">Securing channel…</p>
              <p class="small mb-0">Waiting for mutual encrypted-channel confirmation.</p>
            {:else if isPeerVerified}
              <p class="fw-bold mb-1">✅ Participant verified for this session</p>
              <p class="small mb-0">The E2EE channel is confirmed, and both participants confirmed the current session code.</p>
            {:else if channelStatus === "confirmed" && verificationCode}
              <p class="fw-bold mb-1">🔒 E2EE channel confirmed · participant identity unverified</p>
              <p class="fw-bold mb-1">Compare this safety code</p>
              <code class="safety-code d-block text-center my-2">{verificationCode}</code>
              <p class="small mb-2">
                Compare it by voice, in person, or another trusted channel. Do not compare it only through the same message that carried the invitation.
              </p>
              <p class="small mb-2">
                You: {verificationLocalConfirmed ? "confirmed" : "not confirmed"} · Peer: {verificationPeerConfirmed ? "confirmed" : "not confirmed"}
              </p>
              <button
                class="btn btn-sm btn-primary"
                type="button"
                onclick={confirmSafetyCode}
                disabled={verificationLocalConfirmed}
              >
                {verificationLocalConfirmed ? "Waiting for peer" : "I compared it and it matches"}
              </button>
            {:else}
              <p class="small mb-0">Waiting for a peer and secure-channel confirmation.</p>
            {/if}
          </section>

          <div class="chat-area flex-grow-1 d-flex flex-column gap-2 overflow-auto p-3" aria-label="Chat messages" bind:this={chatAreaEl}>
            {#if discardedMessageCount > 0}
              <p class="history-limit-note small text-muted text-center mb-1">
                {discardedMessageCount} older or oversized {discardedMessageCount === 1 ? "message was" : "messages were"} removed to keep this session responsive.
              </p>
            {/if}
            {#if messages.length === 0}
              <p class="empty-chat small text-muted text-center">No messages yet. Type below to test local send logging.</p>
            {:else}
              {#each messages as message (message.id)}
                <div class:mine={message.isMine} class="message-row d-flex {message.isMine ? 'justify-content-end' : 'justify-content-start'}">
                  <div class="bubble rounded p-2 text-break">
                    <p class="message-sender fw-bold mb-1 small">{message.sender}</p>
                    <p class="mb-0">{message.text}</p>
                  </div>
                </div>
              {/each}
            {/if}
          </div>

          <!-- Message input area -->
          <form
            class="chat-input-row p-2 border-top"
            onsubmit={(event) => {
              event.preventDefault();
              sendMessage();
            }}
          >
            <!-- Encryption warning if not encrypted -->
            {#if channelStatus === "pending"}
              <p class="encryption-warning alert alert-warning small mb-2">Securing channel…</p>
            {:else if channelStatus === "failed"}
              <p class="encryption-warning alert alert-danger small mb-2">Secure channel failed</p>
            {:else if !isEncrypted}
              <p class="encryption-warning alert alert-warning small mb-2">No confirmed E2EE channel</p>
            {:else if identityStatus !== "verified"}
              <p class="encryption-warning alert alert-warning small mb-2">E2EE channel confirmed, but participant identity is not verified</p>
            {/if}
            <!-- Input and send button -->
            <div class="d-flex gap-2">
              <input
                class="chat-input form-control form-control-sm"
                type="text"
                placeholder={isPeerVerified ? "Type a message..." : "Verify the safety code first"}
                bind:value={draft}
                maxlength={MAX_CHAT_MESSAGE_BYTES}
                onkeydown={handleInputKeydown}
                disabled={!isPeerVerified}
              />
              <button class="send-button btn btn-primary btn-sm fw-bold text-nowrap" type="submit" disabled={!isPeerVerified}>Send</button>
            </div>
          </form>
        {/if}
      </main>
    </div>

    <!-- App version indicator -->
    <span class="app-version position-absolute small text-muted" aria-label="version">v{APP_VERSION}</span>
  </section>

  <!-- Modal: Create Room -->
  {#if showCreateModal}
    <div class="modal-backdrop d-flex align-items-center justify-content-center" role="presentation" onclick={closeCreateModalOnBackdropClick}>
      <div
        class="create-modal card shadow-lg"
        role="dialog"
        aria-modal="true"
        aria-label="Create room"
      >
        <div class="card-header bg-primary text-white fw-bold">Create Room</div>
        <div class="card-body p-3">
          <label class="form-label fw-bold small" for="room-name-input">Friendly Room Name</label>
          <input
            id="room-name-input"
            class="form-control form-control-sm mb-3"
            type="text"
            bind:value={roomDraftName}
            placeholder="sunset-chat-394"
          />
          <div class="d-flex gap-2 justify-content-end">
            <button class="btn btn-sm btn-secondary" type="button" onclick={generateRandomRoomName} disabled={isGeneratingName}>
              {isGeneratingName ? "Randomizing..." : "Randomize"}
            </button>
            <button class="btn btn-sm btn-primary fw-bold" type="button" onclick={createRoomFromFrontend} disabled={isCreatingRoom}>
              {isCreatingRoom ? "Creating..." : "Create"}
            </button>
          </div>
        </div>
      </div>
    </div>
  {/if}

  <!-- Modal: Join Room -->
  {#if showJoinModal}
    <div class="modal-backdrop d-flex align-items-center justify-content-center" role="presentation" onclick={closeJoinModalOnBackdropClick}>
      <div
        class="create-modal card shadow-lg"
        role="dialog"
        aria-modal="true"
        aria-label="Join room"
      >
        <div class="card-header bg-primary text-white fw-bold">Join Room</div>
        <div class="card-body p-3">
          <label class="form-label fw-bold small" for="join-link-input">Paste Share Link</label>
          <input
            id="join-link-input"
            class="form-control form-control-sm mb-3"
            type="text"
            bind:value={joinLinkDraft}
            placeholder="Paste host share link"
          />
          <div class="d-flex gap-2 justify-content-end">
            <button class="btn btn-sm btn-secondary" type="button" onclick={() => (showJoinModal = false)}>Cancel</button>
            <button class="btn btn-sm btn-primary fw-bold" type="button" onclick={joinRoomFromFrontend} disabled={isJoiningRoom}>
              {isJoiningRoom ? "Joining..." : "Join"}
            </button>
          </div>
        </div>
      </div>
    </div>
  {/if}

  <!-- Toast notification -->
  {#if toastVisible}
    <div class="toast position-fixed bottom-0 start-50 translate-middle-x mb-3" role="status" aria-live="polite">
      {toastMessage}
    </div>
  {/if}
</div>

<style>
  /* ===== Bootstrap Overrides: Retro AOL/MSN Aesthetic ===== */
  
  :global(html) {
    width: 100%;
    height: 100%;
    margin: 0;
    padding: 0;
  }

  :global(body) {
    margin: 0;
    padding: 0;
    width: 100%;
    height: 100%;
    min-height: 100vh;
    background: linear-gradient(180deg, #0f3f9d 0%, #3f88dd 45%, #89baf0 100%);
    font-family: "MS Sans Serif", "Tahoma", "Geneva", sans-serif;
    /* Ensure body takes full height for Tauri window */
    display: flex;
    overflow: hidden;
  }

  :global(.btn) {
    font-family: "Tahoma", "MS Sans Serif", sans-serif;
    font-weight: 500;
    border-radius: 3px;
    transition: all 0.15s ease-in-out;
  }

  :global(.btn:active) {
    transform: translateY(1px);
  }

  :global(.form-control) {
    font-family: "Tahoma", "MS Sans Serif", sans-serif;
    border: 1px solid #7d96bf;
    background-color: #fff;
    box-shadow: 1px 1px 0 #fff inset;
  }

  :global(.form-control:focus) {
    border-color: #345f9f;
    box-shadow: 0 0 0 1px #7ca0db, 1px 1px 0 #fff inset;
    background-color: #fff;
  }

  :global(.card) {
    border: 1px solid #9eb7e2;
    background-color: #f5f8ff;
    box-shadow: 1px 1px 0 #fff inset;
  }

  :global(.alert) {
    border-radius: 2px;
    box-shadow: 1px 1px 0 #fff inset;
    font-weight: 500;
  }

  /* Desktop background with retro noise/pattern */
  .desktop-bg {
    width: 100%;
    height: 100%;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: clamp(0.35rem, 2vw, 1rem);
    background-image:
      radial-gradient(circle at 14% 12%, rgba(255, 255, 255, 0.25) 0 14%, transparent 15%),
      radial-gradient(circle at 84% 22%, rgba(255, 255, 255, 0.2) 0 9%, transparent 10%),
      radial-gradient(circle at 30% 82%, rgba(255, 255, 255, 0.12) 0 11%, transparent 12%);
    background-size: 220px 220px, 190px 190px, 260px 260px;
  }

  /* Main messenger window container */
  .messenger-window {
    width: clamp(550px, 95vw, 1080px);
    height: clamp(480px, 95dvh, 720px);
    background: #c9d8f7;
    border: 2px solid #0f2e66;
    box-shadow: 0 0 0 2px #f2f6ff inset, 0 16px 40px rgba(6, 20, 52, 0.45);
    display: grid;
    grid-template-rows: auto 1fr;
    grid-template-columns: 100%;
    overflow: hidden;
  }

  /* Title bar styling */
  .title-bar {
    min-height: 42px;
    background: linear-gradient(180deg, #0b4db9 0%, #0f3f9e 55%, #0b357f 100%);
    border-bottom: 1px solid #091d42;
    color: #f8fbff;
    gap: 0.5rem;
  }

  .title-left {
    min-width: 0;
    flex-wrap: wrap;
  }

  /* System indicator dot */
  .window-dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: #5ff2a2;
    border: 1px solid #c7ffdf;
    box-shadow: 0 0 0 1px #1d7349;
  }

  /* Title text */
  .title-text {
    font-weight: 700;
    font-size: 0.95rem;
    letter-spacing: 0.2px;
    text-shadow: 1px 1px 0 #09295e;
  }

  /* Encryption and Tor badges */
  .encryption-badge {
    font-size: 0.65rem;
    letter-spacing: 0.18px;
    padding: 0.1rem 0.35rem;
    border: 1px solid rgba(255, 210, 210, 0.7);
    background: rgba(122, 29, 29, 0.35);
    color: #ffd7d7;
    border-radius: 2px;
  }

  .encryption-badge.encrypted {
    border-color: rgba(170, 255, 216, 0.7);
    background: rgba(24, 114, 66, 0.32);
    color: #d9ffe9;
  }

  .tor-badge {
    font-size: 0.65rem;
    letter-spacing: 0.16px;
    padding: 0.1rem 0.35rem;
    border: 1px solid rgba(255, 223, 182, 0.7);
    background: rgba(110, 78, 24, 0.35);
    color: #ffe7bf;
    border-radius: 2px;
  }

  .tor-badge.active {
    border-color: rgba(194, 236, 255, 0.75);
    background: rgba(17, 87, 140, 0.34);
    color: #dcf3ff;
  }

  .tor-badge.ready {
    border-color: rgba(255, 227, 158, 0.8);
    background: rgba(119, 83, 19, 0.4);
    color: #fff0c9;
  }

  .tor-badge.failed {
    border-color: rgba(255, 188, 188, 0.75);
    background: rgba(122, 29, 29, 0.38);
    color: #ffd7d7;
  }

  /* Onion badge */
  .onion-badge {
    padding: 0.14rem 0.35rem;
    border: 1px solid #8fd7f9;
    background: rgba(221, 241, 255, 0.22);
    color: #d9efff;
    font-size: 0.68rem;
    letter-spacing: 0.15px;
    border-radius: 2px;
  }

  /* Room name display */
  .room-name {
    font-size: 0.78rem;
    color: #e1f1ff;
    letter-spacing: 0.2px;
    padding: 0.05rem 0.2rem;
    border: 1px solid rgba(188, 224, 255, 0.5);
    background: rgba(14, 61, 140, 0.35);
    border-radius: 2px;
  }

  /* Window control buttons */
  .window-buttons {
    gap: 4px;
  }

  .window-btn {
    width: 24px;
    height: 20px;
    border: 1px solid #274f92;
    background: linear-gradient(180deg, #e9f1ff 0%, #cadbfa 100%);
    color: #102f64;
    font-size: 0.75rem;
    line-height: 18px;
    text-align: center;
    user-select: none;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  /* Close room button */
  .close-room-btn {
    background: linear-gradient(180deg, #f8fbff 0%, #d7e5ff 100%);
    color: #1f457d;
    border: 1px solid #658dc7 !important;
    text-transform: uppercase;
    letter-spacing: 0.25px;
    padding: 0.25rem 0.5rem !important;
    height: 28px;
  }

  .close-room-btn:hover {
    background: linear-gradient(180deg, #f0f4ff 0%, #d0deff 100%);
  }

  /* Window body: main layout grid */
  .window-body {
    display: grid;
    grid-template-columns: 280px 1fr;
    gap: 0;
    min-height: 0;
    overflow: hidden;
  }

  /* =====  Buddy Sidebar: Left Panel ===== */
  .buddy-sidebar {
    background: #dde7fb;
    border-right: 2px solid #9bb6e9;
    padding: 0.75rem;
    overflow: auto;
    -webkit-overflow-scrolling: touch;
    min-width: 0;
  }

  .buddy-heading {
    font-size: 0.92rem;
    font-weight: 700;
    color: #0c2f6a;
  }

  /* Identity panel */
  .identity-panel {
    margin-bottom: 0.6rem;
  }

  .identity-label {
    font-size: 0.72rem;
    color: #1f447c;
    text-transform: uppercase;
    letter-spacing: 0.28px;
    font-weight: 700;
  }

  .identity-input {
    height: 30px !important;
    font-size: 0.83rem !important;
    padding: 0.3rem 0.45rem !important;
  }

  /* Buddy card */
  .buddy-card {
    background: #f5f8ff;
    border: 1px solid #9eb7e2;
    box-shadow: 1px 1px 0 #fff inset;
    padding: 0.5rem;
    margin-bottom: 0.6rem;
  }

  .status-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #a5afc0;
    box-shadow: 0 0 0 1px #687483;
  }

  .status-dot.status-online {
    background: #1ee479;
    box-shadow: 0 0 0 1px #107d45;
  }

  .buddy-text {
    font-size: 0.84rem;
  }

  /* Connection status */
  .connection-label {
    font-size: 0.78rem;
    color: #21457a;
    margin-bottom: 0.6rem !important;
  }

  .connection-state {
    color: #a22a2a;
  }

  .connection-state.status-connected {
    color: #1c7d45;
  }

  /* Ephemeral note */
  .ephemeral-note {
    font-size: 0.7rem;
    color: #555;
    background: #f0f0f0;
    border-radius: 2px;
    margin-bottom: 0.6rem !important;
    line-height: 1.3;
  }

  /* Room lifecycle status */
  .room-lifecycle-status {
    font-size: 0.72rem;
    color: #254a7f;
    background: #eef4ff;
    border: 1px solid #b8caea;
    margin-bottom: 0.6rem !important;
    line-height: 1.3;
  }

  /* Sound panel */
  .sound-panel {
    margin-bottom: 0.6rem;
  }

  .sound-heading {
    font-size: 0.78rem;
    color: #22467d;
    text-transform: uppercase;
    letter-spacing: 0.35px;
    font-weight: 700;
  }

  .sound-toggle {
    font-size: 0.8rem;
    color: #1f4074;
  }

  .sound-test {
    background: linear-gradient(180deg, #f8fbff 0%, #d9e6ff 100%) !important;
    color: #214376 !important;
    border: 1px solid #5d7fb7 !important;
    text-align: left;
    padding: 0.28rem 0.35rem !important;
    font-size: 0.74rem !important;
  }

  .sound-test:hover {
    background: linear-gradient(180deg, #f0f4ff 0%, #d1deff 100%) !important;
  }

  /* Backend panel */
  .backend-panel {
    margin-bottom: 0.6rem;
  }

  .backend-status {
    font-size: 0.74rem;
    color: #234777;
    line-height: 1.3;
  }

  /* Alert message */
  .retro-alert {
    margin-bottom: 0 !important;
    padding: 0.38rem 0.45rem !important;
  }

  /* ===== Chat Column: Main Content Area ===== */
  .chat-column {
    background: #f0f5ff;
    min-width: 0;
  }

  /* Chat toolbar */
  .chat-toolbar {
    background: linear-gradient(180deg, #ebf2ff 0%, #d3e2fb 100%);
    border-bottom: 1px solid #9eb7e2;
    padding: 0.5rem 0.58rem !important;
  }

  .toolbar-actions {
    gap: 0.35rem !important;
  }

  .create-room-main {
    background: linear-gradient(180deg, #fbfdff 0%, #d6e5ff 45%, #b7cdf6 100%) !important;
    color: #163a71 !important;
    border: 1px solid #2f548f !important;
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }

  .create-room-main:hover {
    background: linear-gradient(180deg, #f5f9ff 0%, #cfdeff 45%, #b0c5ee 100%) !important;
  }

  .join-room-main {
    background: linear-gradient(180deg, #f8fbff 0%, #d7e6ff 48%, #bfd3f8 100%) !important;
    color: #1b4178 !important;
    border: 1px solid #3c649e !important;
    text-transform: uppercase;
    letter-spacing: 0.25px;
  }

  .join-room-main:hover {
    background: linear-gradient(180deg, #f0f5ff 0%, #cfdeff 48%, #b7cbf0 100%) !important;
  }

  /* Onion address display with proper wrapping */
  .onion-display {
    background: #f8fbff;
    border: 1px solid #aec4ea;
    border-radius: 3px;
    color: #1f447a;
    font-family: "Courier New", monospace;
    font-size: 0.77rem;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .onion-display code {
    word-break: break-all;
    font-size: inherit;
  }

  /* ===== Lobby Panel ===== */
  .lobby-panel {
    background: #ffffff;
    border-left: 1px solid #e0e6f7;
    border-bottom: 2px solid #9db6e4;
  }

  .room-ready-title {
    color: #18407a;
    font-size: 1.1rem;
    text-transform: uppercase;
    letter-spacing: 0.35px;
    font-weight: 700;
    margin: 0 !important;
  }

  .room-note {
    font-size: 0.77rem;
    color: #275087;
  }

  .room-ready-actions {
    gap: 0.5rem !important;
  }

  /* ===== Room Ready Panel ===== */
  .room-ready-panel {
    background: #ffffff;
    border-left: 1px solid #e0e6f7;
    border-bottom: 2px solid #9db6e4;
    gap: 0.75rem !important;
  }

  .room-ready-name {
    font-family: "Courier New", monospace;
    font-size: 1rem;
    color: #1f467f;
    border: 1px solid #aac1e8;
    background: #f3f8ff;
    padding: 0.25rem 0.6rem;
    margin: 0 !important;
    word-break: break-all;
  }

  .share-link-big {
    background: linear-gradient(180deg, #f8fbff 0%, #deebff 100%) !important;
    color: #114177 !important;
    border: 1px solid #5c7db0 !important;
    font-family: "Courier New", monospace;
    font-size: 0.9rem;
    text-align: left;
    padding: 0.52rem 0.7rem !important;
    min-height: auto;
    user-select: text;
  }

  .share-link-big code {
    word-break: break-all;
    display: block;
  }

  /* QR code wrapper */
  .qr-wrap {
    border: 1px solid #8da8d5 !important;
    background: #f7fbff;
    box-shadow: 0 0 0 2px #fff inset;
    padding: 0.5rem !important;
  }

  /* ===== Chat Area ===== */
  .chat-area {
    background: #ffffff;
    border-left: 1px solid #e0e6f7;
    border-bottom: 2px solid #9db6e4;
    -webkit-overflow-scrolling: touch;
    scroll-behavior: smooth;
  }

  .empty-chat {
    margin: 0 !important;
    font-family: "Courier New", monospace;
    font-size: 0.83rem;
    color: #4b6288;
  }

  /* Message row alignment */
  .message-row {
    display: flex;
  }

  .message-row.mine {
    justify-content: flex-end;
  }

  /* Message bubble */
  .bubble {
    max-width: 75%;
    border: 1px solid #98a4b8;
    border-radius: 11px 11px 11px 3px;
    font-family: "Courier New", monospace;
    font-size: 0.85rem;
    line-height: 1.4;
    background: #f0f0f0;
    color: #222;
    box-shadow: 1px 1px 0 #fff inset, 1px 2px 0 rgba(38, 56, 86, 0.3);
    margin: 0 !important;
    word-break: break-word;
  }

  .message-row.mine .bubble {
    background: #d3e5ff;
    border-color: #6f95ca;
    color: #16335e;
    border-radius: 11px 11px 3px 11px;
  }

  /* ===== Chat Input Row ===== */
  .chat-input-row {
    background: #d7e2f8;
    border-top: 1px solid #9ab2df;
    padding: 0.55rem !important;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }

  .encryption-warning {
    font-size: 0.72rem;
    line-height: 1.2;
    padding: 0.22rem 0.42rem !important;
    margin: 0 !important;
  }

  .chat-input {
    height: 33px !important;
    border: 1px solid #7d96bf !important;
    background: #fff !important;
    padding: 0 0.5rem !important;
    font-size: 0.9rem !important;
    color: #123460 !important;
  }

  .send-button {
    background: linear-gradient(180deg, #f1f6ff 0%, #c9daf9 48%, #b7cbf3 100%) !important;
    color: #173b76 !important;
    border: 1px solid #3a5f99 !important;
    text-transform: uppercase;
    letter-spacing: 0.2px;
    padding: 0.35rem 0.7rem !important;
    height: 33px !important;
    font-weight: 700;
    white-space: nowrap;
  }

  .send-button:hover {
    background: linear-gradient(180deg, #f8fbff 0%, #dae6ff 52%, #c6d8fb 100%) !important;
  }

  .send-button:active {
    background: linear-gradient(180deg, #b9cdf6 0%, #d7e4ff 100%) !important;
    transform: translateY(1px);
  }

  /* ===== Modals ===== */
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(13, 35, 72, 0.55);
    z-index: 1000;
  }

  .create-modal {
    width: clamp(300px, 85vw, 420px);
    max-height: 80vh;
    border: 2px solid #1f4378 !important;
    box-shadow: 0 10px 28px rgba(7, 20, 42, 0.5), 0 0 0 2px #f5f9ff inset !important;
    background-color: #dbe7fb !important;
  }

  :global(.create-modal .card-header) {
    background: linear-gradient(180deg, #0d4fb8 0%, #0c3f95 100%) !important;
    font-size: 0.86rem;
    min-height: 34px;
    gap: 0;
  }

  :global(.create-modal .card-body) {
    padding: 0.75rem;
  }

  :global(.create-modal .form-label) {
    font-size: 0.76rem;
    color: #1c437d;
    text-transform: uppercase;
    margin-bottom: 0.35rem;
  }

  :global(.create-modal .form-control-sm) {
    font-size: 0.86rem !important;
    height: 33px !important;
    padding: 0 0.48rem !important;
  }

  /* Modal buttons */
  .modal-btn {
    background: linear-gradient(180deg, #f8fbff 0%, #d7e5ff 100%) !important;
    color: #183d73 !important;
    border: 1px solid #4e70a9 !important;
    font-size: 0.8rem;
    padding: 0.35rem 0.75rem !important;
  }

  .modal-btn:is(.btn-primary) {
    background: linear-gradient(180deg, #e8f2ff 0%, #bbd2f9 100%) !important;
    border-color: #325d99 !important;
  }

  .modal-btn:disabled {
    opacity: 0.65;
    cursor: wait;
  }

  /* ===== Toast Notification ===== */
  .toast {
    background: #222;
    color: #fff;
    padding: 1rem 1.5rem;
    border-radius: 4px;
    font-size: 0.9rem;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    animation: slideUp 0.3s ease-out;
  }

  @keyframes slideUp {
    from {
      opacity: 0;
      transform: translateY(10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  /* ===== App Version ===== */
  .app-version {
    font-size: 0.62rem;
    letter-spacing: 0.16px;
    color: #6a7586;
    user-select: none;
    opacity: 0.9;
    pointer-events: none;
  }

  /* ===== Responsive Breakpoints ===== */
  
  /* Tablet/Medium devices: 768px to 1023px */
  @media (max-width: 1023px) {
    .window-body {
      grid-template-columns: 240px 1fr;
    }

    .buddy-sidebar {
      padding: 0.6rem;
    }

    .create-room-main,
    .join-room-main {
      min-width: 0;
      padding: 0.28rem 0.52rem !important;
      font-size: 0.8rem;
    }

    .messenger-window {
      width: 100%;
    }
  }

  /* Small tablets: 600px to 767px */
  @media (max-width: 767px) {
    .desktop-bg {
      padding: 0.25rem;
    }

    .messenger-window {
      width: 100%;
      height: 100dvh;
      border-width: 1px;
      grid-template-rows: auto auto 1fr;
    }

    .window-body {
      grid-template-columns: 1fr;
      grid-template-rows: auto 1fr;
      border-top: 2px solid #9bb6e9;
    }

    .title-bar {
      flex-wrap: wrap;
      min-height: auto;
      padding: 0.3rem 0.4rem !important;
    }

    .title-left {
      order: 1;
      min-width: 100%;
    }

    .title-right {
      order: 2;
      width: 100%;
      justify-content: flex-end;
    }

    .close-room-btn {
      height: 26px !important;
      font-size: 0.72rem;
    }

    .room-name {
      max-width: 140px;
      font-size: 0.72rem;
    }

    .onion-badge {
      display: none;
    }

    .window-buttons {
      display: none !important;
    }

    /* Stacked buddy sidebar on small screens */
    .buddy-sidebar {
      border-right: 0;
      border-bottom: 2px solid #9bb6e9;
      padding: 0.5rem;
      max-height: 40vh;
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.35rem;
      align-content: start;
    }

    .buddy-heading,
    .identity-panel,
    .buddy-card,
    .connection-label,
    .ephemeral-note,
    .room-lifecycle-status {
      grid-column: 1 / -1;
    }

    .sound-panel,
    .backend-panel {
      margin-bottom: 0;
    }

    .chat-toolbar {
      flex-wrap: wrap;
      gap: 0.4rem !important;
      padding: 0.4rem !important;
    }

    .toolbar-actions {
      width: 100%;
      gap: 0.3rem !important;
    }

    .create-room-main,
    .join-room-main {
      flex: 1;
      min-width: 0;
    }

    .onion-display {
      flex: 1 100%;
      text-overflow: clip;
      white-space: normal;
      overflow-wrap: break-word;
      text-align: center;
      font-size: 0.72rem;
    }

    .chat-area {
      padding: 0.6rem !important;
      gap: 0.4rem !important;
    }

    .bubble {
      max-width: 85%;
    }

    .chat-input-row {
      gap: 0.3rem !important;
    }

    .send-button {
      width: 100%;
      height: 36px !important;
    }

    .room-ready-actions {
      flex-direction: column !important;
      width: 100%;
    }

    .room-ready-actions .btn {
      width: 100%;
    }

    .share-link-big {
      width: 100%;
      font-size: 0.82rem;
    }

    .toast {
      width: calc(100% - 1rem);
      font-size: 0.82rem;
      text-align: center;
      padding: 0.75rem;
    }
  }

  /* Extra small phones: under 600px */
  @media (max-width: 599px) {
    .messenger-window {
      height: 100dvh;
    }

    .title-text {
      font-size: 0.88rem;
    }

    .encryption-badge,
    .tor-badge {
      font-size: 0.6rem;
      padding: 0.08rem 0.28rem;
    }

    .buddy-sidebar {
      grid-template-columns: 1fr;
      max-height: 44vh;
      gap: 0.3rem;
    }

    .chat-toolbar {
      gap: 0.3rem !important;
      padding: 0.35rem !important;
    }

    .toolbar-actions {
      flex-direction: column;
      gap: 0.25rem !important;
      width: 100%;
    }

    .create-room-main,
    .join-room-main {
      width: 100%;
      font-size: 0.75rem;
    }

    .room-ready-panel {
      padding: 0.6rem !important;
    }

    .room-ready-title {
      font-size: 1rem;
    }

    .share-link-big {
      font-size: 0.78rem;
      padding: 0.4rem 0.52rem !important;
    }

    .chat-input {
      height: 36px !important;
    }

    .send-button {
      height: 36px !important;
      font-size: 0.8rem;
    }

    .create-modal {
      width: 90vw;
      max-height: 85vh;
    }

    .text-break {
      word-break: break-word !important;
      overflow-wrap: break-word !important;
    }
  }

  /* Ultra-wide screens: 1400px+ */
  @media (min-width: 1400px) {
    .messenger-window {
      width: min(1200px, 90vw);
    }

    .window-body {
      grid-template-columns: 320px 1fr;
    }

    .chat-toolbar {
      gap: 0.75rem !important;
    }

    .toolbar-actions {
      gap: 0.5rem !important;
    }

    .bubble {
      max-width: 65%;
      font-size: 0.9rem;
    }
  }
</style>
