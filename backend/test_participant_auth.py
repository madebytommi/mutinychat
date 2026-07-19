import unittest

from nacl.public import PrivateKey

from participant_auth import (
    PROTOCOL_VERSION,
    build_confirmation_payload,
    build_invite,
    derive_safety_code,
    parse_invite,
    validate_confirmation_payload,
)


class ParticipantAuthenticationTestCase(unittest.TestCase):
    def setUp(self):
        self.onion = "a" * 56 + ".onion"
        self.host = PrivateKey.generate()
        self.guest = PrivateKey.generate()

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

    def test_safety_code_is_symmetric_and_session_bound(self):
        host_key = bytes(self.host.public_key)
        guest_key = bytes(self.guest.public_key)
        host_code = derive_safety_code(host_key, guest_key, self.onion)
        guest_code = derive_safety_code(guest_key, host_key, self.onion)
        self.assertEqual(host_code, guest_code)
        self.assertRegex(host_code, r"^\d{5} \d{5} \d{5} \d{5}$")

        other_onion = "b" * 56 + ".onion"
        self.assertNotEqual(host_code, derive_safety_code(host_key, guest_key, other_onion))
        self.assertNotEqual(
            host_code,
            derive_safety_code(host_key, bytes(PrivateKey.generate().public_key), self.onion),
        )

    def test_confirmation_payload_must_match_session_code(self):
        code = derive_safety_code(
            bytes(self.host.public_key), bytes(self.guest.public_key), self.onion
        )
        payload = build_confirmation_payload(code)
        validate_confirmation_payload(payload, code)
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_confirmation_payload(payload, "00000 00000 00000 00000")


if __name__ == "__main__":
    unittest.main()
