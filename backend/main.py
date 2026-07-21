"""MutinyChat Tor peer backend and stdio JSON command server."""
from __future__ import annotations

import argparse
import atexit
import base64
import binascii
from collections import deque
import json
import hmac
import os
import random
import re
import secrets
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Optional

from participant_auth import (
    CHANNEL_CHALLENGE_BYTES,
    HANDSHAKE_NONCE_BYTES,
    PROTOCOL_VERSION,
    build_channel_challenge_payload,
    build_channel_response_payload,
    build_confirmation_payload,
    build_invite,
    derive_handshake_transcript_hash,
    derive_safety_code,
    parse_channel_challenge_payload,
    parse_channel_response_payload,
    parse_invite,
    validate_confirmation_payload,
)

import nacl.exceptions
from nacl.public import Box, PrivateKey, PublicKey
import socks
import stem.process
from stem.control import Controller

DEFAULT_ONION_PORT = 8080
CONNECT_TIMEOUT = 20
HANDSHAKE_TIMEOUT = 15
MAX_FRAME_BYTES = 1024 * 1024
MAX_APPLICATION_FRAME_BYTES = 64 * 1024
MAX_CHAT_MESSAGE_BYTES = 16 * 1024
MAX_ENCRYPTED_MESSAGE_CHARS = ((MAX_CHAT_MESSAGE_BYTES + 64 + 2) // 3) * 4
MAX_INBOUND_FRAMES_PER_SECOND = 64
MAX_INBOUND_FRAME_BYTES_PER_SECOND = 512 * 1024
MAX_FRONTEND_QUEUE_MESSAGES = 128
MAX_FRONTEND_QUEUE_BYTES = 512 * 1024
MAX_FRONTEND_QUEUE_ITEM_BYTES = 128 * 1024
MAX_POLL_MESSAGES = 32
MAX_POLL_MESSAGE_BYTES = 128 * 1024
MAX_ERROR_MESSAGE_CHARS = 512
FRONTEND_CONTROL_EVENTS = frozenset(
    {
        "channel_failed",
        "peer_joined",
        "peer_left",
        "peer_verified",
        "room_deleted",
    }
)
ONION_V3_RE = re.compile(r"(?<![a-z2-7])([a-z2-7]{56}\.onion)(?![a-z2-7.])", re.I)

state_lock = threading.RLock()
peer_lock = threading.RLock()
send_lock = threading.Lock()
inbox_lock = threading.Lock()
stop_event = threading.Event()
handshake_event = threading.Event()
verification_event = threading.Event()

tor_controller: Optional[Controller] = None
tor_process: Any = None
_tor_generation = 0
active_service_id: Optional[str] = None
active_local_port: Optional[int] = None
active_socks_port: Optional[int] = None
listener_thread: Optional[threading.Thread] = None
listener_socket: Optional[socket.socket] = None
guest_socket: Optional[socket.socket] = None
active_peer_socket: Optional[socket.socket] = None
_active_peer_generation: Optional[int] = None
_peer_generation = 0
_tor_data_dir: Optional[str] = None
_private_key: Optional[PrivateKey] = None
_peer_public_key: Optional[bytes] = None
_box: Optional[Box] = None
_handshake_transcript_hash: Optional[bytes] = None
_connection_role: Optional[str] = None
_channel_status = "disconnected"
_channel_error: Optional[str] = None
_verification_code: Optional[str] = None
_verification_local_confirmed = False
_verification_peer_confirmed = False
_peer_count = 0
_active_room: Optional[dict[str, Any]] = None
_connection_mode: Optional[str] = None
_inbox: deque[tuple[dict[str, str], int]] = deque()
_inbox_bytes = 0

ADJECTIVES = ["midnight", "pixel", "sunset", "neon", "velvet", "silver", "echo", "lunar"]
NOUNS = ["ocean", "dream", "chat", "signal", "harbor", "voyage", "cipher", "comet"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MutinyChat backend")
    parser.add_argument("--command")
    parser.add_argument("--message")
    parser.add_argument("--room-name")
    parser.add_argument("--onion-address")
    parser.add_argument("--port", type=int)
    parser.add_argument("--stdio-json", action="store_true")
    return parser.parse_args()


def _pick_random_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def generate_random_room_name() -> str:
    return f"{random.choice(ADJECTIVES)}-{random.choice(NOUNS)}-{random.randint(100, 999)}"


def _friendly_error(exc: Exception) -> str:
    message = str(exc).strip()
    if len(message) > MAX_ERROR_MESSAGE_CHARS:
        message = message[: MAX_ERROR_MESSAGE_CHARS - 1] + "…"
    lowered = message.lower()
    if "tor executable not found" in lowered:
        return "Tor is unavailable. Install Tor for development or use a build that bundles it."
    if "failed to start tor" in lowered:
        return "Tor failed to start. Please try again."
    if "no valid .onion" in lowered:
        return "Invalid share link. Paste the complete MutinyChat room link."
    if "invitation" in lowered or "host key" in lowered or "protocol version" in lowered:
        return message or "The authenticated invitation is invalid or incompatible."
    if "participant verification" in lowered or "safety code" in lowered:
        return message or "Compare and confirm the safety code before chatting."
    if "timed out" in lowered or "timeout" in lowered:
        return "The secure connection timed out. Please try again."
    if "secure session" in lowered or "handshake" in lowered:
        return "The secure session is not ready. Please try again."
    if "not connected" in lowered or "no active peer" in lowered:
        return "Not connected to a peer yet."
    return message or "Something went wrong. Please try again."


def _runtime_roots() -> list[Path]:
    module_dir = Path(__file__).resolve().parent
    roots = [module_dir, module_dir / "dist", module_dir / "tor", Path(sys.executable).resolve().parent]
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        roots.extend([Path(bundle_root), Path(bundle_root) / "tor"])
    return roots


def _is_executable_file(candidate: Path) -> bool:
    return candidate.is_file() and (os.name == "nt" or os.access(candidate, os.X_OK))


def _resolve_tor_cmd() -> str:
    configured = os.environ.get("MUTINYCHAT_TOR_PATH", "").strip()
    require_bundled = os.environ.get("MUTINYCHAT_REQUIRE_BUNDLED_TOR", "").strip() == "1"

    if require_bundled:
        if not configured:
            raise RuntimeError("Bundled Tor is required but no executable path was configured")
        bundled_candidate = Path(configured).expanduser()
        if not bundled_candidate.is_absolute():
            raise RuntimeError("Bundled Tor requires an absolute executable path")
        if _is_executable_file(bundled_candidate):
            return str(bundled_candidate)
        raise RuntimeError("Required bundled Tor executable is missing or not executable")

    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser())
    for root in _runtime_roots():
        candidates.extend([root / "tor", root / "tor.exe"])
    candidates.extend([Path("/opt/homebrew/bin/tor"), Path("/usr/local/bin/tor"), Path("/usr/bin/tor")])
    for candidate in candidates:
        if _is_executable_file(candidate):
            return str(candidate)
    found = shutil.which("tor") or shutil.which("tor.exe")
    if found:
        return found
    raise RuntimeError("Tor executable not found")


def _stop_process(process: Any) -> None:
    if process is None:
        return
    try:
        process.terminate()
        process.wait(timeout=5)
    except Exception:
        try:
            process.kill()
            process.wait(timeout=3)
        except Exception:
            pass


def _tor_runtime_status_locked() -> tuple[str, Optional[str]]:
    controller = tor_controller
    process = tor_process
    if controller is None and process is None:
        return "stopped", None
    if controller is None or process is None:
        return "failed", "Tor process state is incomplete"
    try:
        if process.poll() is not None:
            return "failed", "Tor process is no longer running"
    except Exception:
        return "failed", "Tor process status is unavailable"
    try:
        if not controller.is_alive():
            return "failed", "Tor control connection is no longer alive"
    except Exception:
        return "failed", "Tor control connection status is unavailable"
    return "ready", None


def _tor_runtime_status() -> tuple[str, Optional[str]]:
    with state_lock:
        return _tor_runtime_status_locked()


def start_tor() -> Controller:
    global tor_controller, tor_process, active_service_id, active_local_port
    global active_socks_port, _tor_data_dir, _tor_generation
    with state_lock:
        status, _ = _tor_runtime_status_locked()
        if status == "ready" and tor_controller is not None:
            return tor_controller
        stale_controller, stale_process, stale_data_dir = (
            tor_controller,
            tor_process,
            _tor_data_dir,
        )
        tor_controller = None
        tor_process = None
        active_service_id = None
        active_local_port = None
        active_socks_port = None
        _tor_data_dir = None
        if stale_controller is not None:
            try:
                stale_controller.close()
            except Exception:
                pass
        _stop_process(stale_process)
        if stale_data_dir:
            shutil.rmtree(stale_data_dir, ignore_errors=True)
        control_port = _pick_random_port()
        active_socks_port = _pick_random_port()
        _tor_data_dir = tempfile.mkdtemp(prefix="mutinychat-tor-")
        command = _resolve_tor_cmd()
        try:
            tor_process = stem.process.launch_tor_with_config(
                config={"ControlPort": str(control_port), "SocksPort": str(active_socks_port), "DataDirectory": _tor_data_dir},
                take_ownership=True,
                tor_cmd=command,
            )
            tor_controller = Controller.from_port(address="127.0.0.1", port=control_port)
            tor_controller.authenticate()
            _tor_generation += 1
            return tor_controller
        except Exception as exc:
            _stop_process(tor_process)
            tor_process = None
            tor_controller = None
            active_socks_port = None
            if _tor_data_dir:
                shutil.rmtree(_tor_data_dir, ignore_errors=True)
                _tor_data_dir = None
            raise RuntimeError(f"Failed to start Tor using '{command}': {exc}") from exc


def _reset_participant_verification(
    preserve_private_key: bool = True,
    channel_status: str = "disconnected",
    channel_error: Optional[str] = None,
) -> None:
    global _private_key, _peer_public_key, _box
    global _handshake_transcript_hash, _connection_role, _channel_status, _channel_error
    global _verification_code
    global _verification_local_confirmed, _verification_peer_confirmed
    with state_lock:
        if not preserve_private_key:
            _private_key = None
        _peer_public_key = None
        _box = None
        _handshake_transcript_hash = None
        _connection_role = None
        _channel_status = channel_status
        _channel_error = channel_error
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


def _clear_crypto(
    channel_status: str = "disconnected",
    channel_error: Optional[str] = None,
) -> None:
    _reset_participant_verification(
        preserve_private_key=False,
        channel_status=channel_status,
        channel_error=channel_error,
    )


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


def _create_candidate_box(
    value: str,
    local_private_key: PrivateKey,
    expected_public_key: Optional[bytes] = None,
) -> tuple[bytes, Box]:
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Peer public key is malformed") from exc
    if len(raw) != 32:
        raise ValueError("Peer public key has an invalid length")
    if expected_public_key is not None and not hmac.compare_digest(raw, expected_public_key):
        raise ValueError("The host key does not match the authenticated invitation")
    if hmac.compare_digest(raw, bytes(local_private_key.public_key)):
        raise ValueError("Peer public key must differ from the local public key")
    peer_public_key = bytes(raw)
    return peer_public_key, Box(local_private_key, PublicKey(peer_public_key))


def _encode_handshake_nonce(value: bytes) -> str:
    if len(value) != HANDSHAKE_NONCE_BYTES:
        raise ValueError("Handshake nonce has an invalid length")
    return base64.b64encode(value).decode("ascii")


def _decode_handshake_nonce(value: str) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Peer handshake nonce is malformed") from exc
    if len(raw) != HANDSHAKE_NONCE_BYTES:
        raise ValueError("Peer handshake nonce has an invalid length")
    if not hmac.compare_digest(_encode_handshake_nonce(raw), value):
        raise ValueError("Peer handshake nonce is not canonically encoded")
    return raw


def encrypt_message(message: str) -> str:
    with state_lock:
        box = _box
        confirmed = _channel_status == "confirmed" and handshake_event.is_set()
    if box is None or not confirmed:
        raise RuntimeError("Secure session handshake is not complete")
    return _encrypt_with_box(box, message)


def decrypt_message(value: str) -> str:
    with state_lock:
        box = _box
        confirmed = _channel_status == "confirmed" and handshake_event.is_set()
    if box is None or not confirmed:
        raise RuntimeError("Secure session handshake is not complete")
    return _decrypt_with_box(box, value)


def _encrypt_with_box(box: Box, message: str) -> str:
    return base64.b64encode(bytes(box.encrypt(message.encode()))).decode("ascii")


def _decrypt_with_box(box: Box, value: str) -> str:
    return box.decrypt(base64.b64decode(value, validate=True)).decode()


def _encrypt_candidate_payload(box: Box, payload: str) -> str:
    return base64.b64encode(bytes(box.encrypt(payload.encode("utf-8")))).decode("ascii")


def _decrypt_candidate_payload(box: Box, value: str) -> str:
    try:
        ciphertext = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Peer channel-confirmation ciphertext is malformed") from exc
    return box.decrypt(ciphertext).decode("utf-8")


def _send_frame(conn: socket.socket, frame: dict[str, Any]) -> None:
    data = (json.dumps(frame, separators=(",", ":")) + "\n").encode()
    if len(data) > MAX_FRAME_BYTES:
        raise ValueError("Peer frame is too large")
    with send_lock:
        conn.sendall(data)


def _handshake_time_remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Secure session handshake timed out")
    return remaining


def _send_handshake_frame(
    conn: socket.socket,
    frame: dict[str, Any],
    deadline: float,
) -> None:
    previous_timeout = conn.gettimeout()
    try:
        conn.settimeout(_handshake_time_remaining(deadline))
        _send_frame(conn, frame)
    except socket.timeout as exc:
        raise TimeoutError("Secure session handshake timed out") from exc
    finally:
        conn.settimeout(previous_timeout)


def _receive_handshake_frame(conn: socket.socket, deadline: float) -> dict[str, Any]:
    previous_timeout = conn.gettimeout()
    data = bytearray()
    try:
        while True:
            try:
                conn.settimeout(_handshake_time_remaining(deadline))
                chunk = conn.recv(1)
            except socket.timeout as exc:
                raise TimeoutError("Secure session handshake timed out") from exc
            if not chunk:
                raise ConnectionError("Peer closed before the secure session handshake completed")
            if chunk == b"\n":
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


def _expect_handshake_frame(
    conn: socket.socket,
    expected_type: str,
    deadline: float,
) -> dict[str, Any]:
    frame = _receive_handshake_frame(conn, deadline)
    kind = str(frame.get("type", ""))
    if kind == "error":
        raise RuntimeError(str(frame.get("message", "Peer refused the connection")))
    if kind != expected_type:
        raise ValueError(
            f"Expected peer {expected_type} frame, received {kind or '<empty>'}"
        )
    return frame


class StalePeerSessionError(ConnectionError):
    """Raised when work continues after its socket no longer owns the peer session."""


def _is_peer_session_owner_locked(conn: socket.socket, generation: int) -> bool:
    return active_peer_socket is conn and _active_peer_generation == generation


def _is_peer_session_owner(conn: socket.socket, generation: int) -> bool:
    with peer_lock:
        return _is_peer_session_owner_locked(conn, generation)


def _require_peer_session_owner(conn: socket.socket, generation: int) -> None:
    if not _is_peer_session_owner(conn, generation):
        raise StalePeerSessionError("Peer session is no longer active")


def _reset_owned_participant_verification(
    conn: socket.socket,
    generation: int,
    *,
    channel_status: str,
    channel_error: Optional[str] = None,
) -> bool:
    with peer_lock:
        if not _is_peer_session_owner_locked(conn, generation):
            return False
        _reset_participant_verification(
            preserve_private_key=True,
            channel_status=channel_status,
            channel_error=channel_error,
        )
        return True


def _fail_channel_handshake(conn: socket.socket, generation: int, exc: Exception) -> bool:
    return _reset_owned_participant_verification(
        conn,
        generation,
        channel_status="failed",
        channel_error=_friendly_error(exc),
    )


def _perform_handshake(
    conn: socket.socket,
    mode: str,
    generation: int,
    expected_host_public_key: Optional[bytes] = None,
) -> None:
    global _peer_public_key, _box, _handshake_transcript_hash, _connection_role
    global _channel_status, _channel_error
    global _verification_code
    if mode not in {"host", "guest"}:
        raise ValueError("Handshake mode must be host or guest")
    with peer_lock:
        if not _is_peer_session_owner_locked(conn, generation):
            raise StalePeerSessionError("Peer session is no longer active")
        _reset_participant_verification(
            preserve_private_key=True,
            channel_status="pending",
        )
        with state_lock:
            if _private_key is None:
                raise RuntimeError("Local session key is unavailable")
            local_private_key = _private_key
            room = dict(_active_room or {})
    onion = str(room.get("onion_address", "")).strip().lower()
    if not onion:
        exc = RuntimeError("Active room is missing its onion address")
        _fail_channel_handshake(conn, generation, exc)
        raise exc

    peer_role = "guest" if mode == "host" else "host"
    deadline = time.monotonic() + HANDSHAKE_TIMEOUT
    local_nonce = secrets.token_bytes(HANDSHAKE_NONCE_BYTES)
    local_challenge = secrets.token_bytes(CHANNEL_CHALLENGE_BYTES)
    local_public_key = bytes(local_private_key.public_key)

    try:
        _require_peer_session_owner(conn, generation)
        _send_handshake_frame(
            conn,
            {
                "type": "hello",
                "v": PROTOCOL_VERSION,
                "role": mode,
                "public_key": base64.b64encode(local_public_key).decode("ascii"),
                "nonce": _encode_handshake_nonce(local_nonce),
            },
            deadline,
        )
        frame = _expect_handshake_frame(conn, "hello", deadline)
        if set(frame) != {"type", "v", "role", "public_key", "nonce"}:
            raise ValueError("Peer hello frame has unexpected fields")
        if frame.get("v") != PROTOCOL_VERSION:
            if frame.get("v") == 2:
                raise ValueError(
                    "Peer protocol version 2 is incompatible; both participants must update "
                    "to protocol version 3"
                )
            raise ValueError("Peer protocol version is incompatible; update required")
        if frame.get("role") != peer_role:
            raise ValueError("Peer handshake role is invalid")
        peer_nonce = _decode_handshake_nonce(str(frame.get("nonce", "")))
        expected_key = expected_host_public_key if mode == "guest" else None
        peer_public_key, candidate_box = _create_candidate_box(
            str(frame.get("public_key", "")),
            local_private_key,
            expected_key,
        )
        if mode == "host":
            host_key, guest_key = local_public_key, peer_public_key
            host_nonce, guest_nonce = local_nonce, peer_nonce
        else:
            host_key, guest_key = peer_public_key, local_public_key
            host_nonce, guest_nonce = peer_nonce, local_nonce
        transcript_hash = derive_handshake_transcript_hash(
            host_key,
            guest_key,
            onion,
            host_nonce,
            guest_nonce,
        )

        challenge_ciphertext = _encrypt_candidate_payload(
            candidate_box,
            build_channel_challenge_payload(mode, transcript_hash, local_challenge),
        )
        _require_peer_session_owner(conn, generation)
        _send_handshake_frame(
            conn,
            {"type": "channel_challenge", "ciphertext": challenge_ciphertext},
            deadline,
        )
        challenge_frame = _expect_handshake_frame(conn, "channel_challenge", deadline)
        if set(challenge_frame) != {"type", "ciphertext"}:
            raise ValueError("Peer channel challenge frame has unexpected fields")
        peer_challenge = parse_channel_challenge_payload(
            _decrypt_candidate_payload(
                candidate_box, str(challenge_frame.get("ciphertext", ""))
            ),
            peer_role,
            transcript_hash,
        )

        response_ciphertext = _encrypt_candidate_payload(
            candidate_box,
            build_channel_response_payload(mode, transcript_hash, peer_challenge),
        )
        _require_peer_session_owner(conn, generation)
        _send_handshake_frame(
            conn,
            {"type": "channel_response", "ciphertext": response_ciphertext},
            deadline,
        )
        response_frame = _expect_handshake_frame(conn, "channel_response", deadline)
        if set(response_frame) != {"type", "ciphertext"}:
            raise ValueError("Peer channel response frame has unexpected fields")
        peer_response = parse_channel_response_payload(
            _decrypt_candidate_payload(
                candidate_box, str(response_frame.get("ciphertext", ""))
            ),
            peer_role,
            transcript_hash,
        )
        if not hmac.compare_digest(peer_response, local_challenge):
            raise ValueError("Peer channel response does not answer the local challenge")

        verification_code = derive_safety_code(
            host_key,
            guest_key,
            onion,
            host_nonce,
            guest_nonce,
        )
        with peer_lock:
            if not _is_peer_session_owner_locked(conn, generation):
                raise StalePeerSessionError("Peer session is no longer active")
            with state_lock:
                if _private_key is not local_private_key:
                    raise StalePeerSessionError("Peer session key is no longer active")
                _peer_public_key = peer_public_key
                _box = candidate_box
                _handshake_transcript_hash = transcript_hash
                _connection_role = mode
                _verification_code = verification_code
                _channel_status = "confirmed"
                _channel_error = None
                handshake_event.set()
    except Exception as exc:
        _fail_channel_handshake(conn, generation, exc)
        raise


def _mark_verified_if_complete(conn: socket.socket, generation: int) -> bool:
    became_verified = False
    with peer_lock:
        if not _is_peer_session_owner_locked(conn, generation):
            return False
        with state_lock:
            if _verification_local_confirmed and _verification_peer_confirmed:
                if not verification_event.is_set():
                    verification_event.set()
                    became_verified = True
            verified = verification_event.is_set()
    if became_verified:
        _queue_frontend_control("peer_verified")
    return verified


def _handle_peer_verification(conn: socket.socket, generation: int, ciphertext: str) -> None:
    global _verification_peer_confirmed
    with peer_lock:
        if not _is_peer_session_owner_locked(conn, generation):
            raise StalePeerSessionError("Peer session is no longer active")
        with state_lock:
            box = _box
            code = _verification_code
            role = _connection_role
            transcript_hash = _handshake_transcript_hash
            confirmed = _channel_status == "confirmed" and handshake_event.is_set()
    if box is None or not confirmed or not code or not role or transcript_hash is None:
        raise RuntimeError("Participant verification state is unavailable")
    plaintext = _decrypt_with_box(box, ciphertext)
    peer_role = "guest" if role == "host" else "host"
    validate_confirmation_payload(plaintext, code, peer_role, transcript_hash)
    with peer_lock:
        if not _is_peer_session_owner_locked(conn, generation):
            raise StalePeerSessionError("Peer session is no longer active")
        with state_lock:
            if _box is not box or _handshake_transcript_hash != transcript_hash:
                raise StalePeerSessionError("Peer session cryptographic state changed")
            _verification_peer_confirmed = True
    _mark_verified_if_complete(conn, generation)


def confirm_verification() -> dict[str, Any]:
    global _verification_local_confirmed
    with peer_lock:
        conn = active_peer_socket
        generation = _active_peer_generation
        with state_lock:
            code = _verification_code
            role = _connection_role
            transcript_hash = _handshake_transcript_hash
            box = _box
            encrypted = (
                _channel_status == "confirmed"
                and box is not None
                and handshake_event.is_set()
            )
    if (
        conn is None
        or generation is None
        or not encrypted
        or box is None
        or not code
        or not role
        or transcript_hash is None
    ):
        return {"status": "error", "error": "No encrypted peer session is ready for verification"}

    try:
        ciphertext = _encrypt_with_box(
            box, build_confirmation_payload(code, role, transcript_hash)
        )
        _send_frame(conn, {"type": "verification", "ciphertext": ciphertext})
    except (OSError, ValueError, RuntimeError) as exc:
        _fail_active_channel(conn, generation, exc)
        return {"status": "error", "error": _friendly_error(exc)}

    with peer_lock:
        if not _is_peer_session_owner_locked(conn, generation):
            return {"status": "error", "error": "Peer session is no longer active"}
        with state_lock:
            if _box is not box or _handshake_transcript_hash != transcript_hash:
                return {"status": "error", "error": "Peer session is no longer active"}
            _verification_local_confirmed = True
    verified = _mark_verified_if_complete(conn, generation)
    return {
        "status": "verified" if verified else "waiting_for_peer",
        "verified": verified,
        "verification_code": code,
    }


def _chat_event(message: str) -> dict[str, str]:
    return {"kind": "chat", "text": message}


def _control_event(name: str) -> dict[str, str]:
    if name not in FRONTEND_CONTROL_EVENTS:
        raise ValueError(f"Unsupported frontend control event: {name}")
    return {"kind": "control", "event": name}


def _serialized_event_size(event: dict[str, str]) -> int:
    return len(json.dumps(event, separators=(",", ":")).encode("utf-8"))


def _clear_frontend_messages() -> None:
    global _inbox_bytes
    with inbox_lock:
        _inbox.clear()
        _inbox_bytes = 0


def _queue_frontend_event(event: dict[str, str]) -> bool:
    global _inbox_bytes
    serialized_bytes = _serialized_event_size(event)
    if serialized_bytes > MAX_FRONTEND_QUEUE_ITEM_BYTES:
        return False
    with inbox_lock:
        if (
            len(_inbox) >= MAX_FRONTEND_QUEUE_MESSAGES
            or _inbox_bytes + serialized_bytes > MAX_FRONTEND_QUEUE_BYTES
        ):
            return False
        _inbox.append((event, serialized_bytes))
        _inbox_bytes += serialized_bytes
        return True


def _queue_frontend_message(message: str) -> bool:
    return _queue_frontend_event(_chat_event(message))


def _queue_frontend_control(name: str) -> bool:
    return _queue_frontend_event(_control_event(name))


def _claim_active_peer_socket(conn: socket.socket) -> Optional[int]:
    global active_peer_socket, _active_peer_generation, _peer_generation
    with peer_lock:
        if stop_event.is_set():
            return None
        if active_peer_socket is not None and active_peer_socket is not conn:
            return None
        if active_peer_socket is conn and _active_peer_generation is not None:
            return _active_peer_generation
        _peer_generation += 1
        active_peer_socket = conn
        _active_peer_generation = _peer_generation
        return _active_peer_generation


def _close_socket(sock: Optional[socket.socket]) -> None:
    if sock is None:
        return
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


def _fail_active_channel(conn: socket.socket, generation: int, exc: Exception) -> bool:
    global active_peer_socket, guest_socket, _active_peer_generation
    global _peer_count, _active_room, _connection_mode
    failed_owned_session = False
    with peer_lock:
        if _is_peer_session_owner_locked(conn, generation):
            with state_lock:
                if _connection_mode == "host" and _active_room is not None:
                    _peer_count = 1
                    _reset_participant_verification(
                        preserve_private_key=True,
                        channel_status="failed",
                        channel_error=_friendly_error(exc),
                    )
                elif _connection_mode == "guest":
                    _peer_count = 0
                    _active_room = None
                    _connection_mode = None
                    _clear_crypto("failed", _friendly_error(exc))
                else:
                    _reset_participant_verification(
                        preserve_private_key=True,
                        channel_status="failed",
                        channel_error=_friendly_error(exc),
                    )
            active_peer_socket = None
            _active_peer_generation = None
            if guest_socket is conn:
                guest_socket = None
            failed_owned_session = True
    _close_socket(conn)
    if failed_owned_session and not stop_event.is_set():
        _queue_frontend_control("channel_failed")
    return failed_owned_session


def _process_peer_frame(conn: socket.socket, generation: int, raw: bytes) -> bool:
    if not _is_peer_session_owner(conn, generation):
        return False
    try:
        frame = json.loads(raw.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Peer sent malformed JSON") from exc
    if not isinstance(frame, dict):
        raise ValueError("Peer frame must be an object")
    kind = str(frame.get("type", ""))
    if kind in {"hello", "channel_challenge", "channel_response"}:
        raise ValueError(f"Unexpected {kind} frame after the handshake completed")
    if kind == "verification":
        _handle_peer_verification(conn, generation, str(frame.get("ciphertext", "")))
        return True
    if kind == "message":
        with peer_lock:
            if not _is_peer_session_owner_locked(conn, generation):
                return False
            with state_lock:
                box = _box
                verified = verification_event.is_set()
                confirmed = _channel_status == "confirmed" and handshake_event.is_set()
        if box is None or not confirmed or not verified:
            raise RuntimeError("Participant verification is required before messaging")
        ciphertext = str(frame.get("ciphertext", ""))
        if len(ciphertext) > MAX_ENCRYPTED_MESSAGE_CHARS:
            raise ValueError("Peer chat message is too large")
        plaintext = _decrypt_with_box(box, ciphertext)
        if len(plaintext.encode("utf-8")) > MAX_CHAT_MESSAGE_BYTES:
            raise ValueError("Peer chat message is too large")
        with peer_lock:
            if not _is_peer_session_owner_locked(conn, generation):
                return False
            if not _queue_frontend_message(plaintext):
                _clear_frontend_messages()
                raise RuntimeError("Peer exceeded pending message capacity")
        return True
    if kind == "disconnect":
        return False
    if kind == "error":
        raise RuntimeError(str(frame.get("message", "Peer refused the connection")))
    raise ValueError(f"Unsupported peer frame type: {kind or '<empty>'}")


def _read_socket_messages(conn: socket.socket, generation: int) -> None:
    conn.settimeout(1)
    buffer = bytearray()
    rate_window_started = time.monotonic()
    rate_window_frames = 0
    rate_window_bytes = 0
    while not stop_event.is_set():
        if not _is_peer_session_owner(conn, generation):
            return
        try:
            chunk = conn.recv(4096)
            if not chunk:
                return
            buffer.extend(chunk)
            if len(buffer) > MAX_FRAME_BYTES and b"\n" not in buffer:
                raise ValueError("Peer frame is too large")
            while b"\n" in buffer:
                raw, _, remainder = buffer.partition(b"\n")
                buffer = bytearray(remainder)
                if not raw.strip():
                    continue
                if len(raw) > MAX_APPLICATION_FRAME_BYTES:
                    raise ValueError("Peer application frame is too large")
                now = time.monotonic()
                if now - rate_window_started >= 1:
                    rate_window_started = now
                    rate_window_frames = 0
                    rate_window_bytes = 0
                rate_window_frames += 1
                rate_window_bytes += len(raw)
                if (
                    rate_window_frames > MAX_INBOUND_FRAMES_PER_SECOND
                    or rate_window_bytes > MAX_INBOUND_FRAME_BYTES_PER_SECOND
                ):
                    raise RuntimeError("Peer message rate limit exceeded")
                if not _process_peer_frame(conn, generation, bytes(raw)):
                    return
        except socket.timeout:
            continue
        except (OSError, ValueError, RuntimeError, binascii.Error, nacl.exceptions.CryptoError) as exc:
            if not stop_event.is_set():
                failed_owned_session = _reset_owned_participant_verification(
                    conn,
                    generation,
                    channel_status="failed",
                    channel_error=_friendly_error(exc),
                )
                if failed_owned_session:
                    _queue_frontend_message(
                        f"Secure connection closed: {_friendly_error(exc)}"
                    )
            return


def _release_failed_host_connection(
    conn: socket.socket,
    generation: int,
    exc: Exception,
) -> bool:
    global active_peer_socket, _active_peer_generation, _peer_count
    released_owned_session = False
    with peer_lock:
        if _is_peer_session_owner_locked(conn, generation):
            _reset_participant_verification(
                preserve_private_key=True,
                channel_status="failed",
                channel_error=_friendly_error(exc),
            )
            with state_lock:
                if _connection_mode == "host" and _active_room is not None:
                    _peer_count = 1
            active_peer_socket = None
            _active_peer_generation = None
            released_owned_session = True
    _close_socket(conn)
    if released_owned_session and not stop_event.is_set():
        _queue_frontend_message(f"Secure connection attempt failed: {_friendly_error(exc)}")
    return released_owned_session


def _peer_session(
    conn: socket.socket,
    mode: str,
    generation: int,
    handshake_complete: bool = False,
    expected_host_public_key: Optional[bytes] = None,
) -> None:
    global active_peer_socket, guest_socket, _active_peer_generation
    global _peer_count, _active_room, _connection_mode
    try:
        if not handshake_complete:
            _perform_handshake(conn, mode, generation, expected_host_public_key)
        _read_socket_messages(conn, generation)
    finally:
        notification: Optional[str] = None
        with peer_lock:
            if _is_peer_session_owner_locked(conn, generation):
                with state_lock:
                    failed = _channel_status == "failed"
                    final_channel_error = _channel_error if failed else None
                    final_channel_status = "failed" if failed else "disconnected"
                    if mode == "host" and _connection_mode == "host" and _active_room is not None:
                        _peer_count = 1
                        _reset_participant_verification(
                            preserve_private_key=True,
                            channel_status=final_channel_status,
                            channel_error=final_channel_error,
                        )
                        notification = "channel_failed" if failed else "peer_left"
                    elif mode == "guest" and _connection_mode == "guest":
                        _peer_count = 0
                        _active_room = None
                        _connection_mode = None
                        _clear_crypto(final_channel_status, final_channel_error)
                        notification = "channel_failed" if failed else "room_deleted"
                active_peer_socket = None
                _active_peer_generation = None
                if guest_socket is conn:
                    guest_socket = None
        _close_socket(conn)
        if notification is not None and not stop_event.is_set():
            _queue_frontend_control(notification)


def _handle_guest(conn: socket.socket) -> None:
    global _peer_count
    generation = _claim_active_peer_socket(conn)
    if generation is None:
        try:
            _send_frame(conn, {"type": "error", "message": "This room already has two participants"})
        finally:
            _close_socket(conn)
        return

    try:
        _perform_handshake(conn, "host", generation)
    except Exception as exc:
        _release_failed_host_connection(conn, generation, exc)
        return

    with peer_lock:
        if not _is_peer_session_owner_locked(conn, generation):
            _close_socket(conn)
            return
        with state_lock:
            _peer_count = 2
        _queue_frontend_control("peer_joined")
    _peer_session(conn, "host", generation, handshake_complete=True)


def _listener_loop(server: socket.socket) -> None:
    while not stop_event.is_set():
        try:
            conn, _ = server.accept()
        except socket.timeout:
            continue
        except OSError:
            return
        threading.Thread(target=_handle_guest, args=(conn,), daemon=True).start()


def create_hidden_service(room_name: str) -> dict[str, Any]:
    del room_name
    global active_service_id, active_local_port
    controller = start_tor()
    local_port = _pick_random_port()
    service = controller.create_ephemeral_hidden_service(
        {DEFAULT_ONION_PORT: f"127.0.0.1:{local_port}"}, await_publication=True
    )
    active_service_id = service.service_id
    active_local_port = local_port
    return {"onion_address": f"{service.service_id}.onion", "port": DEFAULT_ONION_PORT}


def start_listening(port: Optional[int] = None) -> dict[str, Any]:
    global listener_thread, listener_socket
    with state_lock:
        if _connection_mode != "host" or _active_room is None:
            raise RuntimeError("Create a room before starting the listener")
        if listener_thread is not None and listener_thread.is_alive():
            return {"status": "listening", "port": active_local_port}
        listen_port = port or active_local_port
    if not listen_port:
        raise RuntimeError("Room listener port is unavailable")
    server = socket.socket()
    try:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", listen_port))
        server.listen(1)
        server.settimeout(1)
    except Exception:
        server.close()
        raise
    stop_event.clear()
    listener_socket = server
    listener_thread = threading.Thread(target=_listener_loop, args=(server,), daemon=True)
    listener_thread.start()
    return {"status": "listening", "port": listen_port}


def _extract_onion_host(value: str) -> str:
    match = ONION_V3_RE.search(value.strip())
    if not match:
        raise ValueError("No valid .onion host found in input")
    return match.group(1).lower()


def join_room(invitation: str, port: int) -> dict[str, Any]:
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
    except Exception as exc:
        _close_socket(client)
        close_room()
        _clear_crypto("failed", _friendly_error(exc))
        raise
    generation = _claim_active_peer_socket(client)
    if generation is None:
        _close_socket(client)
        close_room()
        raise RuntimeError("Another peer connection is active")
    with peer_lock:
        if not _is_peer_session_owner_locked(client, generation):
            _close_socket(client)
            raise StalePeerSessionError("Peer session ended before join setup completed")
        guest_socket = client
        with state_lock:
            _peer_count = 1
            _connection_mode = "guest"
            _active_room = {
                "mode": "guest",
                "onion_address": onion_host,
                "port": port,
                "expected_host_public_key": authenticated_invite.host_public_key,
                "tor_generation": _tor_generation,
            }
    try:
        _perform_handshake(
            client,
            "guest",
            generation,
            authenticated_invite.host_public_key,
        )
    except Exception as exc:
        if not _is_peer_session_owner(client, generation):
            _close_socket(client)
            raise
        close_room()
        _clear_crypto("failed", _friendly_error(exc))
        raise
    with peer_lock:
        if not _is_peer_session_owner_locked(client, generation):
            raise StalePeerSessionError("Peer session ended before join completed")
        with state_lock:
            _peer_count = 2
            code = _verification_code
    threading.Thread(
        target=_peer_session,
        args=(client, "guest", generation, True, authenticated_invite.host_public_key),
        daemon=True,
    ).start()
    return {
        "status": "connected",
        "onion_address": onion_host,
        "port": port,
        "channel_status": "confirmed",
        "encrypted": handshake_event.is_set(),
        "identity_status": "unverified",
        "verified": False,
        "verification_code": code,
        "protocol_version": PROTOCOL_VERSION,
    }


def send_message(text: str) -> dict[str, str]:
    payload = text.strip()
    if not payload:
        return {"status": "error", "error": "Message cannot be empty"}
    if len(payload.encode("utf-8")) > MAX_CHAT_MESSAGE_BYTES:
        return {
            "status": "error",
            "error": f"Message exceeds the {MAX_CHAT_MESSAGE_BYTES // 1024} KiB limit",
        }
    with peer_lock:
        conn = active_peer_socket
        generation = _active_peer_generation
        with state_lock:
            box = _box
            confirmed = _channel_status == "confirmed" and handshake_event.is_set()
            verified = verification_event.is_set()
    if conn is None or generation is None:
        return {"status": "error", "error": "No active peer socket"}
    if box is None or not confirmed or not verified:
        return {
            "status": "error",
            "error": "Compare and confirm the participant safety code before sending messages",
        }
    try:
        _send_frame(conn, {"type": "message", "ciphertext": _encrypt_with_box(box, payload)})
        if not _is_peer_session_owner(conn, generation):
            return {"status": "error", "error": "Peer session is no longer active"}
        return {"status": "sent"}
    except (OSError, ValueError, RuntimeError) as exc:
        _fail_active_channel(conn, generation, exc)
        return {"status": "error", "error": _friendly_error(exc)}


def close_room() -> dict[str, str]:
    global tor_controller, tor_process, active_service_id, active_local_port, active_socks_port
    global listener_thread, listener_socket, guest_socket, active_peer_socket, _tor_data_dir
    global _active_peer_generation, _peer_generation
    global _peer_count, _active_room, _connection_mode
    stop_event.set()
    with peer_lock:
        _peer_generation += 1
        peer, guest = active_peer_socket, guest_socket
        active_peer_socket = None
        _active_peer_generation = None
        guest_socket = None
    if peer is not None:
        try:
            _send_frame(peer, {"type": "disconnect"})
        except Exception:
            pass
    _close_socket(peer)
    if guest is not peer:
        _close_socket(guest)
    server, thread = listener_socket, listener_thread
    listener_socket = None
    listener_thread = None
    _close_socket(server)
    if thread is not None and thread.is_alive() and thread is not threading.current_thread():
        thread.join(timeout=2)
    controller, process, service_id, data_dir = tor_controller, tor_process, active_service_id, _tor_data_dir
    tor_controller = None
    tor_process = None
    active_service_id = None
    active_local_port = None
    active_socks_port = None
    _tor_data_dir = None
    _peer_count = 0
    _active_room = None
    _connection_mode = None
    _clear_crypto()
    if controller is not None and service_id is not None:
        try:
            controller.remove_ephemeral_hidden_service(service_id)
        except Exception:
            pass
    if controller is not None:
        try:
            controller.close()
        except Exception:
            pass
    _stop_process(process)
    if data_dir:
        shutil.rmtree(data_dir, ignore_errors=True)
    _clear_frontend_messages()
    return {"status": "closed"}


def build_room_response(room_name: str) -> dict[str, Any]:
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
        "tor_generation": _tor_generation,
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


def poll_messages() -> dict[str, Any]:
    global _inbox_bytes
    with inbox_lock:
        events: list[dict[str, str]] = []
        event_bytes = 0
        while _inbox and len(events) < MAX_POLL_MESSAGES:
            event, serialized_bytes = _inbox[0]
            if events and event_bytes + serialized_bytes > MAX_POLL_MESSAGE_BYTES:
                break
            _inbox.popleft()
            _inbox_bytes -= serialized_bytes
            events.append(event)
            event_bytes += serialized_bytes
        events_pending = len(_inbox)
    with state_lock:
        tor_status, tor_error = _tor_runtime_status_locked()
        tor_route_active = bool(
            tor_status == "ready"
            and _active_room is not None
            and _active_room.get("tor_generation") == _tor_generation
            and _connection_mode in {"host", "guest"}
        )
        channel_status = _channel_status
        encrypted = (
            channel_status == "confirmed"
            and _box is not None
            and handshake_event.is_set()
        )
        verified = encrypted and verification_event.is_set()
        code = _verification_code
        local_confirmed = _verification_local_confirmed
        peer_confirmed = _verification_peer_confirmed
        channel_error = _channel_error
        if not encrypted:
            identity_status = "unavailable"
        elif verified:
            identity_status = "verified"
        elif local_confirmed or peer_confirmed:
            identity_status = "pending"
        else:
            identity_status = "unverified"
    return {
        "events": events,
        "events_pending": events_pending,
        "channel_status": channel_status,
        "channel_error": channel_error,
        "encrypted": encrypted,
        "identity_status": identity_status,
        "verified": verified,
        "verification_code": code if encrypted else None,
        "verification_local_confirmed": local_confirmed if encrypted else False,
        "verification_peer_confirmed": peer_confirmed if encrypted else False,
        "protocol_version": PROTOCOL_VERSION,
        "tor_status": tor_status,
        "tor_error": tor_error,
        "tor_route_active": tor_route_active,
        "peer_count": _peer_count,
    }


def handle_json_command(payload: dict[str, Any]) -> dict[str, Any]:
    command = str(payload.get("cmd", "")).strip()
    if not command:
        return {"error": "Command is required"}
    try:
        if command == "ping":
            return {"status": "MutinyChat backend alive"}
        if command == "create_room":
            name = str(payload.get("room_name", payload.get("name", ""))).strip()
            return build_room_response(name or generate_random_room_name())
        if command == "generate_random_room_name":
            return {"friendly_name": generate_random_room_name()}
        if command == "start_tor":
            start_tor()
            tor_status, tor_error = _tor_runtime_status()
            return {"status": tor_status, "tor_status": tor_status, "tor_error": tor_error}
        if command == "start_listening":
            return start_listening()
        if command == "join_room":
            address = str(payload.get("onion_address", payload.get("message", "")))
            try:
                port = int(payload.get("port", DEFAULT_ONION_PORT))
            except (TypeError, ValueError):
                port = DEFAULT_ONION_PORT
            return join_room(address, port)
        if command == "confirm_verification":
            return confirm_verification()
        if command == "send_message":
            return send_message(str(payload.get("text", payload.get("message", ""))))
        if command == "close_room":
            return close_room()
        if command == "get_peer_count":
            return {"peer_count": _peer_count}
        if command == "poll_messages":
            return poll_messages()
        if command == "echo":
            return {"echo": str(payload.get("message", ""))}
        return {"error": f"Unknown command: {command}"}
    except Exception as exc:
        return {"error": _friendly_error(exc)}


def run_stdio_json_loop() -> None:
    try:
        for line in sys.stdin:
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError("JSON payload must be an object")
                response = handle_json_command(payload)
            except Exception as exc:
                response = {"error": _friendly_error(exc)}
            print(json.dumps(response, separators=(",", ":")), flush=True)
    finally:
        close_room()


def main() -> None:
    args = parse_args()
    if args.stdio_json:
        run_stdio_json_loop()
        return
    if args.command:
        payload: dict[str, Any] = {"cmd": args.command}
        if args.message is not None:
            payload["message"] = args.message
        if args.room_name is not None:
            payload["room_name"] = args.room_name
        if args.onion_address is not None:
            payload["onion_address"] = args.onion_address
        if args.port is not None:
            payload["port"] = args.port
        print(json.dumps(handle_json_command(payload), separators=(",", ":")))
        return
    print(json.dumps({"status": "MutinyChat backend ready"}))


atexit.register(close_room)
if __name__ == "__main__":
    main()
