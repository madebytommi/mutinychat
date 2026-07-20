import base64
import json
import socket
import unittest
from unittest import mock

import nacl.exceptions
from nacl.public import Box, PrivateKey

from participant_auth import build_confirmation_payload, derive_safety_code
import main as backend


def _promote_test_channel(
    peer_public_key: bytes,
    role: str = "host",
    transcript: bytes = b"t" * 32,
) -> None:
    if backend._private_key is None:
        raise RuntimeError("Test local private key is missing")
    peer_key, box = backend._create_candidate_box(
        base64.b64encode(peer_public_key).decode("ascii"),
        backend._private_key,
    )
    local_public_key = bytes(backend._private_key.public_key)
    backend._peer_public_key = peer_key
    backend._box = box
    backend._connection_role = role
    backend._handshake_transcript_hash = transcript
    if role == "host":
        host_key, guest_key = local_public_key, peer_key
    else:
        host_key, guest_key = peer_key, local_public_key
    backend._verification_code = derive_safety_code(
        host_key,
        guest_key,
        "a" * 56 + ".onion",
        b"h" * 32,
        b"g" * 32,
    )
    backend._channel_status = "confirmed"
    backend.handshake_event.set()


class BackendTestCase(unittest.TestCase):
    def setUp(self):
        backend.close_room()
        backend.stop_event.clear()

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
        backend._active_room = {"onion_address": "a" * 56 + ".onion"}
        _promote_test_channel(bytes(bob.public_key))

        encoded = backend.encrypt_message("hello")
        raw = base64.b64decode(encoded, validate=True)
        bob_box = Box(bob, alice.public_key)
        self.assertEqual("hello", bob_box.decrypt(raw).decode("utf-8"))

    def test_wrong_key_cannot_decrypt_message(self):
        alice = PrivateKey.generate()
        bob = PrivateKey.generate()
        eve = PrivateKey.generate()
        backend._private_key = alice
        backend._active_room = {"onion_address": "a" * 56 + ".onion"}
        _promote_test_channel(bytes(bob.public_key))
        encoded = backend.encrypt_message("secret")

        with self.assertRaises(nacl.exceptions.CryptoError):
            Box(eve, alice.public_key).decrypt(base64.b64decode(encoded))

    def test_malformed_peer_json_closes_session(self):
        left, right = socket.socketpair()
        try:
            generation = backend._claim_active_peer_socket(left)
            self.assertIsNotNone(generation)
            with self.assertRaises(ValueError):
                backend._process_peer_frame(left, generation, b"not-json")
        finally:
            left.close()
            right.close()

    def test_arbitrary_valid_length_peer_key_only_creates_pending_candidate(self):
        local = PrivateKey.generate()
        remote = PrivateKey.generate()
        backend._private_key = local
        backend._active_room = {"onion_address": "a" * 56 + ".onion"}
        peer_key, candidate_box = backend._create_candidate_box(
            base64.b64encode(bytes(remote.public_key)).decode("ascii"),
            local,
        )
        state = backend.poll_messages()
        self.assertFalse(state["encrypted"])
        self.assertEqual(bytes(remote.public_key), peer_key)
        self.assertIsNotNone(candidate_box)
        self.assertIsNone(backend._peer_public_key)
        self.assertIsNone(backend._box)
        self.assertFalse(backend.handshake_event.is_set())
        self.assertFalse(state["verified"])
        self.assertIsNone(state["verification_code"])

    def test_reflected_local_public_key_is_rejected(self):
        local = PrivateKey.generate()
        backend._private_key = local
        with self.assertRaisesRegex(ValueError, "must differ"):
            backend._create_candidate_box(
                base64.b64encode(bytes(local.public_key)).decode("ascii"),
                local,
            )
        self.assertFalse(backend.handshake_event.is_set())

    def test_peer_key_install_rejects_invitation_key_mismatch(self):
        local = PrivateKey.generate()
        expected = PrivateKey.generate()
        attacker = PrivateKey.generate()
        backend._private_key = local
        backend._active_room = {"onion_address": "a" * 56 + ".onion"}
        with self.assertRaisesRegex(ValueError, "does not match"):
            backend._create_candidate_box(
                base64.b64encode(bytes(attacker.public_key)).decode("ascii"),
                local,
                bytes(expected.public_key),
            )

    def test_message_is_blocked_until_both_participants_confirm(self):
        left, right = socket.socketpair()
        try:
            self.assertIsNotNone(backend._claim_active_peer_socket(left))
            result = backend.send_message("secret")
            self.assertEqual("error", result["status"])
            self.assertIn("safety code", result["error"])
        finally:
            left.close()
            right.close()

    def test_encrypted_peer_confirmation_completes_verification(self):
        alice = PrivateKey.generate()
        bob = PrivateKey.generate()
        left, right = socket.socketpair()
        try:
            backend._private_key = alice
            backend._active_room = {"onion_address": "a" * 56 + ".onion"}
            generation = backend._claim_active_peer_socket(left)
            self.assertIsNotNone(generation)
            transcript = b"t" * 32
            _promote_test_channel(bytes(bob.public_key), "host", transcript)
            backend._verification_local_confirmed = True
            code = backend.poll_messages()["verification_code"]
            bob_box = Box(bob, alice.public_key)
            ciphertext = base64.b64encode(
                bytes(
                    bob_box.encrypt(
                        build_confirmation_payload(code, "guest", transcript).encode("utf-8")
                    )
                )
            ).decode("ascii")

            backend._handle_peer_verification(left, generation, ciphertext)

            state = backend.poll_messages()
            self.assertTrue(state["verified"])
            self.assertTrue(state["verification_local_confirmed"])
            self.assertTrue(state["verification_peer_confirmed"])
        finally:
            left.close()
            right.close()

    def test_reflected_local_manual_verification_is_rejected(self):
        alice = PrivateKey.generate()
        bob = PrivateKey.generate()
        left, right = socket.socketpair()
        try:
            backend._private_key = alice
            backend._active_room = {"onion_address": "a" * 56 + ".onion"}
            generation = backend._claim_active_peer_socket(left)
            self.assertIsNotNone(generation)
            transcript = b"t" * 32
            _promote_test_channel(bytes(bob.public_key), "host", transcript)
            code = backend.poll_messages()["verification_code"]
            reflected = backend.encrypt_message(
                build_confirmation_payload(code, "host", transcript)
            )

            with self.assertRaisesRegex(ValueError, "role"):
                backend._handle_peer_verification(left, generation, reflected)
            self.assertFalse(backend.poll_messages()["verification_peer_confirmed"])
        finally:
            left.close()
            right.close()

    def test_verified_message_is_sent_as_ciphertext(self):
        alice = PrivateKey.generate()
        bob = PrivateKey.generate()
        left, right = socket.socketpair()
        try:
            backend._private_key = alice
            backend._active_room = {"onion_address": "a" * 56 + ".onion"}
            self.assertIsNotNone(backend._claim_active_peer_socket(left))
            _promote_test_channel(bytes(bob.public_key))
            backend._verification_local_confirmed = True
            backend._verification_peer_confirmed = True
            backend.verification_event.set()

            result = backend.send_message("secret")
            raw = right.recv(4096).split(b"\n", 1)[0]
            frame = json.loads(raw.decode("utf-8"))
            self.assertEqual({"status": "sent"}, result)
            self.assertEqual("message", frame["type"])
            self.assertNotIn("secret", raw.decode("utf-8"))
            plaintext = Box(bob, alice.public_key).decrypt(
                base64.b64decode(frame["ciphertext"], validate=True)
            ).decode("utf-8")
            self.assertEqual("secret", plaintext)
        finally:
            left.close()
            right.close()

    def test_send_failure_invalidates_confirmed_channel(self):
        alice = PrivateKey.generate()
        bob = PrivateKey.generate()
        left, right = socket.socketpair()
        backend._private_key = alice
        backend._active_room = {"onion_address": "a" * 56 + ".onion"}
        self.assertIsNotNone(backend._claim_active_peer_socket(left))
        _promote_test_channel(bytes(bob.public_key))
        backend.verification_event.set()
        left.close()
        try:
            result = backend.send_message("secret")
            self.assertEqual("error", result["status"])
            state = backend.poll_messages()
            self.assertEqual("failed", state["channel_status"])
            self.assertFalse(state["encrypted"])
            self.assertFalse(state["verified"])
        finally:
            right.close()

    def test_raw_onion_join_is_rejected_before_network_access(self):
        response = backend.handle_json_command(
            {"cmd": "join_room", "message": "a" * 56 + ".onion"}
        )
        self.assertIn("authenticated", response["error"].lower())

    def test_disconnect_frame_stops_reader(self):
        left, right = socket.socketpair()
        try:
            generation = backend._claim_active_peer_socket(left)
            self.assertIsNotNone(generation)
            self.assertFalse(
                backend._process_peer_frame(
                    left,
                    generation,
                    json.dumps({"type": "disconnect"}).encode("utf-8"),
                )
            )
        finally:
            left.close()
            right.close()

    def test_host_rejects_second_peer(self):
        first_left, first_right = socket.socketpair()
        second_left, second_right = socket.socketpair()
        try:
            self.assertTrue(backend._claim_active_peer_socket(first_left))
            self.assertIsNone(backend._claim_active_peer_socket(second_left))
        finally:
            first_left.close()
            first_right.close()
            second_left.close()
            second_right.close()

    def test_failed_host_attempt_releases_connection_slot_for_next_peer(self):
        failed_left, failed_right = socket.socketpair()
        valid_left, valid_right = socket.socketpair()
        backend._connection_mode = "host"
        backend._active_room = {"mode": "host", "onion_address": "a" * 56 + ".onion"}
        try:
            failed_generation = backend._claim_active_peer_socket(failed_left)
            self.assertIsNotNone(failed_generation)
            backend._release_failed_host_connection(
                failed_left,
                failed_generation,
                ValueError("bad handshake"),
            )
            self.assertIsNone(backend.active_peer_socket)
            self.assertEqual("failed", backend.poll_messages()["channel_status"])
            self.assertTrue(backend._claim_active_peer_socket(valid_left))
        finally:
            failed_right.close()
            valid_left.close()
            valid_right.close()

    def test_close_room_is_idempotent(self):
        self.assertEqual({"status": "closed"}, backend.close_room())
        self.assertEqual({"status": "closed"}, backend.close_room())
        self.assertIsNone(backend.active_peer_socket)
        self.assertIsNone(backend.tor_controller)
        self.assertFalse(backend.handshake_event.is_set())
        self.assertFalse(backend.verification_event.is_set())

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
        self.assertTrue(response["share_link"].startswith("mutinychat://join?"))
        self.assertNotIn("key_b64", response)


if __name__ == "__main__":
    unittest.main()
