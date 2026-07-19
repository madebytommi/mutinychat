from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"Expected exactly one {label} block, found {text.count(old)}")
    return text.replace(old, new, 1)


def replace_between(text: str, start: str, end: str, replacement: str, label: str) -> str:
    start_index = text.find(start)
    if start_index < 0:
        raise RuntimeError(f"Missing start marker for {label}")
    end_index = text.find(end, start_index)
    if end_index < 0:
        raise RuntimeError(f"Missing end marker for {label}")
    return text[:start_index] + replacement + text[end_index:]


main_path = ROOT / "backend" / "main.py"
main = main_path.read_text(encoding="utf-8")

main = replace_once(
    main,
    "import json\nimport os\n",
    "import json\nimport hmac\nimport os\n",
    "hmac import",
)
main = replace_once(
    main,
    "from typing import Any, Optional\n\nimport nacl.exceptions\n",
    "from typing import Any, Optional\n\nfrom participant_auth import (\n"
    "    PROTOCOL_VERSION,\n"
    "    build_confirmation_payload,\n"
    "    build_invite,\n"
    "    derive_safety_code,\n"
    "    parse_invite,\n"
    "    validate_confirmation_payload,\n"
    ")\n\nimport nacl.exceptions\n",
    "participant auth imports",
)
main = replace_once(
    main,
    "stop_event = threading.Event()\nhandshake_event = threading.Event()\n",
    "stop_event = threading.Event()\nhandshake_event = threading.Event()\nverification_event = threading.Event()\n",
    "verification event",
)
main = replace_once(
    main,
    "_private_key: Optional[PrivateKey] = None\n_box: Optional[Box] = None\n_peer_count = 0\n",
    "_private_key: Optional[PrivateKey] = None\n"
    "_peer_public_key: Optional[bytes] = None\n"
    "_box: Optional[Box] = None\n"
    "_verification_code: Optional[str] = None\n"
    "_verification_local_confirmed = False\n"
    "_verification_peer_confirmed = False\n"
    "_peer_count = 0\n",
    "participant verification globals",
)
main = replace_once(
    main,
    "    if \"timed out\" in lowered or \"timeout\" in lowered:\n"
    "        return \"The secure connection timed out. Please try again.\"\n",
    "    if \"invitation\" in lowered or \"host key\" in lowered or \"protocol version\" in lowered:\n"
    "        return message or \"The authenticated invitation is invalid or incompatible.\"\n"
    "    if \"participant verification\" in lowered or \"safety code\" in lowered:\n"
    "        return message or \"Compare and confirm the safety code before chatting.\"\n"
    "    if \"timed out\" in lowered or \"timeout\" in lowered:\n"
    "        return \"The secure connection timed out. Please try again.\"\n",
    "friendly authentication errors",
)

crypto_block = '''def _reset_participant_verification(preserve_private_key: bool = True) -> None:
    global _private_key, _peer_public_key, _box, _verification_code
    global _verification_local_confirmed, _verification_peer_confirmed
    with state_lock:
        if not preserve_private_key:
            _private_key = None
        _peer_public_key = None
        _box = None
        _verification_code = None
        _verification_local_confirmed = False
        _verification_peer_confirmed = False
        handshake_event.clear()
        verification_event.clear()


def _reset_crypto() -> None:
    global _private_key
    with state_lock:
        _private_key = PrivateKey.generate()
    _reset_participant_verification(preserve_private_key=True)


def _clear_crypto() -> None:
    _reset_participant_verification(preserve_private_key=False)


def _public_key_bytes() -> bytes:
    global _private_key
    with state_lock:
        if _private_key is None:
            _private_key = PrivateKey.generate()
        return bytes(_private_key.public_key)


def _public_key_b64() -> str:
    return base64.b64encode(_public_key_bytes()).decode("ascii")


def _room_onion_address() -> str:
    with state_lock:
        room = dict(_active_room or {})
    onion = str(room.get("onion_address", "")).strip().lower()
    if not onion:
        raise RuntimeError("Active room is missing its onion address")
    return onion


def _install_peer_public_key(value: str, expected_public_key: Optional[bytes] = None) -> None:
    global _peer_public_key, _box, _verification_code
    raw = base64.b64decode(value, validate=True)
    if len(raw) != 32:
        raise ValueError("Peer public key has an invalid length")
    if expected_public_key is not None and not hmac.compare_digest(raw, expected_public_key):
        raise ValueError("The host key does not match the authenticated invitation")
    onion = _room_onion_address()
    with state_lock:
        if _private_key is None:
            raise RuntimeError("Local session key is unavailable")
        local_public_key = bytes(_private_key.public_key)
        _peer_public_key = bytes(raw)
        _box = Box(_private_key, PublicKey(raw))
        _verification_code = derive_safety_code(local_public_key, raw, onion)
        handshake_event.set()
        verification_event.clear()


'''
main = replace_between(main, "def _reset_crypto() -> None:\n", "def encrypt_message(message: str) -> str:\n", crypto_block, "crypto state")

