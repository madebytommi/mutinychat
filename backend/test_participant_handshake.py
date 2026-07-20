from __future__ import annotations

import base64
import json
import socket
import threading
import time
import unittest

import nacl.exceptions
from nacl.public import Box, PrivateKey, PublicKey

import main as backend
from participant_auth import (
    PROTOCOL_VERSION,
    build_channel_challenge_payload,
    build_channel_response_payload,
    derive_handshake_transcript_hash,
    parse_channel_challenge_payload,
    parse_channel_response_payload,
)


TEST_ONION = "a" * 56 + ".onion"


def _read_frame(sock: socket.socket) -> dict:
    data = bytearray()
    while True:
        chunk = sock.recv(1)
        if not chunk:
            raise ConnectionError("socket closed")
        if chunk == b"\n":
            return json.loads(data.decode("utf-8"))
        data.extend(chunk)


def _send_frame(sock: socket.socket, frame: dict) -> None:
    sock.sendall((json.dumps(frame, separators=(",", ":")) + "\n").encode("utf-8"))


def _peer_protocol(
    sock: socket.socket,
    key: PrivateKey,
    *,
    role: str,
    nonce: bytes = b"r" * 32,
    version: int = PROTOCOL_VERSION,
    behavior: str = "valid",
    advertised_key: PrivateKey | None = None,
    replayed_challenge_frame: dict | None = None,
    captured_challenges: list[dict] | None = None,
) -> None:
    local_hello = _read_frame(sock)
    advertised = advertised_key or key
    hello = {
        "type": "hello",
        "v": version,
        "role": role,
        "public_key": base64.b64encode(bytes(advertised.public_key)).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
    }
    _send_frame(sock, hello)
    if behavior == "hello_only" or version != PROTOCOL_VERSION:
        return

    local_public_key = base64.b64decode(local_hello["public_key"], validate=True)
    local_nonce = base64.b64decode(local_hello["nonce"], validate=True)
    if role == "host":
        host_key, guest_key = bytes(advertised.public_key), local_public_key
        host_nonce, guest_nonce = nonce, local_nonce
        expected_local_role = "guest"
    else:
        host_key, guest_key = local_public_key, bytes(advertised.public_key)
        host_nonce, guest_nonce = local_nonce, nonce
        expected_local_role = "host"
    transcript = derive_handshake_transcript_hash(
        host_key,
        guest_key,
        TEST_ONION,
        host_nonce,
        guest_nonce,
    )
    box = Box(key, PublicKey(local_public_key))
    local_challenge_frame = _read_frame(sock)

    if behavior == "reflected_challenge":
        _send_frame(sock, local_challenge_frame)
        return
    if behavior == "malformed_ciphertext":
        _send_frame(sock, {"type": "channel_challenge", "ciphertext": "!!!!"})
        return
    if replayed_challenge_frame is not None:
        _send_frame(sock, replayed_challenge_frame)
        return

    local_challenge_payload = box.decrypt(
        base64.b64decode(local_challenge_frame["ciphertext"], validate=True)
    ).decode("utf-8")
    local_challenge = parse_channel_challenge_payload(
        local_challenge_payload,
        expected_local_role,
        transcript,
    )
    peer_challenge = b"p" * 32
    challenge_role = expected_local_role if behavior == "wrong_role" else role
    challenge_transcript = b"x" * 32 if behavior == "wrong_transcript" else transcript
    challenge_ciphertext = base64.b64encode(
        bytes(
            box.encrypt(
                build_channel_challenge_payload(
                    challenge_role,
                    challenge_transcript,
                    peer_challenge,
                ).encode("utf-8")
            )
        )
    ).decode("ascii")
    challenge_frame = {"type": "channel_challenge", "ciphertext": challenge_ciphertext}
    if captured_challenges is not None:
        captured_challenges.append(challenge_frame)
    _send_frame(sock, challenge_frame)
    if behavior in {"wrong_role", "wrong_transcript"}:
        return

    local_response_frame = _read_frame(sock)
    local_response_payload = box.decrypt(
        base64.b64decode(local_response_frame["ciphertext"], validate=True)
    ).decode("utf-8")
    self_response = parse_channel_response_payload(
        local_response_payload,
        expected_local_role,
        transcript,
    )
    if self_response != peer_challenge:
        raise AssertionError("Local endpoint did not answer the peer challenge")
    if behavior == "one_sided":
        time.sleep(0.3)
        return
    if behavior == "duplicate_challenge":
        _send_frame(sock, challenge_frame)
        return

    response = b"z" * 32 if behavior == "wrong_response" else local_challenge
    response_ciphertext = base64.b64encode(
        bytes(
            box.encrypt(
                build_channel_response_payload(role, transcript, response).encode("utf-8")
            )
        )
    ).decode("ascii")
    _send_frame(sock, {"type": "channel_response", "ciphertext": response_ciphertext})


