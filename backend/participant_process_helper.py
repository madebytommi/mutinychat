"""Test-only helper for exercising the protocol in independent processes."""
from __future__ import annotations

import argparse
import base64
import json
import socket
import sys
import threading
import time
from typing import Any

from nacl.public import PrivateKey

import main as backend

TEST_ONION = "a" * 56 + ".onion"
WAIT_SECONDS = 8


def _wait_for_message(expected: str) -> bool:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        messages = backend.poll_messages()["messages"]
        if expected in messages:
            return True
        time.sleep(0.02)
    return False


def _wait_for_verification() -> bool:
    return backend.verification_event.wait(WAIT_SECONDS)


def _prepare_state(role: str, conn: socket.socket, private_key: PrivateKey) -> None:
    backend.close_room()
    backend.stop_event.clear()
    backend._private_key = private_key
    backend.active_peer_socket = conn
    backend._connection_mode = role
    backend._peer_count = 2
    backend._active_room = {
        "mode": role,
        "onion_address": TEST_ONION,
        "port": backend.DEFAULT_ONION_PORT,
    }


def _start_reader(conn: socket.socket) -> threading.Thread:
    reader = threading.Thread(target=backend._read_socket_messages, args=(conn,), daemon=True)
    reader.start()
    return reader


def _result(role: str, received: str) -> dict[str, Any]:
    state = backend.poll_messages()
    return {
        "role": role,
        "encrypted": state["encrypted"],
        "verified": state["verified"],
        "verification_code": state["verification_code"],
        "received": received,
    }


def run_host(port: int) -> int:
    private_key = PrivateKey.generate()
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", port))
    listener.listen(1)
    listener.settimeout(WAIT_SECONDS)
    print(
        json.dumps(
            {
                "ready": True,
                "host_public_key": base64.b64encode(bytes(private_key.public_key)).decode("ascii"),
            },
            separators=(",", ":"),
        ),
        flush=True,
    )

    conn, _ = listener.accept()
    listener.close()
    try:
        _prepare_state("host", conn, private_key)
        backend._perform_handshake(conn, "host")
        _start_reader(conn)
        confirmation = backend.confirm_verification()
        if confirmation["status"] == "error" or not _wait_for_verification():
            raise RuntimeError("Host verification did not complete")
        if not _wait_for_message("guest-message"):
            raise RuntimeError("Host did not receive the guest message")
        send_result = backend.send_message("host-message")
        if send_result != {"status": "sent"}:
            raise RuntimeError(f"Host message failed: {send_result}")
        print(json.dumps(_result("host", "guest-message"), separators=(",", ":")), flush=True)
        return 0
    finally:
        backend.close_room()


def run_guest(port: int, expected_host_key_b64: str) -> int:
    private_key = PrivateKey.generate()
    expected_host_key = base64.b64decode(expected_host_key_b64, validate=True)
    conn = socket.create_connection(("127.0.0.1", port), timeout=WAIT_SECONDS)
    try:
        _prepare_state("guest", conn, private_key)
        backend._perform_handshake(conn, "guest", expected_host_key)
        _start_reader(conn)
        confirmation = backend.confirm_verification()
        if confirmation["status"] == "error" or not _wait_for_verification():
            raise RuntimeError("Guest verification did not complete")
        send_result = backend.send_message("guest-message")
        if send_result != {"status": "sent"}:
            raise RuntimeError(f"Guest message failed: {send_result}")
        if not _wait_for_message("host-message"):
            raise RuntimeError("Guest did not receive the host message")
        print(json.dumps(_result("guest", "host-message"), separators=(",", ":")), flush=True)
        return 0
    finally:
        backend.close_room()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("host", "guest"), required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--expected-host-key")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.role == "host":
        return run_host(args.port)
    if not args.expected_host_key:
        raise ValueError("Guest requires the expected host public key")
    return run_guest(args.port, args.expected_host_key)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")), file=sys.stderr, flush=True)
        raise