handshake_block = '''def _receive_handshake_frame(conn: socket.socket) -> dict[str, Any]:
    previous_timeout = conn.gettimeout()
    data = bytearray()
    try:
        conn.settimeout(HANDSHAKE_TIMEOUT)
        while True:
            try:
                chunk = conn.recv(1)
            except socket.timeout as exc:
                raise TimeoutError("Secure session handshake timed out") from exc
            if not chunk:
                raise ConnectionError("Peer closed before the secure session handshake completed")
            if chunk == b"\\n":
                break
            data.extend(chunk)
            if len(data) > MAX_FRAME_BYTES:
                raise ValueError("Peer handshake frame is too large")
    finally:
        conn.settimeout(previous_timeout)

    try:
        frame = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Peer sent a malformed handshake frame") from exc
    if not isinstance(frame, dict):
        raise ValueError("Peer handshake frame must be an object")
    return frame


def _perform_handshake(
    conn: socket.socket,
    mode: str,
    expected_host_public_key: Optional[bytes] = None,
) -> None:
    if mode not in {"host", "guest"}:
        raise ValueError("Handshake mode must be host or guest")
    peer_role = "guest" if mode == "host" else "host"
    _send_frame(
        conn,
        {
            "type": "hello",
            "v": PROTOCOL_VERSION,
            "role": mode,
            "public_key": _public_key_b64(),
        },
    )
    frame = _receive_handshake_frame(conn)
    kind = str(frame.get("type", ""))
    if kind == "error":
        raise RuntimeError(str(frame.get("message", "Peer refused the connection")))
    if kind != "hello":
        raise ValueError(f"Expected peer hello frame, received {kind or '<empty>'}")
    if frame.get("v") != PROTOCOL_VERSION:
        raise ValueError("Peer protocol version is incompatible")
    if frame.get("role") != peer_role:
        raise ValueError("Peer handshake role is invalid")
    expected_key = expected_host_public_key if mode == "guest" else None
    _install_peer_public_key(str(frame.get("public_key", "")), expected_key)
    if _box is None or not handshake_event.is_set() or not _verification_code:
        raise RuntimeError("Secure session handshake did not establish participant verification")


def _mark_verified_if_complete() -> bool:
    became_verified = False
    with state_lock:
        if _verification_local_confirmed and _verification_peer_confirmed:
            if not verification_event.is_set():
                verification_event.set()
                became_verified = True
    if became_verified:
        _queue_frontend_message("__peer_verified__")
    return verification_event.is_set()


def _handle_peer_verification(ciphertext: str) -> None:
    global _verification_peer_confirmed
    plaintext = decrypt_message(ciphertext)
    with state_lock:
        code = _verification_code
    if not code:
        raise RuntimeError("Participant verification code is unavailable")
    validate_confirmation_payload(plaintext, code)
    with state_lock:
        _verification_peer_confirmed = True
    _mark_verified_if_complete()


def confirm_verification() -> dict[str, Any]:
    global _verification_local_confirmed
    with peer_lock:
        conn = active_peer_socket
    with state_lock:
        code = _verification_code
        encrypted = _box is not None and handshake_event.is_set()
    if conn is None or not encrypted or not code:
        return {"status": "error", "error": "No encrypted peer session is ready for verification"}

    ciphertext = encrypt_message(build_confirmation_payload(code))
    try:
        _send_frame(conn, {"type": "verification", "ciphertext": ciphertext})
    except (OSError, ValueError, RuntimeError) as exc:
        return {"status": "error", "error": _friendly_error(exc)}

    with state_lock:
        _verification_local_confirmed = True
    verified = _mark_verified_if_complete()
    return {
        "status": "verified" if verified else "waiting_for_peer",
        "verified": verified,
        "verification_code": code,
    }


'''
main = replace_once(
    main,
    "def _queue_frontend_message(message: str) -> None:\n",
    handshake_block + "def _queue_frontend_message(message: str) -> None:\n",
    "handshake and verification helpers",
)

process_frame_block = '''def _process_peer_frame(conn: socket.socket, raw: bytes) -> bool:
    del conn
    try:
        frame = json.loads(raw.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Peer sent malformed JSON") from exc
    if not isinstance(frame, dict):
        raise ValueError("Peer frame must be an object")
    kind = str(frame.get("type", ""))
    if kind == "hello":
        raise ValueError("Unexpected hello frame after the handshake completed")
    if kind == "verification":
        _handle_peer_verification(str(frame.get("ciphertext", "")))
        return True
    if kind == "message":
        if not verification_event.is_set():
            raise RuntimeError("Participant verification is required before messaging")
        plaintext = decrypt_message(str(frame.get("ciphertext", "")))
        if plaintext == "__disconnect__":
            return False
        _queue_frontend_message(plaintext)
        return True
    if kind == "disconnect":
        return False
    if kind == "error":
        raise RuntimeError(str(frame.get("message", "Peer refused the connection")))
    raise ValueError(f"Unsupported peer frame type: {kind or '<empty>'}")


'''
main = replace_between(main, "def _process_peer_frame(conn: socket.socket, raw: bytes) -> bool:\n", "def _read_socket_messages(conn: socket.socket) -> None:\n", process_frame_block, "peer frame processing")