class ParticipantHandshakeTestCase(unittest.TestCase):
    def setUp(self):
        backend.close_room()
        backend._reset_crypto()
        backend._active_room = {"mode": "guest", "onion_address": TEST_ONION}
        backend.stop_event.clear()
        self.original_timeout = backend.HANDSHAKE_TIMEOUT

    def tearDown(self):
        backend.HANDSHAKE_TIMEOUT = self.original_timeout
        backend.close_room()

    def _claim(self, sock: socket.socket) -> int:
        generation = backend._claim_active_peer_socket(sock)
        self.assertIsNotNone(generation)
        return generation

    def _run_peer(self, target, *args, **kwargs):
        failures = []

        def run():
            try:
                target(*args, **kwargs)
            except Exception as exc:
                failures.append(exc)
            finally:
                if args and isinstance(args[0], socket.socket):
                    try:
                        args[0].close()
                    except OSError:
                        pass

        thread = threading.Thread(target=run)
        thread.peer_failures = failures
        thread.start()
        return thread

    def _join_peer(
        self,
        thread: threading.Thread,
        *,
        expected_failure: type[BaseException] | tuple[type[BaseException], ...] | None = None,
    ) -> None:
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive(), "Peer protocol thread did not finish")
        failures = getattr(thread, "peer_failures", [])
        if expected_failure is not None:
            self.assertEqual(1, len(failures), "Expected one peer protocol failure")
            self.assertIsInstance(failures[0], expected_failure)
        elif failures:
            raise failures[0]

    def test_correct_mutual_challenge_response_confirms_channel(self):
        local, remote = socket.socketpair()
        generation = self._claim(local)
        expected_host = PrivateKey.generate()
        thread = self._run_peer(_peer_protocol, remote, expected_host, role="host")
        try:
            backend._perform_handshake(
                local,
                "guest",
                generation,
                bytes(expected_host.public_key),
            )
            state = backend.poll_messages()
            self.assertEqual("confirmed", state["channel_status"])
            self.assertTrue(state["encrypted"])
            self.assertFalse(state["verified"])
            self.assertEqual("unverified", state["identity_status"])
        finally:
            backend._fail_active_channel(
                local,
                generation,
                ConnectionError("Test handshake cleanup"),
            )
            local.close()
            remote.close()
            self._join_peer(thread)

    def test_guest_rejects_substituted_host_key(self):
        local, remote = socket.socketpair()
        generation = self._claim(local)
        expected_host = PrivateKey.generate()
        attacker = PrivateKey.generate()
        thread = self._run_peer(
            _peer_protocol, remote, attacker, role="host", behavior="hello_only"
        )
        try:
            with self.assertRaisesRegex(ValueError, "does not match"):
                backend._perform_handshake(
                    local,
                    "guest",
                    generation,
                    bytes(expected_host.public_key),
                )
            self._assert_failed_and_cleared()
        finally:
            backend._fail_active_channel(
                local,
                generation,
                ConnectionError("Test handshake cleanup"),
            )
            local.close()
            remote.close()
            self._join_peer(thread)

    def test_peer_lacking_advertised_private_key_cannot_confirm(self):
        local, remote = socket.socketpair()
        generation = self._claim(local)
        advertised = PrivateKey.generate()
        wrong_private_key = PrivateKey.generate()
        thread = self._run_peer(
            _peer_protocol,
            remote,
            wrong_private_key,
            role="host",
            advertised_key=advertised,
        )
        try:
            with self.assertRaises((nacl.exceptions.CryptoError, ConnectionError)):
                backend._perform_handshake(
                    local,
                    "guest",
                    generation,
                    bytes(advertised.public_key),
                )
            self._assert_failed_and_cleared()
        finally:
            local.close()
            remote.close()
            self._join_peer(thread, expected_failure=nacl.exceptions.CryptoError)

    def test_protocol_v2_peer_is_rejected_without_downgrade(self):
        local, remote = socket.socketpair()
        generation = self._claim(local)
        host = PrivateKey.generate()
        thread = self._run_peer(
            _peer_protocol,
            remote,
            host,
            role="host",
            version=2,
        )
        try:
            with self.assertRaisesRegex(ValueError, "both participants must update"):
                backend._perform_handshake(
                    local,
                    "guest",
                    generation,
                    bytes(host.public_key),
                )
            self._assert_failed_and_cleared()
        finally:
            local.close()
            remote.close()
            self._join_peer(thread)

    def test_reflected_encrypted_challenge_is_rejected(self):
        self._assert_malicious_behavior_fails("reflected_challenge", "role")

    def test_wrong_role_is_rejected(self):
        self._assert_malicious_behavior_fails("wrong_role", "role")

    def test_wrong_transcript_is_rejected(self):
        self._assert_malicious_behavior_fails("wrong_transcript", "transcript")

    def test_malformed_ciphertext_is_rejected(self):
        self._assert_malicious_behavior_fails("malformed_ciphertext", "malformed")

    def test_duplicate_or_out_of_order_challenge_is_rejected(self):
        self._assert_malicious_behavior_fails("duplicate_challenge", "Expected peer channel_response")

    def test_wrong_challenge_response_is_rejected(self):
        self._assert_malicious_behavior_fails("wrong_response", "does not answer")

    def test_one_sided_completion_times_out_and_cleans_candidate(self):
        backend.HANDSHAKE_TIMEOUT = 0.1
        self._assert_malicious_behavior_fails("one_sided", "timed out")

    def test_disconnect_during_handshake_cleans_candidate(self):
        local, remote = socket.socketpair()
        generation = self._claim(local)

        def disconnect_after_hello():
            _read_frame(remote)
            remote.close()

        thread = self._run_peer(disconnect_after_hello)
        try:
            with self.assertRaises(ConnectionError):
                backend._perform_handshake(local, "guest", generation)
            self._assert_failed_and_cleared()
        finally:
            local.close()
            self._join_peer(thread)

    def test_prior_session_challenge_replay_is_rejected(self):
        peer_key = PrivateKey.generate()
        captured = []
        first_local, first_remote = socket.socketpair()
        first_generation = self._claim(first_local)
        first = self._run_peer(
            _peer_protocol,
            first_remote,
            peer_key,
            role="guest",
            nonce=b"g" * 32,
            captured_challenges=captured,
        )
        try:
            backend._perform_handshake(first_local, "host", first_generation)
        finally:
            first_local.close()
            first_remote.close()
            self._join_peer(first)

        backend._fail_active_channel(
            first_local,
            first_generation,
            ConnectionError("Test session complete"),
        )
        backend._reset_participant_verification(preserve_private_key=True)
        second_local, second_remote = socket.socketpair()
        second_generation = self._claim(second_local)
        second = self._run_peer(
            _peer_protocol,
            second_remote,
            peer_key,
            role="guest",
            nonce=b"g" * 32,
            replayed_challenge_frame=captured[0],
        )
        try:
            with self.assertRaisesRegex(ValueError, "transcript"):
                backend._perform_handshake(second_local, "host", second_generation)
            self._assert_failed_and_cleared()
        finally:
            second_local.close()
            second_remote.close()
            self._join_peer(second)

    def test_valid_connection_succeeds_after_failed_malicious_attempt(self):
        self._assert_malicious_behavior_fails("reflected_challenge", "role")
        local, remote = socket.socketpair()
        generation = self._claim(local)
        guest = PrivateKey.generate()
        thread = self._run_peer(_peer_protocol, remote, guest, role="guest")
        try:
            backend._perform_handshake(local, "host", generation)
            self.assertEqual("confirmed", backend.poll_messages()["channel_status"])
        finally:
            local.close()
            remote.close()
            self._join_peer(thread)

    def _assert_malicious_behavior_fails(self, behavior: str, error_pattern: str):
        local, remote = socket.socketpair()
        generation = self._claim(local)
        host = PrivateKey.generate()
        thread = self._run_peer(
            _peer_protocol,
            remote,
            host,
            role="host",
            behavior=behavior,
        )
        try:
            with self.assertRaisesRegex(
                (ValueError, TimeoutError, nacl.exceptions.CryptoError),
                error_pattern,
            ):
                backend._perform_handshake(
                    local,
                    "guest",
                    generation,
                    bytes(host.public_key),
                )
            self._assert_failed_and_cleared()
        finally:
            backend._fail_active_channel(
                local,
                generation,
                ConnectionError("Test handshake cleanup"),
            )
            local.close()
            remote.close()
            self._join_peer(thread)

    def _assert_failed_and_cleared(self):
        state = backend.poll_messages()
        self.assertEqual("failed", state["channel_status"])
        self.assertFalse(state["encrypted"])
        self.assertFalse(state["verified"])
        self.assertIsNone(backend._box)
        self.assertIsNone(backend._peer_public_key)
        self.assertIsNone(backend._handshake_transcript_hash)
        self.assertFalse(backend.handshake_event.is_set())
        self.assertFalse(backend.verification_event.is_set())


if __name__ == "__main__":
    unittest.main()
