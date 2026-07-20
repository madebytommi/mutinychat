"""Participant-authentication helpers for MutinyChat invitations and sessions."""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlsplit

PROTOCOL_VERSION = 3
INVITE_SCHEME = "mutinychat"
INVITE_HOST = "join"
PUBLIC_KEY_BYTES = 32
HANDSHAKE_NONCE_BYTES = 32
CHANNEL_CHALLENGE_BYTES = 32
TRANSCRIPT_HASH_BYTES = 32
SAFETY_CODE_DIGITS = 20
MAX_INVITE_CHARS = 512
ONION_V3_RE = re.compile(r"^[a-z2-7]{56}\.onion$", re.IGNORECASE)
TRANSCRIPT_DOMAIN = b"MutinyChat channel transcript v3"


@dataclass(frozen=True)
class AuthenticatedInvite:
    onion_address: str
    host_public_key: bytes
    protocol_version: int = PROTOCOL_VERSION


def encode_public_key(raw: bytes) -> str:
    if len(raw) != PUBLIC_KEY_BYTES:
        raise ValueError("Public key has an invalid length")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_public_key(value: str) -> bytes:
    encoded = value.strip()
    if not encoded:
        raise ValueError("Invitation host key is missing")
    try:
        padding = "=" * (-len(encoded) % 4)
        raw = base64.b64decode(encoded + padding, altchars=b"-_", validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Invitation host key is malformed") from exc
    if len(raw) != PUBLIC_KEY_BYTES:
        raise ValueError("Invitation host key has an invalid length")
    if not hmac.compare_digest(encode_public_key(raw), encoded):
        raise ValueError("Invitation host key is not canonically encoded")
    return raw


def _validate_onion(value: str) -> str:
    onion = value.strip().lower()
    if not ONION_V3_RE.fullmatch(onion):
        raise ValueError("Invitation contains an invalid v3 onion address")
    return onion


def build_invite(onion_address: str, host_public_key: bytes) -> str:
    onion = _validate_onion(onion_address)
    query = urlencode(
        {
            "v": str(PROTOCOL_VERSION),
            "onion": onion,
            "host_key": encode_public_key(host_public_key),
        }
    )
    return f"{INVITE_SCHEME}://{INVITE_HOST}?{query}"


def parse_invite(value: str) -> AuthenticatedInvite:
    raw = value.strip()
    if not raw or len(raw) > MAX_INVITE_CHARS:
        raise ValueError("Invitation link is missing or too long")
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise ValueError("Invitation link is malformed") from exc

    if parsed.scheme.lower() != INVITE_SCHEME or parsed.netloc.lower() != INVITE_HOST:
        raise ValueError("Paste the complete authenticated MutinyChat invitation")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invitation link contains an invalid port") from exc
    if parsed.path not in ("", "/") or parsed.fragment or parsed.username or parsed.password or port:
        raise ValueError("Invitation link contains unsupported components")

    try:
        query = parse_qs(parsed.query, strict_parsing=True, keep_blank_values=True)
    except ValueError as exc:
        raise ValueError("Invitation query is malformed") from exc

    expected_fields = {"v", "onion", "host_key"}
    if set(query) != expected_fields or any(len(values) != 1 for values in query.values()):
        raise ValueError("Invitation must contain exactly one version, onion address, and host key")

    try:
        version = int(query["v"][0])
    except ValueError as exc:
        raise ValueError("Invitation protocol version is invalid") from exc
    if version != PROTOCOL_VERSION:
        if version == 2:
            raise ValueError(
                "Invitation protocol version 2 is incompatible; both participants must update "
                "to protocol version 3"
            )
        raise ValueError(f"Invitation protocol version {version} is unsupported; update required")

    return AuthenticatedInvite(
        onion_address=_validate_onion(query["onion"][0]),
        host_public_key=decode_public_key(query["host_key"][0]),
        protocol_version=version,
    )


def _encode_fixed_bytes(value: bytes, expected_length: int, label: str) -> str:
    if len(value) != expected_length:
        raise ValueError(f"{label} has an invalid length")
    return base64.b64encode(value).decode("ascii")


def _decode_fixed_bytes(value: str, expected_length: int, label: str) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError(f"{label} is malformed") from exc
    if len(raw) != expected_length:
        raise ValueError(f"{label} has an invalid length")
    if not hmac.compare_digest(_encode_fixed_bytes(raw, expected_length, label), value):
        raise ValueError(f"{label} is not canonically encoded")
    return raw


def _validate_role(role: str) -> str:
    if role not in {"host", "guest"}:
        raise ValueError("Participant role must be host or guest")
    return role


def derive_handshake_transcript_hash(
    host_public_key: bytes,
    guest_public_key: bytes,
    onion_address: str,
    host_nonce: bytes,
    guest_nonce: bytes,
) -> bytes:
    if len(host_public_key) != PUBLIC_KEY_BYTES or len(guest_public_key) != PUBLIC_KEY_BYTES:
        raise ValueError("Handshake transcript keys must each be 32 bytes")
    if len(host_nonce) != HANDSHAKE_NONCE_BYTES or len(guest_nonce) != HANDSHAKE_NONCE_BYTES:
        raise ValueError("Handshake transcript nonces must each be 32 bytes")
    onion = _validate_onion(onion_address).encode("ascii")
    transcript = b"\x00".join(
        (
            TRANSCRIPT_DOMAIN,
            str(PROTOCOL_VERSION).encode("ascii"),
            onion,
            b"host-role",
            b"host",
            b"host-key",
            bytes(host_public_key),
            b"guest-role",
            b"guest",
            b"guest-key",
            bytes(guest_public_key),
            b"host-nonce",
            bytes(host_nonce),
            b"guest-nonce",
            bytes(guest_nonce),
        )
    )
    return hashlib.sha256(transcript).digest()


def derive_safety_code(
    host_public_key: bytes,
    guest_public_key: bytes,
    onion_address: str,
    host_nonce: bytes,
    guest_nonce: bytes,
) -> str:
    digest = derive_handshake_transcript_hash(
        host_public_key,
        guest_public_key,
        onion_address,
        host_nonce,
        guest_nonce,
    )
    number = int.from_bytes(digest[:9], "big") % (10**SAFETY_CODE_DIGITS)
    digits = f"{number:0{SAFETY_CODE_DIGITS}d}"
    return " ".join(digits[index : index + 5] for index in range(0, SAFETY_CODE_DIGITS, 5))


def build_channel_challenge_payload(
    sender_role: str,
    transcript_hash: bytes,
    challenge: bytes,
) -> str:
    return json.dumps(
        {
            "type": "channel_challenge",
            "v": PROTOCOL_VERSION,
            "role": _validate_role(sender_role),
            "transcript": _encode_fixed_bytes(
                transcript_hash, TRANSCRIPT_HASH_BYTES, "Handshake transcript hash"
            ),
            "challenge": _encode_fixed_bytes(
                challenge, CHANNEL_CHALLENGE_BYTES, "Channel challenge"
            ),
        },
        separators=(",", ":"),
    )


def parse_channel_challenge_payload(
    payload: str,
    expected_role: str,
    expected_transcript_hash: bytes,
) -> bytes:
    value = _parse_protocol_payload(payload, "channel_challenge")
    if set(value) != {"type", "v", "role", "transcript", "challenge"}:
        raise ValueError("Peer channel challenge has unexpected fields")
    _validate_expected_role_and_transcript(value, expected_role, expected_transcript_hash)
    return _decode_fixed_bytes(
        str(value.get("challenge", "")), CHANNEL_CHALLENGE_BYTES, "Peer channel challenge"
    )


def build_channel_response_payload(
    sender_role: str,
    transcript_hash: bytes,
    response: bytes,
) -> str:
    return json.dumps(
        {
            "type": "channel_response",
            "v": PROTOCOL_VERSION,
            "role": _validate_role(sender_role),
            "transcript": _encode_fixed_bytes(
                transcript_hash, TRANSCRIPT_HASH_BYTES, "Handshake transcript hash"
            ),
            "response": _encode_fixed_bytes(
                response, CHANNEL_CHALLENGE_BYTES, "Channel challenge response"
            ),
        },
        separators=(",", ":"),
    )


def parse_channel_response_payload(
    payload: str,
    expected_role: str,
    expected_transcript_hash: bytes,
) -> bytes:
    value = _parse_protocol_payload(payload, "channel_response")
    if set(value) != {"type", "v", "role", "transcript", "response"}:
        raise ValueError("Peer channel response has unexpected fields")
    _validate_expected_role_and_transcript(value, expected_role, expected_transcript_hash)
    return _decode_fixed_bytes(
        str(value.get("response", "")), CHANNEL_CHALLENGE_BYTES, "Peer channel response"
    )


def _parse_protocol_payload(payload: str, expected_type: str) -> dict[str, object]:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Peer {expected_type.replace('_', ' ')} is malformed") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Peer {expected_type.replace('_', ' ')} must be an object")
    if value.get("type") != expected_type or value.get("v") != PROTOCOL_VERSION:
        raise ValueError(f"Peer {expected_type.replace('_', ' ')} has an unsupported format")
    return value