peer_session_block = '''def _release_failed_host_connection(conn: socket.socket, exc: Exception) -> None:
    global _peer_count
    with peer_lock:
        if active_peer_socket is conn:
            globals()["active_peer_socket"] = None
    _close_socket(conn)
    with state_lock:
        if _connection_mode == "host" and _active_room is not None:
            _peer_count = 1
    _reset_participant_verification(preserve_private_key=True)
    if not stop_event.is_set():
        _queue_frontend_message(f"Secure connection attempt failed: {_friendly_error(exc)}")


def _peer_session(
    conn: socket.socket,
    mode: str,
    handshake_complete: bool = False,
    expected_host_public_key: Optional[bytes] = None,
) -> None:
    global active_peer_socket, guest_socket, _peer_count, _active_room, _connection_mode
    try:
        if not handshake_complete:
            _perform_handshake(conn, mode, expected_host_public_key)
        _read_socket_messages(conn)
    finally:
        with peer_lock:
            if active_peer_socket is conn:
                active_peer_socket = None
            if guest_socket is conn:
                guest_socket = None
        _close_socket(conn)
        with state_lock:
            if mode == "host" and _connection_mode == "host" and _active_room is not None:
                _peer_count = 1
                _reset_participant_verification(preserve_private_key=True)
                if not stop_event.is_set():
                    _queue_frontend_message("__peer_left__")
            elif mode == "guest" and _connection_mode == "guest":
                _peer_count = 0
                _active_room = None
                _connection_mode = None
                _clear_crypto()
                if not stop_event.is_set():
                    _queue_frontend_message("room_deleted")


def _handle_guest(conn: socket.socket) -> None:
    global _peer_count
    if not _claim_active_peer_socket(conn):
        try:
            _send_frame(conn, {"type": "error", "message": "This room already has two participants"})
        finally:
            _close_socket(conn)
        return

    _reset_participant_verification(preserve_private_key=True)
    try:
        _perform_handshake(conn, "host")
    except Exception as exc:
        _release_failed_host_connection(conn, exc)
        return

    with state_lock:
        _peer_count = 2
    _queue_frontend_message("__peer_joined__")
    _peer_session(conn, "host", handshake_complete=True)


'''
main = replace_between(main, "def _peer_session(conn: socket.socket, mode: str) -> None:\n", "def _listener_loop(server: socket.socket) -> None:\n", peer_session_block, "peer session lifecycle")

join_block = '''def join_room(invitation: str, port: int) -> dict[str, Any]:
    global guest_socket, _peer_count, _active_room, _connection_mode
    authenticated_invite = parse_invite(invitation)
    onion_host = authenticated_invite.onion_address
    close_room()
    start_tor()
    if not active_socks_port:
        raise RuntimeError("Tor SOCKS port is unavailable")
    _reset_crypto()
    stop_event.clear()
    client = socks.socksocket()
    try:
        client.set_proxy(socks.SOCKS5, "127.0.0.1", active_socks_port)
        client.settimeout(CONNECT_TIMEOUT)
        client.connect((onion_host, port))
        client.settimeout(1)
    except Exception:
        _close_socket(client)
        close_room()
        raise
    if not _claim_active_peer_socket(client):
        _close_socket(client)
        close_room()
        raise RuntimeError("Another peer connection is active")
    guest_socket = client
    _peer_count = 1
    _connection_mode = "guest"
    _active_room = {
        "mode": "guest",
        "onion_address": onion_host,
        "port": port,
        "expected_host_public_key": authenticated_invite.host_public_key,
    }
    try:
        _perform_handshake(client, "guest", authenticated_invite.host_public_key)
    except Exception:
        close_room()
        raise
    with state_lock:
        _peer_count = 2
        code = _verification_code
    threading.Thread(
        target=_peer_session,
        args=(client, "guest", True, authenticated_invite.host_public_key),
        daemon=True,
    ).start()
    return {
        "status": "connected",
        "onion_address": onion_host,
        "port": port,
        "encrypted": True,
        "verified": False,
        "verification_code": code,
        "protocol_version": PROTOCOL_VERSION,
    }


'''
main = replace_between(main, "def join_room(onion_address: str, port: int) -> dict[str, Any]:\n", "def send_message(text: str) -> dict[str, str]:\n", join_block, "authenticated join")

