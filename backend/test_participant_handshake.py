import base64
import json
import socket
import threading
import unittest

from nacl.public import PrivateKey

import main as backend
from participant_auth import PROTOCOL_VERSION


def _read_line(sock: socket.socket) -> bytes:
    data = bytearray()
    while True:
        chunk = sock.recv(1)
        if not chunk or chunk == b"\n":
            return bytes(data)
        data.extend(chunk)


def _send_hello(
    sock: socket.socket,
    key: PrivateKey,
    *,
    version: int = PROTOCOL_VERSION,
    role: str = "host",
) -> None:
    _read_line(sock)
    frame = {
        "type": "hello",
        "v": version,
        "role": role,
        "public_key": base64.b64encode(bytes(key.public_key)).decode("ascii"),
    }
    sock.sendall((json.dumps(frame, separators=(",", ":")) + "\n").encode("utf-8"))


class ParticipantHandshakeTestCase(unittest.TestCase):
    def setUp(self):
        backend.close_room()
        backend._reset_crypto()
        backend._active_room = {
            "mode": "guest",
            "onion_address": "a" * 56 + ".onion",
        }
        backend.stop_event.clear()

    def tearDown(self):
        backend.close_room()

    def test_guest_accepts_only_the_host_key_bound_to_invitation(self):
        local, remote = socket.socketpair()
        expected_host = PrivateKey.generate()
        thread = threading.Thread(
            target=_send_hello,
            args=(remote, expected_host),
        )
        thread.start()
        try:
            backend._perform_handshake(
                local,
                "guest",
                bytes(expected_host.public_key),
            )
            state = backend.poll_messages()
            self.assertTrue(state["encrypted"])
            self.assertFalse(state["verified"])
            self.assertRegex(
                state["verification_code"],
                r"^\d{5} \d{5} \d{5} \d{5}$",
            )
        finally:
            local.close()
            remote.close()
            thread.join(timeout=2)

    def test_guest_rejects_substituted_host_key(self):
        local, remote = socket.socketpair()
        expected_host = PrivateKey.generate()
        attacker = PrivateKey.generate()
        thread = threading.Thread(target=_send_hello, args=(remote, attacker))
        thread.start()
        try:
            with self.assertRaisesRegex(ValueError, "does not match"):
                backend._perform_handshake(
                    local,
                    "guest",
                    bytes(expected_host.public_key),
                )
            self.assertFalse(backend.handshake_event.is_set())
            self.assertFalse(backend.verification_event.is_set())
        finally:
            local.close()
            remote.close()
            thread.join(timeout=2)

    def test_guest_rejects_incompatible_protocol_version(self):
        local, remote = socket.socketpair()
        expected_host = PrivateKey.generate()
        thread = threading.Thread(
            target=_send_hello,
            args=(remote, expected_host),
            kwargs={"version": PROTOCOL_VERSION + 1},
        )
        thread.start()
        try:
            with self.assertRaisesRegex(ValueError, "protocol version"):
                backend._perform_handshake(
                    local,
                    "guest",
                    bytes(expected_host.public_key),
                )
            self.assertFalse(backend.handshake_event.is_set())
        finally:
            local.close()
            remote.close()
            thread.join(timeout=2)

    def test_host_session_key_remains_bound_to_existing_invitation(self):
        first_public_key = backend._public_key_bytes()
        backend._reset_participant_verification(preserve_private_key=True)
        self.assertEqual(first_public_key, backend._public_key_bytes())


if __name__ == "__main__":
    unittest.main()
