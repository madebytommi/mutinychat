import base64
import json
import socket
import threading
import unittest
from unittest import mock

from nacl.public import PrivateKey

import main as backend
import sidecar


def _read_line(sock: socket.socket) -> bytes:
    data = bytearray()
    while True:
        chunk = sock.recv(1)
        if not chunk or chunk == b"\n":
            return bytes(data)
        data.extend(chunk)


class SidecarHandshakeTestCase(unittest.TestCase):
    def setUp(self):
        backend.close_room()
        backend._reset_crypto()

    def tearDown(self):
        backend.close_room()

    def test_perform_handshake_establishes_encryption(self):
        local, remote = socket.socketpair()
        remote_key = PrivateKey.generate()

        def peer():
            hello = json.loads(_read_line(remote).decode("utf-8"))
            self.assertEqual("hello", hello["type"])
            remote.sendall(
                (
                    json.dumps(
                        {
                            "type": "hello",
                            "public_key": base64.b64encode(
                                bytes(remote_key.public_key)
                            ).decode("ascii"),
                        }
                    )
                    + "\n"
                ).encode("utf-8")
            )

        thread = threading.Thread(target=peer)
        thread.start()
        try:
            sidecar._perform_handshake(local)
            self.assertTrue(backend.handshake_event.is_set())
            self.assertIsNotNone(backend._box)
        finally:
            local.close()
            remote.close()
            thread.join(timeout=2)

    def test_perform_handshake_surfaces_peer_error(self):
        local, remote = socket.socketpair()

        def peer():
            _read_line(remote)
            remote.sendall(
                (json.dumps({"type": "error", "message": "room full"}) + "\n").encode(
                    "utf-8"
                )
            )

        thread = threading.Thread(target=peer)
        thread.start()
        try:
            with self.assertRaisesRegex(RuntimeError, "room full"):
                sidecar._perform_handshake(local)
        finally:
            local.close()
            remote.close()
            thread.join(timeout=2)

    def test_host_is_not_marked_connected_when_handshake_fails(self):
        local, remote = socket.socketpair()
        backend._connection_mode = "host"
        backend._active_room = {"mode": "host"}
        backend._peer_count = 1

        try:
            with mock.patch.object(
                sidecar,
                "_perform_handshake",
                side_effect=TimeoutError("Secure session handshake timed out"),
            ):
                sidecar._handle_guest(local)

            self.assertEqual(1, backend._peer_count)
            self.assertIsNone(backend.active_peer_socket)
            queued = backend.poll_messages()["messages"]
            self.assertTrue(any("Secure connection attempt failed" in item for item in queued))
        finally:
            remote.close()

    def test_install_replaces_connection_entrypoints(self):
        sidecar.install()
        self.assertIs(backend.join_room, sidecar.join_room)
        self.assertIs(backend._handle_guest, sidecar._handle_guest)
        self.assertIs(backend._peer_session, sidecar._peer_session)
        self.assertEqual(60, backend.CONNECT_TIMEOUT)
        self.assertEqual(30, backend.HANDSHAKE_TIMEOUT)


if __name__ == "__main__":
    unittest.main()