send_block = '''def send_message(text: str) -> dict[str, str]:
    payload = text.strip()
    if not payload:
        return {"status": "error", "error": "Message cannot be empty"}
    with peer_lock:
        conn = active_peer_socket
    if conn is None:
        return {"status": "error", "error": "No active peer socket"}
    if not verification_event.is_set():
        return {
            "status": "error",
            "error": "Compare and confirm the participant safety code before sending messages",
        }
    try:
        _send_frame(conn, {"type": "message", "ciphertext": encrypt_message(payload)})
        return {"status": "sent"}
    except (OSError, ValueError, RuntimeError) as exc:
        return {"status": "error", "error": _friendly_error(exc)}


'''
main = replace_between(main, "def send_message(text: str) -> dict[str, str]:\n", "def close_room() -> dict[str, str]:\n", send_block, "verification-gated messages")

room_response_block = '''def build_room_response(room_name: str) -> dict[str, Any]:
    global _active_room, _peer_count, _connection_mode
    close_room()
    _reset_crypto()
    try:
        room = create_hidden_service(room_name)
    except Exception:
        close_room()
        raise
    _active_room = {
        "mode": "host", "friendly_name": room_name, "onion_address": room["onion_address"],
        "service_id": active_service_id, "local_port": active_local_port,
    }
    _connection_mode = "host"
    _peer_count = 1
    invitation = build_invite(room["onion_address"], _public_key_bytes())
    return {
        "friendly_name": room_name,
        "onion_address": room["onion_address"],
        "share_link": invitation,
        "protocol_version": PROTOCOL_VERSION,
    }


'''
main = replace_between(main, "def build_room_response(room_name: str) -> dict[str, Any]:\n", "def poll_messages() -> dict[str, Any]:\n", room_response_block, "authenticated room response")

poll_block = '''def poll_messages() -> dict[str, Any]:
    with inbox_lock:
        messages = list(_inbox)
        _inbox.clear()
    with state_lock:
        encrypted = _box is not None and handshake_event.is_set()
        verified = verification_event.is_set()
        code = _verification_code
        local_confirmed = _verification_local_confirmed
        peer_confirmed = _verification_peer_confirmed
    return {
        "messages": messages,
        "encrypted": encrypted,
        "verified": verified,
        "verification_code": code,
        "verification_local_confirmed": local_confirmed,
        "verification_peer_confirmed": peer_confirmed,
        "protocol_version": PROTOCOL_VERSION,
        "tor_active": tor_controller is not None,
        "peer_count": _peer_count,
    }


'''
main = replace_between(main, "def poll_messages() -> dict[str, Any]:\n", "def handle_json_command(payload: dict[str, Any]) -> dict[str, Any]:\n", poll_block, "verification polling state")
main = replace_once(
    main,
    "        if command == \"send_message\":\n"
    "            return send_message(str(payload.get(\"text\", payload.get(\"message\", \"\"))))\n",
    "        if command == \"confirm_verification\":\n"
    "            return confirm_verification()\n"
    "        if command == \"send_message\":\n"
    "            return send_message(str(payload.get(\"text\", payload.get(\"message\", \"\"))))\n",
    "confirm verification command",
)
main_path.write_text(main, encoding="utf-8")

sidecar_path = ROOT / "backend" / "sidecar.py"
sidecar_path.write_text(
    '''"""Windows sidecar entrypoint using the shared authenticated backend protocol."""
from __future__ import annotations

import main as backend

CONNECT_TIMEOUT = 60
HANDSHAKE_TIMEOUT = 30


def install() -> None:
    """Use Windows-friendly timeouts without replacing protocol functions."""
    backend.CONNECT_TIMEOUT = CONNECT_TIMEOUT
    backend.HANDSHAKE_TIMEOUT = HANDSHAKE_TIMEOUT


if __name__ == "__main__":
    install()
    backend.main()
''',
    encoding="utf-8",
)

test_sidecar_path = ROOT / "backend" / "test_sidecar.py"
test_sidecar_path.write_text(
    '''import unittest

import main as backend
import sidecar


class SidecarConfigurationTestCase(unittest.TestCase):
    def test_install_sets_windows_timeouts_without_replacing_protocol(self):
        original_join = backend.join_room
        original_handle_guest = backend._handle_guest
        original_peer_session = backend._peer_session

        sidecar.install()

        self.assertIs(backend.join_room, original_join)
        self.assertIs(backend._handle_guest, original_handle_guest)
        self.assertIs(backend._peer_session, original_peer_session)
        self.assertEqual(60, backend.CONNECT_TIMEOUT)
        self.assertEqual(30, backend.HANDSHAKE_TIMEOUT)


if __name__ == "__main__":
    unittest.main()
''',
    encoding="utf-8",
)

