"""Windows sidecar entrypoint with a deterministic peer handshake.

The core backend remains in main.py. This entrypoint replaces only the peer
connection lifecycle before starting the existing stdio/CLI command server.
"""
from __future__ import annotations

import json
import socket
import threading
from typing import Any

import main as backend

CONNECT_TIMEOUT = 60
HANDSHAKE_TIMEOUT = 30


def _receive_handshake_frame(conn: socket.socket) -> dict[str, Any]:
    """Read exactly one newline-delimited frame without consuming chat data."""
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
            if len(data) > backend.MAX_FRAME_BYTES:
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


def _perform_handshake(conn: socket.socket) -> None:
    """Exchange ephemeral public keys before either peer is marked connected."""
    backend._send_frame(conn, {"type": "hello", "public_key": backend._public_key_b64()})
    frame = _receive_handshake_frame(conn)
    kind = str(frame.get("type", ""))
    if kind == "error":
        raise RuntimeError(str(frame.get("message", "Peer refused the connection")))
    if kind != "hello":
        raise ValueError(f"Expected peer hello frame, received {kind or '<empty>'}")
    backend._install_peer_public_key(str(frame.get("public_key", "")))
    if backend._box is None or not backend.handshake_event.is_set():
        raise RuntimeError("Secure session handshake did not establish encryption")


def _peer_session(conn: socket.socket, mode: str, handshake_complete: bool = False) -> None:
    """Run the message reader and reliably reset state when the peer leaves."""
    try:
        if not handshake_complete:
            _perform_handshake(conn)
        backend._read_socket_messages(conn)
    finally:
        with backend.peer_lock:
            if backend.active_peer_socket is conn:
                backend.active_peer_socket = None
            if backend.guest_socket is conn:
                backend.guest_socket = None
        backend._close_socket(conn)
        with backend.state_lock:
            if mode == "host" and backend._connection_mode == "host" and backend._active_room is not None:
                backend._peer_count = 1
                backend._reset_crypto()
                if not backend.stop_event.is_set():
                    backend._queue_frontend_message("__peer_left__")
            elif mode == "guest" and backend._connection_mode == "guest":
                backend._peer_count = 0
                backend._active_room = None
                backend._connection_mode = None
                backend._clear_crypto()
                if not backend.stop_event.is_set():
                    backend._queue_frontend_message("room_deleted")


def _release_failed_host_connection(conn: socket.socket, exc: Exception) -> None:
    with backend.peer_lock:
        if backend.active_peer_socket is conn:
            backend.active_peer_socket = None
    backend._close_socket(conn)
    with backend.state_lock:
        if backend._connection_mode == "host" and backend._active_room is not None:
            backend._peer_count = 1
            backend._reset_crypto()
    if not backend.stop_event.is_set():
        backend._queue_frontend_message(
            f"Secure connection attempt failed: {backend._friendly_error(exc)}"
        )


def _handle_guest(conn: socket.socket) -> None:
    """Accept one guest, but report 2/2 only after encryption is established."""
    if not backend._claim_active_peer_socket(conn):
        try:
            backend._send_frame(
                conn,
                {"type": "error", "message": "This room already has two participants"},
            )
        finally:
            backend._close_socket(conn)
        return

    backend._reset_crypto()
    try:
        _perform_handshake(conn)
    except Exception as exc:
        _release_failed_host_connection(conn, exc)
        return

    with backend.state_lock:
        backend._peer_count = 2
    backend._queue_frontend_message("__peer_joined__")
    _peer_session(conn, "host", handshake_complete=True)


def join_room(onion_address: str, port: int) -> dict[str, Any]:
    """Connect through Tor and complete the key exchange synchronously."""
    onion_host = backend._extract_onion_host(onion_address)
    backend.close_room()
    backend.start_tor()
    if not backend.active_socks_port:
        raise RuntimeError("Tor SOCKS port is unavailable")

    backend._reset_crypto()
    backend.stop_event.clear()
    client = backend.socks.socksocket()
    try:
        client.set_proxy(backend.socks.SOCKS5, "127.0.0.1", backend.active_socks_port)
        client.settimeout(CONNECT_TIMEOUT)
        client.connect((onion_host, port))
        client.settimeout(1)
    except Exception:
        backend._close_socket(client)
        backend.close_room()
        raise

    if not backend._claim_active_peer_socket(client):
        backend._close_socket(client)
        backend.close_room()
        raise RuntimeError("Another peer connection is active")

    backend.guest_socket = client
    backend._peer_count = 1
    backend._connection_mode = "guest"
    backend._active_room = {
        "mode": "guest",
        "onion_address": onion_host,
        "port": port,
    }

    try:
        _perform_handshake(client)
    except Exception:
        backend.close_room()
        raise

    with backend.state_lock:
        backend._peer_count = 2
    threading.Thread(
        target=_peer_session,
        args=(client, "guest", True),
        daemon=True,
    ).start()
    return {"status": "connected", "onion_address": onion_host, "port": port}


def install() -> None:
    """Install the hardened connection functions into the core backend module."""
    backend.CONNECT_TIMEOUT = CONNECT_TIMEOUT
    backend.HANDSHAKE_TIMEOUT = HANDSHAKE_TIMEOUT
    backend._peer_session = _peer_session
    backend._handle_guest = _handle_guest
    backend.join_room = join_room


if __name__ == "__main__":
    install()
    backend.main()
