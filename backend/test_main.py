import base64
import json
import socket
import threading
import unittest
from unittest import mock

import nacl.exceptions
from nacl.public import Box, PrivateKey

import main as backend


class BackendTestCase(unittest.TestCase):
    def setUp(self):
        backend.close_room()

    def tearDown(self):
        backend.close_room()

    def test_random_room_name_has_expected_shape(self):
        name = backend.generate_random_room_name()
        parts = name.split("-")
        self.assertEqual(3, len(parts))
        self.assertIn(parts[0], backend.ADJECTIVES)
        self.assertIn(parts[1], backend.NOUNS)
        self.assertTrue(parts[2].isdigit())

    def test_extract_onion_host_accepts_v3_address_in_share_link(self):
        onion = "a" * 56 + ".onion"
        self.assertEqual(onion, backend._extract_onion_host(f"Join room → {onion}"))

    def test_extract_onion_host_rejects_legacy_or_malformed_address(self):
        with self.assertRaises(ValueError):
            backend._extract_onion_host("abcdefghijklmnop.onion")
        with self.assertRaises(ValueError):
            backend._extract_onion_host("not-an-onion")

    def test_command_is_required(self):
        self.assertEqual({"error": "Command is required"}, backend.handle_json_command({}))

    def test_unknown_command_returns_error(self):
        self.assertEqual(
            {"error": "Unknown command: nonsense"},
            backend.handle_json_command({"cmd": "nonsense"}),
        )

    def test_echo_preserves_message(self):
        self.assertEqual(
            {"echo": "hello"},
            backend.handle_json_command({"cmd": "echo", "message": "hello"}),
        )

    def test_empty_message_is_rejected(self):
        self.assertEqual(
            {"status": "error", "error": "Message cannot be empty"},
            backend.send_message("   "),
        )

    def test_send_message_requires_peer(self):
        self.assertEqual(
            {"status": "error", "error": "No active peer socket"},
            backend.send_message("hello"),
        )

    def test_ephemeral_box_round_trip_between_peers(self):
        alice = PrivateKey.generate()
        bob = PrivateKey.generate()
        backend._private_key = alice
        backend._install_peer_public_key(base64.b64encode(bytes(bob.public_key)).decode("ascii"))

        encoded = backend.encrypt_message("hello")
        raw = base64.b64decode(encoded, validate=True)
        bob_box = Box(bob, alice.public_key)
        self.assertEqual("hello", bob_box.decrypt(raw).decode("utf-8"))

    def test_wrong_key_cannot_decrypt_message(self):
        alice = PrivateKey.generate()
        bob = PrivateKey.generate()
        eve = PrivateKey.generate()
        backend._private_key = alice
        backend._install_peer_public_key(base64.b64encode(bytes(bob.public_key)).decode("ascii"))
        encoded = backend.encrypt_message("secret")

        with self.assertRaises(nacl.exceptions.CryptoError):
            Box(eve, alice.public_key).decrypt(base64.b64decode(encoded))

    def test_malformed_peer_json_closes_session(self):
        left, right = socket.socketpair()
        try:
            with self.assertRaises(ValueError):
                backend._process_peer_frame(left, b"not-json")
        finally:
            left.close()
            right.close()

    def test_hello_frame_establishes_secure_session(self):
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
            self.assertTrue(backend.handshake_ready_event.is_set())
            self.assertIsNotNone(backend._box)
        finally:
            left.close()
            right.close()

    def test_disconnect_frame_stops_reader(self):
        left, right = socket.socketpair()
        try:
            self.assertFalse(
                backend._process_peer_frame(left, json.dumps({"type": "disconnect"}).encode("utf-8"))
            )
        finally:
            left.close()
            right.close()

    def test_host_rejects_second_peer(self):
        first_left, first_right = socket.socketpair()
        second_left, second_right = socket.socketpair()
        try:
            self.assertTrue(backend._claim_active_peer_socket(first_left))
            self.assertFalse(backend._claim_active_peer_socket(second_left))
        finally:
            first_left.close()
            first_right.close()
            second_left.close()
            second_right.close()

    def test_close_room_is_idempotent(self):
        self.assertEqual({"status": "closed"}, backend.close_room())
        self.assertEqual({"status": "closed"}, backend.close_room())
        self.assertIsNone(backend.active_peer_socket)
        self.assertIsNone(backend.tor_controller)
        self.assertFalse(backend.handshake_ready_event.is_set())

    def test_poll_messages_drains_queue(self):
        backend._queue_frontend_message("one")
        backend._queue_frontend_message("two")
        first = backend.poll_messages()
        second = backend.poll_messages()
        self.assertEqual(["one", "two"], first["messages"])
        self.assertEqual([], second["messages"])

    @mock.patch.object(backend, "create_hidden_service")
    @mock.patch.object(backend, "close_room")
    def test_room_creation_sets_host_state(self, close_room, create_hidden_service):
        create_hidden_service.return_value = {
            "onion_address": "a" * 56 + ".onion",
            "port": backend.DEFAULT_ONION_PORT,
        }
        backend.active_service_id = "service-id"
        backend.active_local_port = 12345

        response = backend.build_room_response("test-room")

        close_room.assert_called_once()
        self.assertEqual("host", backend._connection_mode)
        self.assertEqual(1, backend._peer_count)
        self.assertEqual("test-room", response["friendly_name"])
        self.assertNotIn("key_b64", response)


if __name__ == "__main__":
    unittest.main()