test_main_path = ROOT / "backend" / "test_main.py"
test_main = test_main_path.read_text(encoding="utf-8")
test_main = replace_once(
    test_main,
    "        backend._private_key = alice\n"
    "        backend._install_peer_public_key(base64.b64encode(bytes(bob.public_key)).decode(\"ascii\"))\n",
    "        backend._private_key = alice\n"
    "        backend._active_room = {\"onion_address\": \"a\" * 56 + \".onion\"}\n"
    "        backend._install_peer_public_key(base64.b64encode(bytes(bob.public_key)).decode(\"ascii\"))\n",
    "round-trip active room",
)
test_main = replace_once(
    test_main,
    "        backend._private_key = alice\n"
    "        backend._install_peer_public_key(base64.b64encode(bytes(bob.public_key)).decode(\"ascii\"))\n",
    "        backend._private_key = alice\n"
    "        backend._active_room = {\"onion_address\": \"a\" * 56 + \".onion\"}\n"
    "        backend._install_peer_public_key(base64.b64encode(bytes(bob.public_key)).decode(\"ascii\"))\n",
    "wrong-key active room",
)
old_hello_test = '''    def test_hello_frame_establishes_secure_session(self):
        local = PrivateKey.generate()
        remote = PrivateKey.generate()
        backend._private_key = local
        left, right = socket.socketpair()
        try:
            frame = json.dumps(
                {
                    "type": "hello",
                    "public_key": base64.b64encode(bytes(remote.public_key)).decode("ascii"),
                }
            ).encode("utf-8")
            self.assertTrue(backend._process_peer_frame(left, frame))
            self.assertTrue(backend.handshake_event.is_set())
            self.assertIsNotNone(backend._box)
        finally:
            left.close()
            right.close()

'''
new_auth_tests = '''    def test_peer_key_install_creates_unverified_safety_code(self):
        local = PrivateKey.generate()
        remote = PrivateKey.generate()
        backend._private_key = local
        backend._active_room = {"onion_address": "a" * 56 + ".onion"}
        backend._install_peer_public_key(
            base64.b64encode(bytes(remote.public_key)).decode("ascii")
        )
        state = backend.poll_messages()
        self.assertTrue(state["encrypted"])
        self.assertFalse(state["verified"])
        self.assertRegex(state["verification_code"], r"^\\d{5} \\d{5} \\d{5} \\d{5}$")

    def test_peer_key_install_rejects_invitation_key_mismatch(self):
        local = PrivateKey.generate()
        expected = PrivateKey.generate()
        attacker = PrivateKey.generate()
        backend._private_key = local
        backend._active_room = {"onion_address": "a" * 56 + ".onion"}
        with self.assertRaisesRegex(ValueError, "does not match"):
            backend._install_peer_public_key(
                base64.b64encode(bytes(attacker.public_key)).decode("ascii"),
                bytes(expected.public_key),
            )

    def test_message_is_blocked_until_both_participants_confirm(self):
        left, right = socket.socketpair()
        try:
            backend.active_peer_socket = left
            result = backend.send_message("secret")
            self.assertEqual("error", result["status"])
            self.assertIn("safety code", result["error"])
        finally:
            backend.active_peer_socket = None
            left.close()
            right.close()

'''
test_main = replace_once(test_main, old_hello_test, new_auth_tests, "obsolete hello test")
test_main = replace_once(
    test_main,
    "        self.assertEqual(\"test-room\", response[\"friendly_name\"])\n"
    "        self.assertNotIn(\"key_b64\", response)\n",
    "        self.assertEqual(\"test-room\", response[\"friendly_name\"])\n"
    "        self.assertTrue(response[\"share_link\"].startswith(\"mutinychat://join?\"))\n"
    "        self.assertNotIn(\"key_b64\", response)\n",
    "authenticated room test",
)
test_main_path.write_text(test_main, encoding="utf-8")

