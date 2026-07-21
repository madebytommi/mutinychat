import base64
import json
import socket
import unittest
from unittest import mock

import nacl.exceptions
from nacl.public import Box, PrivateKey

from participant_auth import build_confirmation_payload, build_invite, derive_safety_code
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

    def test_bundled_tor_requirement_rejects_missing_configured_path_without_fallback(self):
        missing_path = str(backend.Path.cwd() / "missing" / "mutinychat" / "tor")
        with mock.patch.dict(
            backend.os.environ,
            {
                "MUTINYCHAT_REQUIRE_BUNDLED_TOR": "1",
                "MUTINYCHAT_TOR_PATH": missing_path,
            },
            clear=False,
        ), mock.patch.object(
            backend, "_is_executable_file", return_value=False
        ) as is_executable, mock.patch.object(
            backend.shutil, "which", return_value="C:/attacker/tor.exe"
        ) as which:
            with self.assertRaisesRegex(RuntimeError, "Required bundled Tor"):
                backend._resolve_tor_cmd()

        is_executable.assert_called_once()
        which.assert_not_called()

    def test_bundled_tor_requirement_accepts_only_configured_absolute_path(self):
        configured = str(backend.Path.cwd() / "bundled-tor-test")
        with mock.patch.dict(
            backend.os.environ,
            {
                "MUTINYCHAT_REQUIRE_BUNDLED_TOR": "1",
                "MUTINYCHAT_TOR_PATH": configured,
            },
            clear=False,
        ), mock.patch.object(backend, "_is_executable_file", return_value=True):
            self.assertEqual(configured, backend._resolve_tor_cmd())

    def test_bundled_tor_requirement_rejects_relative_path(self):
        with mock.patch.dict(
            backend.os.environ,
            {
                "MUTINYCHAT_REQUIRE_BUNDLED_TOR": "1",
                "MUTINYCHAT_TOR_PATH": "tor.exe",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "absolute executable path"):
                backend._resolve_tor_cmd()

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

    def test_poll_reports_live_tor_without_overstating_room_routing(self):
        controller = mock.MagicMock()
        controller.is_alive.return_value = True
        process = mock.MagicMock()
        process.poll.return_value = None
        backend.tor_controller = controller
        backend.tor_process = process

        ready = backend.poll_messages()

        self.assertEqual("ready", ready["tor_status"])
        self.assertIsNone(ready["tor_error"])
        self.assertFalse(ready["tor_route_active"])
        self.assertNotIn("tor_active", ready)

    def test_poll_requires_live_process_and_controller_for_tor_status(self):
        controller = mock.MagicMock()
        controller.is_alive.return_value = True
        process = mock.MagicMock()
        process.poll.return_value = 1
        backend.tor_controller = controller
        backend.tor_process = process
        backend._active_room = {
            "mode": "guest",
            "tor_generation": backend._tor_generation,
        }
        backend._connection_mode = "guest"

        stopped = backend.poll_messages()

        self.assertEqual("failed", stopped["tor_status"])
        self.assertIn("no longer running", stopped["tor_error"])
        self.assertFalse(stopped["tor_route_active"])

        process.poll.return_value = None
        controller.is_alive.return_value = False
        disconnected = backend.poll_messages()
        self.assertEqual("failed", disconnected["tor_status"])
        self.assertIn("control connection", disconnected["tor_error"])
        self.assertFalse(disconnected["tor_route_active"])

    def test_room_route_is_bound_to_the_live_tor_generation(self):
        controller = mock.MagicMock()
        controller.is_alive.return_value = True
        process = mock.MagicMock()
        process.poll.return_value = None
        backend.tor_controller = controller
        backend.tor_process = process
        backend._connection_mode = "host"
        backend._active_room = {
            "mode": "host",
            "tor_generation": backend._tor_generation,
        }

        current = backend.poll_messages()
        self.assertTrue(current["tor_route_active"])

        backend._active_room["tor_generation"] = backend._tor_generation - 1
        stale = backend.poll_messages()
        self.assertEqual("ready", stale["tor_status"])
        self.assertFalse(stale["tor_route_active"])

    @mock.patch.object(backend.Controller, "from_port")
    @mock.patch.object(backend.stem.process, "launch_tor_with_config")
    @mock.patch.object(backend, "_resolve_tor_cmd", return_value="tor")
    def test_start_tor_replaces_stale_runtime(
        self,
        _resolve_tor_cmd,
        launch_tor_with_config,
        from_port,
    ):
        stale_controller = mock.MagicMock()
        stale_controller.is_alive.return_value = False
        stale_process = mock.MagicMock()
        stale_process.poll.return_value = 1
        backend.tor_controller = stale_controller
        backend.tor_process = stale_process

        new_controller = mock.MagicMock()
        new_controller.is_alive.return_value = True
        new_process = mock.MagicMock()
        new_process.poll.return_value = None
        launch_tor_with_config.return_value = new_process
        from_port.return_value = new_controller
        previous_generation = backend._tor_generation

        result = backend.start_tor()

        self.assertIs(new_controller, result)
        self.assertIs(new_controller, backend.tor_controller)
        self.assertEqual(previous_generation + 1, backend._tor_generation)
        stale_controller.close.assert_called_once()
        stale_process.terminate.assert_called_once()
        new_controller.authenticate.assert_called_once()
        tor_config = launch_tor_with_config.call_args.kwargs["config"]
        self.assertRegex(tor_config["ControlPort"], r"^127\.0\.0\.1:\d+$")
        self.assertRegex(
            tor_config["SocksPort"],
            r"^127\.0\.0\.1:\d+ IsolateSOCKSAuth$",
        )
        self.assertEqual("1", tor_config["CookieAuthentication"])
        self.assertEqual("0", tor_config["CookieAuthFileGroupReadable"])
        self.assertEqual(backend._tor_data_dir, tor_config["DataDirectory"])

    @mock.patch.object(backend.threading, "Thread")
    @mock.patch.object(backend, "_perform_handshake")
    @mock.patch.object(backend, "start_tor")
    @mock.patch.object(backend.socks, "socksocket")
    def test_join_room_uses_fresh_socks_credentials_for_stream_isolation(
        self,
        socksocket,
        start_tor,
        _perform_handshake,
        _thread,
    ):
        client = mock.MagicMock()
        socksocket.return_value = client

        def mark_tor_ready():
            backend.active_socks_port = 45678
            return mock.MagicMock()

        start_tor.side_effect = mark_tor_ready
        host = PrivateKey.generate()
        invitation = build_invite("a" * 56 + ".onion", bytes(host.public_key))

        with mock.patch.object(
            backend.secrets,
            "token_hex",
            side_effect=["session-user", "session-password"],
        ) as token_hex:
            backend.join_room(invitation, backend.DEFAULT_ONION_PORT)

        token_hex.assert_has_calls([mock.call(32), mock.call(32)])
        client.set_proxy.assert_called_once_with(
            backend.socks.SOCKS5,
            "127.0.0.1",
            45678,
            username="session-user",
            password="session-password",
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

    def test_send_message_rejects_oversized_utf8_payload_before_peer_lookup(self):
        result = backend.send_message("é" * (backend.MAX_CHAT_MESSAGE_BYTES // 2 + 1))

        self.assertEqual("error", result["status"])
        self.assertIn("16 KiB", result["error"])

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

    def test_handshake_reader_uses_chunks_and_preserves_coalesced_frames(self):
        conn = mock.MagicMock()
        conn.gettimeout.return_value = None
        conn.recv.return_value = b'{"type":"first"}\n{"type":"second"}\n'
        buffer = bytearray()
        deadline = backend.time.monotonic() + 1

        first = backend._receive_handshake_frame(conn, deadline, buffer)
        second = backend._receive_handshake_frame(conn, deadline, buffer)

        self.assertEqual({"type": "first"}, first)
        self.assertEqual({"type": "second"}, second)
        conn.recv.assert_called_once_with(4096)
        self.assertEqual(bytearray(), buffer)

    def test_handshake_reader_rejects_frame_over_its_dedicated_limit(self):
        conn = mock.MagicMock()
        conn.gettimeout.return_value = None
        conn.recv.side_effect = lambda size: b"x" * size

        with self.assertRaisesRegex(ValueError, "handshake frame is too large"):
            backend._receive_handshake_frame(
                conn,
                backend.time.monotonic() + 1,
                bytearray(),
            )

        self.assertEqual(5, conn.recv.call_count)

    @mock.patch.object(backend.threading, "Thread")
    def test_listener_reserves_slot_before_starting_only_one_worker(self, thread):
        server = mock.MagicMock()
        first = mock.MagicMock()
        second = mock.MagicMock()
        server.accept.side_effect = [
            (first, ("127.0.0.1", 1)),
            (second, ("127.0.0.1", 2)),
            OSError("listener stopped"),
        ]

        backend._listener_loop(server)

        thread.assert_called_once_with(
            target=backend._handle_guest,
            args=(first, mock.ANY),
            daemon=True,
        )
        thread.return_value.start.assert_called_once()
        self.assertIs(backend.active_peer_socket, first)
        second.sendall.assert_called_once()
        rejected = json.loads(second.sendall.call_args.args[0].decode("utf-8"))
        self.assertEqual("error", rejected["type"])
        second.close.assert_called_once()

    @mock.patch.object(backend.threading, "Thread")
    def test_listener_releases_reserved_slot_when_worker_cannot_start(self, thread):
        server = mock.MagicMock()
        conn = mock.MagicMock()
        server.accept.side_effect = [
            (conn, ("127.0.0.1", 1)),
            OSError("listener stopped"),
        ]
        thread.return_value.start.side_effect = RuntimeError("thread unavailable")

        backend._listener_loop(server)

        self.assertIsNone(backend.active_peer_socket)
        conn.close.assert_called_once()

    @mock.patch.object(backend, "_perform_handshake", side_effect=RuntimeError("failed"))
    def test_host_peer_count_is_not_promoted_when_handshake_fails(self, _perform_handshake):
        left, right = socket.socketpair()
        backend._connection_mode = "host"
        backend._active_room = {"mode": "host", "onion_address": "a" * 56 + ".onion"}
        backend._peer_count = 1
        try:
            generation = backend._claim_active_peer_socket(left)
            self.assertIsNotNone(generation)
            backend._handle_guest(left, generation)

            self.assertEqual(1, backend._peer_count)
            self.assertIsNone(backend.active_peer_socket)
        finally:
            left.close()
            right.close()

    @mock.patch.object(backend, "_peer_session")
    @mock.patch.object(backend, "_perform_handshake")
    def test_host_peer_count_is_promoted_after_shared_handshake_succeeds(
        self,
        _perform_handshake,
        peer_session,
    ):
        left, right = socket.socketpair()
        backend._connection_mode = "host"
        backend._active_room = {"mode": "host", "onion_address": "a" * 56 + ".onion"}
        backend._peer_count = 1
        try:
            generation = backend._claim_active_peer_socket(left)
            self.assertIsNotNone(generation)
            _perform_handshake.return_value = b""
            backend._handle_guest(left, generation)

            _perform_handshake.assert_called_once()
            self.assertEqual(2, backend._peer_count)
            peer_session.assert_called_once_with(
                left,
                "host",
                mock.ANY,
                handshake_complete=True,
                initial_buffer=b"",
            )
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

    def test_control_sentinel_plaintext_is_delivered_only_as_chat(self):
        alice = PrivateKey.generate()
        bob = PrivateKey.generate()
        left, right = socket.socketpair()
        sentinels = (
            "__disconnect__",
            "room_deleted",
            "__peer_joined__",
            "__peer_left__",
            "__peer_verified__",
            "__channel_failed__",
        )
        try:
            backend._private_key = alice
            backend._active_room = {"onion_address": "a" * 56 + ".onion"}
            generation = backend._claim_active_peer_socket(left)
            self.assertIsNotNone(generation)
            _promote_test_channel(bytes(bob.public_key))
            backend.verification_event.set()
            peer_box = Box(bob, alice.public_key)

            for sentinel in sentinels:
                ciphertext = base64.b64encode(
                    bytes(peer_box.encrypt(sentinel.encode("utf-8")))
                ).decode("ascii")
                frame = json.dumps(
                    {"type": "message", "ciphertext": ciphertext},
                    separators=(",", ":"),
                ).encode("utf-8")
                self.assertTrue(backend._process_peer_frame(left, generation, frame))

            state = backend.poll_messages()
            self.assertEqual(
                [{"kind": "chat", "text": sentinel} for sentinel in sentinels],
                state["events"],
            )
            self.assertTrue(backend._is_peer_session_owner(left, generation))
        finally:
            left.close()
            right.close()

    def test_local_disconnect_sentinel_is_sent_as_encrypted_chat(self):
        alice = PrivateKey.generate()
        bob = PrivateKey.generate()
        left, right = socket.socketpair()
        try:
            backend._private_key = alice
            backend._active_room = {"onion_address": "a" * 56 + ".onion"}
            self.assertIsNotNone(backend._claim_active_peer_socket(left))
            _promote_test_channel(bytes(bob.public_key))
            backend.verification_event.set()

            self.assertEqual({"status": "sent"}, backend.send_message("__disconnect__"))

            frame = json.loads(right.recv(4096).split(b"\n", 1)[0].decode("utf-8"))
            self.assertEqual("message", frame["type"])
            plaintext = Box(bob, alice.public_key).decrypt(
                base64.b64decode(frame["ciphertext"], validate=True)
            ).decode("utf-8")
            self.assertEqual("__disconnect__", plaintext)
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

    def test_close_room_sends_typed_disconnect_frame(self):
        left, right = socket.socketpair()
        self.assertIsNotNone(backend._claim_active_peer_socket(left))
        try:
            self.assertEqual({"status": "closed"}, backend.close_room())

            frame = json.loads(right.recv(4096).split(b"\n", 1)[0].decode("utf-8"))
            self.assertEqual({"type": "disconnect"}, frame)
        finally:
            left.close()
            right.close()

    def test_poll_messages_drains_queue(self):
        self.assertTrue(backend._queue_frontend_message("one"))
        self.assertTrue(backend._queue_frontend_message("two"))
        first = backend.poll_messages()
        second = backend.poll_messages()
        self.assertEqual(
            [
                {"kind": "chat", "text": "one"},
                {"kind": "chat", "text": "two"},
            ],
            first["events"],
        )
        self.assertEqual(0, first["events_pending"])
        self.assertEqual([], second["events"])

    def test_frontend_control_events_are_typed_and_validated(self):
        self.assertTrue(backend._queue_frontend_control("peer_joined"))
        state = backend.poll_messages()

        self.assertEqual(
            [{"kind": "control", "event": "peer_joined"}],
            state["events"],
        )
        with self.assertRaisesRegex(ValueError, "Unsupported frontend control event"):
            backend._queue_frontend_control("attacker_selected_event")

    def test_poll_messages_returns_bounded_fifo_batches(self):
        total = backend.MAX_POLL_MESSAGES + 5
        for index in range(total):
            self.assertTrue(backend._queue_frontend_message(f"message-{index}"))

        first = backend.poll_messages()
        second = backend.poll_messages()

        self.assertEqual(
            [
                {"kind": "chat", "text": f"message-{index}"}
                for index in range(backend.MAX_POLL_MESSAGES)
            ],
            first["events"],
        )
        self.assertEqual(5, first["events_pending"])
        self.assertEqual(
            [
                {"kind": "chat", "text": f"message-{index}"}
                for index in range(backend.MAX_POLL_MESSAGES, total)
            ],
            second["events"],
        )
        self.assertEqual(0, second["events_pending"])

    def test_frontend_queue_enforces_message_count_limit(self):
        for index in range(backend.MAX_FRONTEND_QUEUE_MESSAGES):
            self.assertTrue(backend._queue_frontend_message(f"message-{index}"))

        self.assertFalse(backend._queue_frontend_message("overflow"))
        self.assertEqual(backend.MAX_FRONTEND_QUEUE_MESSAGES, len(backend._inbox))

    def test_frontend_queue_enforces_serialized_byte_limit(self):
        message = "\\" * 16_000
        serialized_size = backend._serialized_event_size(backend._chat_event(message))
        accepted = 0
        while backend._queue_frontend_message(message):
            accepted += 1

        self.assertGreater(accepted, 0)
        self.assertLessEqual(backend._inbox_bytes, backend.MAX_FRONTEND_QUEUE_BYTES)
        self.assertGreater(
            backend._inbox_bytes + serialized_size,
            backend.MAX_FRONTEND_QUEUE_BYTES,
        )

    def test_poll_messages_enforces_serialized_byte_limit(self):
        message = "\\" * backend.MAX_CHAT_MESSAGE_BYTES
        for _ in range(4):
            self.assertTrue(backend._queue_frontend_message(message))

        response = backend.poll_messages()
        serialized_events = sum(
            backend._serialized_event_size(event) for event in response["events"]
        )

        self.assertLessEqual(serialized_events, backend.MAX_POLL_MESSAGE_BYTES)
        self.assertGreater(response["events_pending"], 0)

    def test_oversized_peer_ciphertext_is_rejected_before_decryption(self):
        alice = PrivateKey.generate()
        bob = PrivateKey.generate()
        left, right = socket.socketpair()
        try:
            backend._private_key = alice
            backend._active_room = {"onion_address": "a" * 56 + ".onion"}
            generation = backend._claim_active_peer_socket(left)
            self.assertIsNotNone(generation)
            _promote_test_channel(bytes(bob.public_key))
            backend.verification_event.set()
            frame = json.dumps(
                {
                    "type": "message",
                    "ciphertext": "A" * (backend.MAX_ENCRYPTED_MESSAGE_CHARS + 1),
                }
            ).encode("utf-8")

            with self.assertRaisesRegex(ValueError, "too large"):
                backend._process_peer_frame(left, generation, frame)
        finally:
            left.close()
            right.close()

    @mock.patch.object(backend, "_process_peer_frame", return_value=True)
    def test_socket_reader_rejects_excessive_frame_rate(self, process_peer_frame):
        left, right = socket.socketpair()
        try:
            generation = backend._claim_active_peer_socket(left)
            self.assertIsNotNone(generation)
            right.sendall(b"{}\n" * (backend.MAX_INBOUND_FRAMES_PER_SECOND + 1))

            backend._read_socket_messages(left, generation)

            self.assertEqual(backend.MAX_INBOUND_FRAMES_PER_SECOND, process_peer_frame.call_count)
            state = backend.poll_messages()
            self.assertEqual("failed", state["channel_status"])
            self.assertIn("rate limit", state["channel_error"])
        finally:
            left.close()
            right.close()

    @mock.patch.object(backend, "_process_peer_frame", return_value=True)
    def test_socket_reader_rejects_oversized_application_frame(self, process_peer_frame):
        left, right = socket.socketpair()
        try:
            generation = backend._claim_active_peer_socket(left)
            self.assertIsNotNone(generation)
            right.sendall(b"x" * (backend.MAX_APPLICATION_FRAME_BYTES + 1) + b"\n")

            backend._read_socket_messages(left, generation)

            process_peer_frame.assert_not_called()
            state = backend.poll_messages()
            self.assertEqual("failed", state["channel_status"])
            self.assertIn("too large", state["channel_error"])
        finally:
            left.close()
            right.close()

    def test_peer_queue_overflow_clears_pending_messages_and_fails(self):
        alice = PrivateKey.generate()
        bob = PrivateKey.generate()
        left, right = socket.socketpair()
        try:
            backend._private_key = alice
            backend._active_room = {"onion_address": "a" * 56 + ".onion"}
            generation = backend._claim_active_peer_socket(left)
            self.assertIsNotNone(generation)
            _promote_test_channel(bytes(bob.public_key))
            backend.verification_event.set()
            for index in range(backend.MAX_FRONTEND_QUEUE_MESSAGES):
                self.assertTrue(backend._queue_frontend_message(f"queued-{index}"))
            ciphertext = base64.b64encode(
                bytes(Box(bob, alice.public_key).encrypt(b"overflow"))
            ).decode("ascii")
            frame = json.dumps({"type": "message", "ciphertext": ciphertext}).encode(
                "utf-8"
            )

            with self.assertRaisesRegex(RuntimeError, "pending message capacity"):
                backend._process_peer_frame(left, generation, frame)

            self.assertEqual(0, len(backend._inbox))
            self.assertEqual(0, backend._inbox_bytes)
        finally:
            left.close()
            right.close()

    def test_friendly_error_truncates_peer_controlled_text(self):
        result = backend._friendly_error(RuntimeError("x" * 10_000))

        self.assertEqual(backend.MAX_ERROR_MESSAGE_CHARS, len(result))
        self.assertTrue(result.endswith("…"))

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
        self.assertEqual(backend._tor_generation, backend._active_room["tor_generation"])
        self.assertEqual("test-room", response["friendly_name"])
        self.assertTrue(response["share_link"].startswith("mutinychat://join?"))
        self.assertNotIn("key_b64", response)


if __name__ == "__main__":
    unittest.main()
