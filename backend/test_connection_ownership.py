from __future__ import annotations

import base64
import json
import socket
import threading
import unittest
from unittest import mock

from nacl.public import PrivateKey

import main as backend
from test_participant_handshake import TEST_ONION, _peer_protocol


class ConnectionOwnershipTestCase(unittest.TestCase):
    def setUp(self):
        backend.close_room()
        backend.stop_event.clear()
        backend._reset_crypto()
        backend._connection_mode = "host"
        backend._active_room = {"mode": "host", "onion_address": TEST_ONION}
        self.sockets: list[socket.socket] = []

    def tearDown(self):
        backend.close_room()
        for sock in self.sockets:
            try:
                sock.close()
            except OSError:
                pass

    def _socket_pair(self) -> tuple[socket.socket, socket.socket]:
        pair = socket.socketpair()
        self.sockets.extend(pair)
        return pair

    def _claim(self, conn: socket.socket) -> int:
        generation = backend._claim_active_peer_socket(conn)
        self.assertIsNotNone(generation)
        return generation

    def _set_owned_channel(
        self,
        conn: socket.socket,
        generation: int,
        *,
        verified: bool = False,
    ) -> None:
        peer = PrivateKey.generate()
        self.assertIsNotNone(backend._private_key)
        peer_key, box = backend._create_candidate_box(
            base64.b64encode(bytes(peer.public_key)).decode("ascii"),
            backend._private_key,
        )
        with backend.peer_lock:
            self.assertTrue(backend._is_peer_session_owner_locked(conn, generation))
            with backend.state_lock:
                backend._peer_public_key = peer_key
                backend._box = box
                backend._handshake_transcript_hash = b"t" * 32
                backend._connection_role = "host"
                backend._verification_code = "00000 00000 00000 00000"
                backend._channel_status = "confirmed"
                backend._channel_error = None
                backend.handshake_event.set()
                if verified:
                    backend._verification_local_confirmed = True
                    backend._verification_peer_confirmed = True
                    backend.verification_event.set()

    def _start_thread(self, target) -> tuple[threading.Thread, list[BaseException]]:
        failures: list[BaseException] = []

        def run():
            try:
                target()
            except BaseException as exc:
                failures.append(exc)

        thread = threading.Thread(target=run)
        thread.start()
        return thread, failures

    def _join(self, thread: threading.Thread) -> None:
        thread.join(timeout=3)
        self.assertFalse(thread.is_alive(), "Controlled race thread did not finish")

    def test_old_failed_cleanup_cannot_clear_new_pending_session(self):
        old_conn, _ = self._socket_pair()
        old_generation = self._claim(old_conn)
        released = threading.Event()
        continue_cleanup = threading.Event()
        cleanup_results: list[bool] = []

        def old_cleanup():
            backend._release_failed_host_connection(
                old_conn,
                old_generation,
                ValueError("malicious handshake"),
            )
            released.set()
            self.assertTrue(continue_cleanup.wait(2))
            cleanup_results.append(
                backend._reset_owned_participant_verification(
                    old_conn,
                    old_generation,
                    channel_status="failed",
                    channel_error="stale cleanup",
                )
            )

        thread, failures = self._start_thread(old_cleanup)
        self.assertTrue(released.wait(2))
        new_conn, _ = self._socket_pair()
        new_generation = self._claim(new_conn)
        self.assertTrue(
            backend._reset_owned_participant_verification(
                new_conn,
                new_generation,
                channel_status="pending",
            )
        )
        continue_cleanup.set()
        self._join(thread)

        self.assertEqual([], failures)
        self.assertEqual([False], cleanup_results)
        self.assertEqual("pending", backend.poll_messages()["channel_status"])
        self.assertTrue(backend._is_peer_session_owner(new_conn, new_generation))

    def test_stale_frame_cannot_use_new_connection_box(self):
        old_conn, _ = self._socket_pair()
        old_generation = self._claim(old_conn)
        self._set_owned_channel(old_conn, old_generation, verified=True)
        old_box = backend._box
        self.assertIsNotNone(old_box)
        old_ciphertext = backend._encrypt_with_box(old_box, "stale message")
        backend._fail_active_channel(old_conn, old_generation, ConnectionError("old failed"))
        backend.poll_messages()

        new_conn, _ = self._socket_pair()
        new_generation = self._claim(new_conn)
        self._set_owned_channel(new_conn, new_generation, verified=True)
        raw = json.dumps(
            {"type": "message", "ciphertext": old_ciphertext},
            separators=(",", ":"),
        ).encode("utf-8")

        self.assertFalse(backend._process_peer_frame(old_conn, old_generation, raw))
        state = backend.poll_messages()
        self.assertEqual("confirmed", state["channel_status"])
        self.assertTrue(state["encrypted"])
        self.assertEqual([], state["messages"])

    def test_old_peer_session_finally_cannot_clear_new_connection(self):
        old_conn, _ = self._socket_pair()
        old_generation = self._claim(old_conn)
        reader_entered = threading.Event()
        release_reader = threading.Event()

        def blocked_reader(conn: socket.socket, generation: int):
            self.assertIs(conn, old_conn)
            self.assertEqual(old_generation, generation)
            reader_entered.set()
            self.assertTrue(release_reader.wait(2))

        with mock.patch.object(backend, "_read_socket_messages", side_effect=blocked_reader):
            thread, failures = self._start_thread(
                lambda: backend._peer_session(
                    old_conn,
                    "host",
                    old_generation,
                    handshake_complete=True,
                )
            )
            self.assertTrue(reader_entered.wait(2))
            backend._fail_active_channel(
                old_conn,
                old_generation,
                ConnectionError("old session failed"),
            )
            new_conn, _ = self._socket_pair()
            new_generation = self._claim(new_conn)
            self._set_owned_channel(new_conn, new_generation)
            release_reader.set()
            self._join(thread)

        self.assertEqual([], failures)
        self.assertTrue(backend._is_peer_session_owner(new_conn, new_generation))
        self.assertEqual("confirmed", backend.poll_messages()["channel_status"])

    def test_close_room_during_handshake_remains_disconnected(self):
        conn, _ = self._socket_pair()
        generation = self._claim(conn)
        send_entered = threading.Event()
        release_send = threading.Event()

        def blocked_send(*_args, **_kwargs):
            send_entered.set()
            self.assertTrue(release_send.wait(2))
            raise OSError("socket closed by room shutdown")

        with mock.patch.object(backend, "_send_handshake_frame", side_effect=blocked_send):
            thread, failures = self._start_thread(
                lambda: backend._perform_handshake(conn, "host", generation)
            )
            self.assertTrue(send_entered.wait(2))
            backend.close_room()
            release_send.set()
            self._join(thread)

        self.assertEqual(1, len(failures))
        self.assertIsInstance(failures[0], OSError)
        state = backend.poll_messages()
        self.assertEqual("disconnected", state["channel_status"])
        self.assertFalse(state["encrypted"])

    def test_stale_handshake_cannot_promote_after_ownership_changes(self):
        conn, remote = self._socket_pair()
        generation = self._claim(conn)
        peer_key = PrivateKey.generate()
        peer_thread, peer_failures = self._start_thread(
            lambda: _peer_protocol(remote, peer_key, role="guest")
        )
        promotion_entered = threading.Event()
        release_promotion = threading.Event()
        original_derive = backend.derive_safety_code

        def blocked_derive(*args, **kwargs):
            promotion_entered.set()
            self.assertTrue(release_promotion.wait(2))
            return original_derive(*args, **kwargs)

        with mock.patch.object(backend, "derive_safety_code", side_effect=blocked_derive):
            handshake_thread, handshake_failures = self._start_thread(
                lambda: backend._perform_handshake(conn, "host", generation)
            )
            self.assertTrue(promotion_entered.wait(2))
            backend._fail_active_channel(
                conn,
                generation,
                ConnectionError("old ownership released"),
            )
            new_conn, _ = self._socket_pair()
            new_generation = self._claim(new_conn)
            self._set_owned_channel(new_conn, new_generation)
            release_promotion.set()
            self._join(handshake_thread)

        self._join(peer_thread)
        self.assertEqual([], peer_failures)
        self.assertEqual(1, len(handshake_failures))
        self.assertIsInstance(handshake_failures[0], backend.StalePeerSessionError)
        self.assertTrue(backend._is_peer_session_owner(new_conn, new_generation))
        self.assertEqual("confirmed", backend.poll_messages()["channel_status"])

    def test_stale_send_failure_cannot_invalidate_new_confirmed_session(self):
        old_conn, _ = self._socket_pair()
        old_generation = self._claim(old_conn)
        self._set_owned_channel(old_conn, old_generation, verified=True)
        send_entered = threading.Event()
        release_send = threading.Event()
        send_results: list[dict[str, str]] = []

        def blocked_send(*_args, **_kwargs):
            send_entered.set()
            self.assertTrue(release_send.wait(2))
            raise OSError("stale send failed")

        with mock.patch.object(backend, "_send_frame", side_effect=blocked_send):
            send_thread, failures = self._start_thread(
                lambda: send_results.append(backend.send_message("secret"))
            )
            self.assertTrue(send_entered.wait(2))
            backend._fail_active_channel(
                old_conn,
                old_generation,
                ConnectionError("old connection released"),
            )
            new_conn, _ = self._socket_pair()
            new_generation = self._claim(new_conn)
            self._set_owned_channel(new_conn, new_generation, verified=True)
            release_send.set()
            self._join(send_thread)

        self.assertEqual([], failures)
        self.assertEqual("error", send_results[0]["status"])
        self.assertTrue(backend._is_peer_session_owner(new_conn, new_generation))
        state = backend.poll_messages()
        self.assertEqual("confirmed", state["channel_status"])
        self.assertTrue(state["encrypted"])
        self.assertTrue(state["verified"])

    def test_new_valid_handshake_succeeds_while_old_finally_is_delayed(self):
        old_conn, _ = self._socket_pair()
        old_generation = self._claim(old_conn)
        reader_entered = threading.Event()
        release_reader = threading.Event()

        def blocked_reader(_conn: socket.socket, _generation: int):
            reader_entered.set()
            self.assertTrue(release_reader.wait(2))

        with mock.patch.object(backend, "_read_socket_messages", side_effect=blocked_reader):
            old_thread, old_failures = self._start_thread(
                lambda: backend._peer_session(
                    old_conn,
                    "host",
                    old_generation,
                    handshake_complete=True,
                )
            )
            self.assertTrue(reader_entered.wait(2))
            backend._fail_active_channel(
                old_conn,
                old_generation,
                ConnectionError("malicious connection failed"),
            )

            new_conn, new_remote = self._socket_pair()
            new_generation = self._claim(new_conn)
            peer_key = PrivateKey.generate()
            peer_thread, peer_failures = self._start_thread(
                lambda: _peer_protocol(new_remote, peer_key, role="guest")
            )
            backend._perform_handshake(new_conn, "host", new_generation)
            self._join(peer_thread)
            release_reader.set()
            self._join(old_thread)

        self.assertEqual([], peer_failures)
        self.assertEqual([], old_failures)
        self.assertTrue(backend._is_peer_session_owner(new_conn, new_generation))
        state = backend.poll_messages()
        self.assertEqual("confirmed", state["channel_status"])
        self.assertTrue(state["encrypted"])


if __name__ == "__main__":
    unittest.main()