app_path = ROOT / "src" / "App.svelte"
app = app_path.read_text(encoding="utf-8")
app = replace_once(
    app,
    "  let isEncrypted = $state(false);\n"
    "  let isTorProtected = $state(false);\n",
    "  let isEncrypted = $state(false);\n"
    "  let isTorProtected = $state(false);\n"
    "  let isPeerVerified = $state(false);\n"
    "  let verificationCode = $state(\"\");\n"
    "  let verificationLocalConfirmed = $state(false);\n"
    "  let verificationPeerConfirmed = $state(false);\n"
    "  let peerCount = $state(0);\n",
    "frontend verification state",
)
app = replace_once(
    app,
    "    const text = draft.trim();\n"
    "    if (!text) return;\n",
    "    if (!isPeerVerified) {\n"
    "      showAlert(\"Compare and confirm the safety code before messaging.\");\n"
    "      return;\n"
    "    }\n\n"
    "    const text = draft.trim();\n"
    "    if (!text) return;\n",
    "frontend send verification gate",
)
app = replace_once(
    app,
    "    isEncrypted = false;\n"
    "    isTorProtected = false;\n",
    "    isEncrypted = false;\n"
    "    isTorProtected = false;\n"
    "    isPeerVerified = false;\n"
    "    verificationCode = \"\";\n"
    "    verificationLocalConfirmed = false;\n"
    "    verificationPeerConfirmed = false;\n"
    "    peerCount = 0;\n",
    "frontend close verification reset",
)
old_extract = '''  /** @param {string} input */
  function extractOnionAddress(input) {
    const raw = String(input || "").trim();
    const match = raw.match(/([a-z2-7]{16,56}\.onion)/i);
    if (match?.[1]) {
      return match[1].toLowerCase();
    }
    throw new Error("No valid .onion address found. Paste the exact share link copied from the host room");
  }
'''
new_extract = '''  /** @param {string} input */
  function normalizeAuthenticatedInvite(input) {
    const raw = String(input || "").trim();
    if (!raw.toLowerCase().startsWith("mutinychat://join?")) {
      throw new Error("Paste the complete authenticated MutinyChat invitation");
    }
    return raw;
  }
'''
app = replace_once(app, old_extract, new_extract, "frontend invitation parser")
app = replace_once(
    app,
    "    let onion;\n"
    "    try {\n"
    "      onion = extractOnionAddress(joinLinkDraft);\n",
    "    let invitation;\n"
    "    try {\n"
    "      invitation = normalizeAuthenticatedInvite(joinLinkDraft);\n",
    "join invitation variable",
)
app = replace_once(
    app,
    "        message: onion,\n",
    "        message: invitation,\n",
    "join authenticated invitation payload",
)
app = replace_once(
    app,
    "      onionAddress = String(parsed.onion_address || \"\");\n"
    "      friendName = \"Connected!\";\n"
    "      connectionStatus = \"Connected\";\n"
    "      messages = [];\n"
    "      draft = \"\";\n"
    "      isEncrypted = false;\n"
    "      currentView = \"chat\";\n"
    "      showJoinModal = false;\n"
    "      backendStatus = \"Connected!\";\n",
    "      onionAddress = String(parsed.onion_address || \"\");\n"
    "      friendName = \"Peer\";\n"
    "      connectionStatus = \"Verification required\";\n"
    "      messages = [];\n"
    "      draft = \"\";\n"
    "      isEncrypted = Boolean(parsed.encrypted);\n"
    "      isPeerVerified = Boolean(parsed.verified);\n"
    "      verificationCode = String(parsed.verification_code || \"\");\n"
    "      verificationLocalConfirmed = false;\n"
    "      verificationPeerConfirmed = false;\n"
    "      peerCount = 2;\n"
    "      currentView = \"chat\";\n"
    "      showJoinModal = false;\n"
    "      backendStatus = \"Encrypted connection ready — compare the safety code\";\n",
    "guest verification state",
)
confirm_function = '''
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
      connectionStatus = isPeerVerified ? "Verified" : "Waiting for peer confirmation";
      backendStatus = isPeerVerified
        ? "Participant verified for this session"
        : "Your confirmation was sent — waiting for your peer";
    } catch (error) {
      backendStatus = `Backend error: ${String(error)}`;
      showAlert("Could not confirm the safety code.");
    }
  }

'''
app = replace_once(
    app,
    "  /** @param {KeyboardEvent} event */\n  function handleInputKeydown(event) {\n",
    confirm_function + "  /** @param {KeyboardEvent} event */\n  function handleInputKeydown(event) {\n",
    "safety code confirmation function",
)
app = replace_once(
    app,
    "  function startChatting() {\n"
    "    messages = [];\n"
    "    friendName = `${roomName}-friend`;\n"
    "    connectionStatus = \"Connected\";\n"
    "    backendStatus = \"Live chat ready\";\n"
    "    currentView = \"chat\";\n"
    "  }\n",
    "  function startChatting() {\n"
    "    messages = [];\n"
    "    friendName = \"Peer\";\n"
    "    connectionStatus = peerCount >= 2 ? \"Verification required\" : \"Waiting for peer\";\n"
    "    backendStatus = peerCount >= 2\n"
    "      ? \"Encrypted connection ready — compare the safety code\"\n"
    "      : \"Waiting for a peer to join\";\n"
    "    currentView = \"chat\";\n"
    "  }\n",
    "host chat transition",
)
app = replace_once(
    app,
    "        isEncrypted = Boolean(parsed.encrypted);\n"
    "        isTorProtected = Boolean(parsed.tor_active);\n"
    "        const items = Array.isArray(parsed.messages) ? parsed.messages : [];\n",
    "        isEncrypted = Boolean(parsed.encrypted);\n"
    "        isTorProtected = Boolean(parsed.tor_active);\n"
    "        isPeerVerified = Boolean(parsed.verified);\n"
    "        verificationCode = String(parsed.verification_code || \"\");\n"
    "        verificationLocalConfirmed = Boolean(parsed.verification_local_confirmed);\n"
    "        verificationPeerConfirmed = Boolean(parsed.verification_peer_confirmed);\n"
    "        peerCount = Number(parsed.peer_count || 0);\n"
    "        if (peerCount >= 2) {\n"
    "          connectionStatus = isPeerVerified ? \"Verified\" : \"Verification required\";\n"
    "        } else if (currentView !== \"lobby\") {\n"
    "          connectionStatus = \"Waiting for peer\";\n"
    "        }\n"
    "        const items = Array.isArray(parsed.messages) ? parsed.messages : [];\n",
    "poll verification state",
)
app = replace_once(
    app,
    "            messages = [];\n"
    "            isEncrypted = false;\n"
    "            currentView = \"lobby\";\n",
    "            messages = [];\n"
    "            isEncrypted = false;\n"
    "            isPeerVerified = false;\n"
    "            verificationCode = \"\";\n"
    "            verificationLocalConfirmed = false;\n"
    "            verificationPeerConfirmed = false;\n"
    "            peerCount = 0;\n"
    "            currentView = \"lobby\";\n",
    "room deletion verification reset",
)
app = replace_once(
    app,
    "          if (payload === \"__peer_joined__\") {\n"
    "            connectionStatus = \"Connected\";\n"
    "            playRetroSound(\"door\");\n"
    "            continue;\n"
    "          }\n\n"
    "          addMessage(payload, false);\n",
    "          if (payload === \"__peer_joined__\") {\n"
    "            connectionStatus = \"Verification required\";\n"
    "            playRetroSound(\"door\");\n"
    "            continue;\n"
    "          }\n\n"
    "          if (payload === \"__peer_verified__\") {\n"
    "            isPeerVerified = true;\n"
    "            connectionStatus = \"Verified\";\n"
    "            showToast(\"Participant verified for this session\");\n"
    "            continue;\n"
    "          }\n\n"
    "          if (payload === \"__peer_left__\") {\n"
    "            isEncrypted = false;\n"
    "            isPeerVerified = false;\n"
    "            verificationCode = \"\";\n"
    "            verificationLocalConfirmed = false;\n"
    "            verificationPeerConfirmed = false;\n"
    "            peerCount = 1;\n"
    "            connectionStatus = \"Waiting for peer\";\n"
    "            showToast(\"Peer disconnected\");\n"
    "            continue;\n"
    "          }\n\n"
    "          addMessage(payload, false);\n",
    "frontend verification control events",
)
app = replace_once(
    app,
    "        <span class:encrypted={isEncrypted} class=\"encryption-badge d-inline-block flex-shrink-0\" aria-live=\"polite\">\n"
    "          {isEncrypted ? \"🔒 E2EE\" : \"🔓 Not Encrypted\"}\n"
    "        </span>\n",
    "        <span class:encrypted={isEncrypted} class:verified={isPeerVerified} class=\"encryption-badge d-inline-block flex-shrink-0\" aria-live=\"polite\">\n"
    "          {isPeerVerified ? \"✅ Verified E2EE\" : isEncrypted ? \"🔒 Encrypted • Unverified\" : \"🔓 Not Encrypted\"}\n"
    "        </span>\n",
    "verified encryption badge",
)
app = app.replace('class:status-online={connectionStatus === "Connected"}', 'class:status-online={peerCount >= 2}', 1)
app = app.replace('class:status-connected={connectionStatus === "Connected"}', 'class:status-connected={isPeerVerified}', 1)
app = replace_once(
    app,
    "          {connectionStatus === \"Connected\" ? \"2/2 connected - room will vanish when both leave\" : \"1/2 connected - room will vanish when both leave\"}\n",
    "          {peerCount >= 2 ? \"2/2 connected - verify before chatting\" : \"1/2 connected - waiting for peer\"}\n",
    "peer count wording",
)
verification_panel = '''          <section class="verification-panel alert {isPeerVerified ? 'alert-success' : 'alert-warning'} m-2 mb-0" aria-live="polite">
            {#if isPeerVerified}
              <p class="fw-bold mb-1">✅ Participant verified for this session</p>
              <p class="small mb-0">This only proves that both apps saw the same session keys after you compared the code.</p>
            {:else if isEncrypted && verificationCode}
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
              <p class="small mb-0">Waiting for the encrypted handshake and safety code.</p>
            {/if}
          </section>

'''
app = replace_once(
    app,
    "        {:else}\n"
    "          <!-- Chat view: Messages and input -->\n"
    "          <div class=\"chat-area flex-grow-1 d-flex flex-column gap-2 overflow-auto p-3\" aria-label=\"Chat messages\" bind:this={chatAreaEl}>\n",
    "        {:else}\n"
    "          <!-- Chat view: Messages and input -->\n"
    + verification_panel
    + "          <div class=\"chat-area flex-grow-1 d-flex flex-column gap-2 overflow-auto p-3\" aria-label=\"Chat messages\" bind:this={chatAreaEl}>\n",
    "verification panel",
)
app = replace_once(
    app,
    "            {#if !isEncrypted}\n"
    "              <p class=\"encryption-warning alert alert-warning small mb-2\">🔓 Not Encrypted</p>\n"
    "            {/if}\n",
    "            {#if !isEncrypted}\n"
    "              <p class=\"encryption-warning alert alert-warning small mb-2\">🔓 Not Encrypted</p>\n"
    "            {:else if !isPeerVerified}\n"
    "              <p class=\"encryption-warning alert alert-warning small mb-2\">🔒 Encrypted, but participant identity is not verified</p>\n"
    "            {/if}\n",
    "unverified encryption warning",
)
app = replace_once(
    app,
    "                placeholder=\"Type a message...\"\n"
    "                bind:value={draft}\n"
    "                onkeydown={handleInputKeydown}\n"
    "              />\n"
    "              <button class=\"send-button btn btn-primary btn-sm fw-bold text-nowrap\" type=\"submit\">Send</button>\n",
    "                placeholder={isPeerVerified ? \"Type a message...\" : \"Verify the safety code first\"}\n"
    "                bind:value={draft}\n"
    "                onkeydown={handleInputKeydown}\n"
    "                disabled={!isPeerVerified}\n"
    "              />\n"
    "              <button class=\"send-button btn btn-primary btn-sm fw-bold text-nowrap\" type=\"submit\" disabled={!isPeerVerified}>Send</button>\n",
    "disabled unverified message input",
)
style_insert = '''
  .encryption-badge.verified {
    border-color: rgba(184, 255, 204, 0.85);
    background: rgba(20, 120, 62, 0.45);
    color: #e2ffeb;
  }

  .verification-panel {
    border-radius: 3px;
    flex-shrink: 0;
  }

  .safety-code {
    font-family: "Courier New", monospace;
    font-size: clamp(1rem, 2.5vw, 1.35rem);
    font-weight: 700;
    letter-spacing: 0.08em;
    user-select: text;
  }

'''
if "  .encryption-badge.verified {" in app:
    raise RuntimeError("Verification styles already present")
