import json
import unittest

from nacl.public import PrivateKey

from participant_auth import (
    CHANNEL_CHALLENGE_BYTES,
    HANDSHAKE_NONCE_BYTES,
    MAX_INVITE_CHARS,
    PROTOCOL_VERSION,
    build_channel_challenge_payload,
    build_channel_response_payload,
    build_confirmation_payload,
    build_invite,
    derive_handshake_transcript_hash,
    derive_safety_code,
    parse_channel_challenge_payload,
    parse_channel_response_payload,
    parse_invite,
    validate_confirmation_payload,
)


class ParticipantAuthenticationTestCase(unittest.TestCase):
    def setUp(self):
        self.onion = "a" * 56 + ".onion"
        self.host = PrivateKey.generate()
        self.guest = PrivateKey.generate()
        self.host_nonce = b"h" * HANDSHAKE_NONCE_BYTES
        self.guest_nonce = b"g" * HANDSHAKE_NONCE_BYTES

    def safety_code(self) -> str:
        return derive_safety_code(
            bytes(self.host.public_key),
            bytes(self.guest.public_key),
            self.onion,
            self.host_nonce,
            self.guest_nonce,
        )

    def test_authenticated_invite_round_trip(self):
        invite = build_invite(self.onion, bytes(self.host.public_key))
        parsed = parse_invite(invite)
        self.assertEqual(PROTOCOL_VERSION, parsed.protocol_version)
        self.assertEqual(self.onion, parsed.onion_address)
        self.assertEqual(bytes(self.host.public_key), parsed.host_public_key)

    def test_raw_onion_is_not_an_authenticated_invite(self):
        with self.assertRaisesRegex(ValueError, "complete authenticated"):
            parse_invite(self.onion)

    def test_invite_rejects_host_key_substitution_or_malformed_key(self):
        invite = build_invite(self.onion, bytes(self.host.public_key))
        malformed = invite.replace("host_key=", "host_key=short")
        with self.assertRaises(ValueError):
            parse_invite(malformed)

    def test_invite_rejects_padded_noncanonical_host_key(self):
        invite = build_invite(self.onion, bytes(self.host.public_key))
        with self.assertRaisesRegex(ValueError, "canonically"):
            parse_invite(invite + "%3D")

    def test_invite_rejects_oversized_input(self):
        with self.assertRaisesRegex(ValueError, "too long"):
            parse_invite("x" * (MAX_INVITE_CHARS + 1))

    def test_protocol_v2_invite_is_rejected_without_downgrade(self):
        invite = build_invite(self.onion, bytes(self.host.public_key)).replace("v=3", "v=2")
        with self.assertRaisesRegex(ValueError, "both participants must update"):
            parse_invite(invite)

    def test_safety_code_is_bound_to_roles_keys_onion_and_nonces(self):
        code = self.safety_code()
        self.assertRegex(code, r"^\d{5} \d{5} \d{5} \d{5}$")

        self.assertNotEqual(
            code,
            derive_safety_code(
                bytes(self.guest.public_key),
                bytes(self.host.public_key),
                self.onion,
                self.guest_nonce,
                self.host_nonce,
            ),
        )
        self.assertNotEqual(
            code,
            derive_safety_code(
                bytes(self.host.public_key),
                bytes(self.guest.public_key),
                "b" * 56 + ".onion",
                self.host_nonce,
                self.guest_nonce,
            ),
        )
        self.assertNotEqual(
            code,
            derive_safety_code(
                bytes(self.host.public_key),
                bytes(PrivateKey.generate().public_key),
                self.onion,
                self.host_nonce,
                self.guest_nonce,
            ),
        )
        self.assertNotEqual(
            code,
            derive_safety_code(
                bytes(self.host.public_key),
                bytes(self.guest.public_key),
                self.onion,
                b"x" * HANDSHAKE_NONCE_BYTES,
                self.guest_nonce,
            ),
        )

    def test_safety_code_rejects_invalid_nonce_length(self):
        with self.assertRaisesRegex(ValueError, "nonces"):
            derive_safety_code(
                bytes(self.host.public_key),
                bytes(self.guest.public_key),
                self.onion,
                b"short",
                self.guest_nonce,
            )

    def test_confirmation_payload_must_match_session_code(self):
        code = self.safety_code()
        transcript = derive_handshake_transcript_hash(
            bytes(self.host.public_key),
            bytes(self.guest.public_key),
            self.onion,
            self.host_nonce,
            self.guest_nonce,
        )
        payload = build_confirmation_payload(code, "host", transcript)
        validate_confirmation_payload(payload, code, "host", transcript)
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_confirmation_payload(
                payload,
                "00000 00000 00000 00000",
                "host",
                transcript,
            )

    def test_channel_payloads_are_role_and_transcript_bound(self):
        transcript = derive_handshake_transcript_hash(
            bytes(self.host.public_key),
            bytes(self.guest.public_key),
            self.onion,
            self.host_nonce,
            self.guest_nonce,
        )
        challenge = b"c" * CHANNEL_CHALLENGE_BYTES
        challenge_payload = build_channel_challenge_payload("host", transcript, challenge)
        response_payload = build_channel_response_payload("guest", transcript, challenge)
        self.assertEqual(
            challenge,
            parse_channel_challenge_payload(challenge_payload, "host", transcript),
        )
        self.assertEqual(
            challenge,
            parse_channel_response_payload(response_payload, "guest", transcript),
        )
        with self.assertRaisesRegex(ValueError, "role"):
            parse_channel_challenge_payload(challenge_payload, "guest", transcript)
        with self.assertRaisesRegex(ValueError, "transcript"):
            parse_channel_response_payload(response_payload, "guest", b"x" * 32)

    def test_channel_payload_rejects_malformed_challenge_encoding(self):
        transcript = derive_handshake_transcript_hash(
            bytes(self.host.public_key),
            bytes(self.guest.public_key),
            self.onion,
            self.host_nonce,
            self.guest_nonce,
        )
        value = json.loads(
            build_channel_challenge_payload(
                "host", transcript, b"c" * CHANNEL_CHALLENGE_BYTES
            )
        )
        value["challenge"] = "!!!!"
        payload = json.dumps(value, separators=(",", ":"))
        with self.assertRaisesRegex(ValueError, "malformed"):
            parse_channel_challenge_payload(payload, "host", transcript)


if __name__ == "__main__":
    unittest.main()
