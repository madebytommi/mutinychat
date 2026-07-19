"""MutinyChat Tor peer backend and stdio JSON command server."""
from __future__ import annotations

import argparse
import atexit
import base64
import binascii
import json
import hmac
import os
import random
import re
import shutil
import socket
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Optional

from participant_auth import (
    PROTOCOL_VERSION,
    build_confirmation_payload,
    build_invite,
    derive_safety_code,
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
active_service_id: Optional[str] = None
active_local_port: Optional[int] = None
active_socks_port: Optional[int] = None
listener_thread: Optional[threading.Thread] = None
listener_socket: Optional[socket.socket] = None
guest_socket: Optional[socket.socket] = None
active_peer_socket: Optional[socket.socket] = None
_tor_data_dir: Optional[str] = None
_private_key: Optional[PrivateKey] = None
_peer_public_key: Optional[bytes] = None
_box: Optional[Box] = None
_verification_code: Optional[str] = None
_verification_local_confirmed = False
_verification_peer_confirmed = False
_peer_count = 0
_active_room: Optional[dict[str, Any]] = None
_connection_mode: Optional[str] = None
_inbox: list[str] = []

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


def _resolve_tor_cmd() -> str:
    candidates: list[Path] = []
    configured = os.environ.get("MUTINYCHAT_TOR_PATH", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())
    for root in _runtime_roots():
        candidates.extend([root / "tor", root / "tor.exe"])
    candidates.extend([Path("/opt/homebrew/bin/tor"), Path("/usr/local/bin/tor"), Path("/usr/bin/tor")])
    for candidate in candidates:
        if candidate.is_file() and (os.name == "nt" or os.access(candidate, os.X_OK)):
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


def start_tor() -> Controller:
    global tor_controller, tor_process, active_socks_port, _tor_data_dir
    with state_lock:
        if tor_controller is not None:
            return tor_controller
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
            return tor_controller
        except Exception as exc:
            _stop_process(tor_process)
            tor_process = None
            active_socks_port = None
            if _tor_data_dir:
                shutil.rmtree(_tor_data_dir, ignore_errors=True)
                _tor_data_dir = None
            raise RuntimeError(f"Failed to start Tor using '{command}': {exc}") from exc


def _reset_participant_verification(preserve_private_key: bool = True) -> None:
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


def encrypt_message(message: str) -> str:
    with state_lock:
        box = _box
    if box is None:
        raise RuntimeError("Secure session handshake is not complete")
    return base64.b64encode(bytes(box.encrypt(message.encode()))).decode("ascii")


def decrypt_message(value: str) -> str:
    with state_lock:
        box = _box
    if box is None:
        raise RuntimeError("Secure session handshake is not complete")
    return box.decrypt(base64.b64decode(value, validate=True)).decode()


def _send_frame(conn: socket.socket, frame: dict[str, Any]) -> None:
    data = (json.dumps(frame, separators=(",", ":")) + "\n").encode()
    if len(data) > MAX_FRAME_BYTES:
        raise ValueError("Peer frame is too large")
    with send_lock:
        conn.sendall(data)


def _receive_handshake_frame(conn: socket.socket) -> dict[str, Any]:
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


def _queue_frontend_message(message: str) -> None:
    with inbox_lock:
        _inbox.append(message)


def _claim_active_peer_socket(conn: socket.socket) -> bool:
    global active_peer_socket
    with peer_lock:
        if active_peer_socket is not None and active_peer_socket is not conn:
            return False
        active_peer_socket = conn
        return True


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


def _process_peer_frame(conn: socket.socket, raw: bytes) -> bool:
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


def _read_socket_messages(conn: socket.socket) -> None:
    conn.settimeout(1)
    buffer = bytearray()
    while not stop_event.is_set():
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
                if raw.strip() and not _process_peer_frame(conn, bytes(raw)):
                    return
        except socket.timeout:
            continue
        except (OSError, ValueError, RuntimeError, binascii.Error, nacl.exceptions.CryptoError) as exc:
            if not stop_event.is_set():
                _queue_frontend_message(f"Secure connection closed: {_friendly_error(exc)}")
            return


def _release_failed_host_connection(conn: socket.socket, exc: Exception) -> None:
    global active_peer_socket, _peer_count
    with peer_lock:
        if active_peer_socket is conn:
            active_peer_socket = None
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


def send_message(text: str) -> dict[str, str]:
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


def close_room() -> dict[str, str]:
    global tor_controller, tor_process, active_service_id, active_local_port, active_socks_port
    global listener_thread, listener_socket, guest_socket, active_peer_socket, _tor_data_dir
    global _peer_count, _active_room, _connection_mode
    stop_event.set()
    with peer_lock:
        peer, guest = active_peer_socket, guest_socket
        active_peer_socket = None
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
    with inbox_lock:
        _inbox.clear()
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
            return {"status": "ready"}
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