app = app.replace("  /* Tor protection badge */", style_insert + "  /* Tor protection badge */", 1)
app_path.write_text(app, encoding="utf-8")

readme_path = ROOT / "README.md"
readme = readme_path.read_text(encoding="utf-8")
readme = replace_once(
    readme,
    "- PyNaCl public-key session handshake and encrypted messages\n"
    "- One host and one guest per room\n",
    "- PyNaCl public-key session handshake and encrypted messages\n"
    "- Authenticated invitations that bind the onion address to the host session key\n"
    "- A 20-digit participant safety code that both people must compare and confirm before messaging\n"
    "- One host and one guest per room\n",
    "README implemented authentication",
)
readme = replace_once(
    readme,
    "- PyNaCl `Box` public-key handshake and encrypted messages\n"
    "- Runtime Tor data stored in a temporary writable directory and removed during normal shutdown\n",
    "- PyNaCl `Box` public-key handshake and encrypted messages\n"
    "- Invitation-bound host keys plus a session safety code derived from both ephemeral keys and the onion address\n"
    "- Chat remains locked until both participants confirm that they compared the same safety code\n"
    "- Runtime Tor data stored in a temporary writable directory and removed during normal shutdown\n",
    "README backend authentication",
)
readme = replace_once(
    readme,
    "- No user-verifiable safety-number or identity-verification UI exists yet.\n",
    "- First-contact identity still requires the two people to compare the safety code through a separate trusted channel; the app cannot automatically know a person's real-world identity.\n",
    "README limitation update",
)
readme = replace_once(
    readme,
    "- Removing third-party sound requests does not mean every application network flow is automatically protected by Tor.\n"
    "- Do not treat prototype status as a guarantee of anonymity or security.\n",
    "- Removing third-party sound requests does not mean every application network flow is automatically protected by Tor.\n"
    "- An authenticated invitation detects a host-key mismatch, while the safety-code comparison detects full invitation substitution when users compare it through an independent trusted channel.\n"
    "- Never confirm a safety code without actually comparing it with the intended participant. A user who blindly confirms can still accept an attacker.\n"
    "- Verification applies only to the current ephemeral session and does not create a persistent identity or contact record.\n"
    "- Do not treat prototype status as a guarantee of anonymity or security.\n",
    "README participant verification guidance",
)
readme_path.write_text(readme, encoding="utf-8")

print("Applied C2 participant-authentication patch successfully.")