def _validate_expected_role_and_transcript(
    value: dict[str, object],
    expected_role: str,
    expected_transcript_hash: bytes,
) -> None:
    if value.get("role") != _validate_role(expected_role):
        raise ValueError("Peer confirmation role is invalid")
    received_hash = _decode_fixed_bytes(
        str(value.get("transcript", "")),
        TRANSCRIPT_HASH_BYTES,
        "Peer handshake transcript hash",
    )
    if not hmac.compare_digest(received_hash, expected_transcript_hash):
        raise ValueError("Peer confirmation does not match this handshake transcript")


def build_confirmation_payload(
    safety_code: str,
    sender_role: str,
    transcript_hash: bytes,
) -> str:
    return json.dumps(
        {
            "type": "participant_verification",
            "v": PROTOCOL_VERSION,
            "role": _validate_role(sender_role),
            "transcript": _encode_fixed_bytes(
                transcript_hash, TRANSCRIPT_HASH_BYTES, "Handshake transcript hash"
            ),
            "code": safety_code,
        },
        separators=(",", ":"),
    )


def validate_confirmation_payload(
    payload: str,
    expected_safety_code: str,
    expected_role: str,
    expected_transcript_hash: bytes,
) -> None:
    value = _parse_protocol_payload(payload, "participant_verification")
    if set(value) != {"type", "v", "role", "transcript", "code"}:
        raise ValueError("Peer verification confirmation has unexpected fields")
    _validate_expected_role_and_transcript(value, expected_role, expected_transcript_hash)
    received = str(value.get("code", ""))
    if not hmac.compare_digest(received, expected_safety_code):
        raise ValueError("Peer verification confirmation does not match this session")
