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

PROTOCOL_VERSION = 2
INVITE_SCHEME = "mutinychat"
INVITE_HOST = "join"
PUBLIC_KEY_BYTES = 32
HANDSHAKE_NONCE_BYTES = 32
SAFETY_CODE_DIGITS = 20
MAX_INVITE_CHARS = 512
ONION_V3_RE = re.compile(r"^[a-z2-7]{56}\.onion$", re.IGNORECASE)


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
        raise ValueError(f"Invitation protocol version {version} is unsupported")

    return AuthenticatedInvite(
        onion_address=_validate_onion(query["onion"][0]),
        host_public_key=decode_public_key(query["host_key"][0]),
        protocol_version=version,
    )


def derive_safety_code(
    host_public_key: bytes,
    guest_public_key: bytes,
    onion_address: str,
    host_nonce: bytes,
    guest_nonce: bytes,
) -> str:
    if len(host_public_key) != PUBLIC_KEY_BYTES or len(guest_public_key) != PUBLIC_KEY_BYTES:
        raise ValueError("Safety-code keys must each be 32 bytes")
    if len(host_nonce) != HANDSHAKE_NONCE_BYTES or len(guest_nonce) != HANDSHAKE_NONCE_BYTES:
        raise ValueError("Safety-code handshake nonces must each be 32 bytes")
    onion = _validate_onion(onion_address).encode("ascii")
    transcript = b"\x00".join(
        (
            b"MutinyChat participant safety code",
            str(PROTOCOL_VERSION).encode("ascii"),
            onion,
            b"host-key",
            bytes(host_public_key),
            b"guest-key",
            bytes(guest_public_key),
            b"host-nonce",
            bytes(host_nonce),
            b"guest-nonce",
            bytes(guest_nonce),
        )
    )
    digest = hashlib.sha256(transcript).digest()
    number = int.from_bytes(digest[:9], "big") % (10**SAFETY_CODE_DIGITS)
    digits = f"{number:0{SAFETY_CODE_DIGITS}d}"
    return " ".join(digits[index : index + 5] for index in range(0, SAFETY_CODE_DIGITS, 5))


def build_confirmation_payload(safety_code: str) -> str:
    return json.dumps(
        {
            "type": "participant_verification",
            "v": PROTOCOL_VERSION,
            "code": safety_code,
        },
        separators=(",", ":"),
    )


def validate_confirmation_payload(payload: str, expected_safety_code: str) -> None:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("Peer verification confirmation is malformed") from exc
    if not isinstance(value, dict):
        raise ValueError("Peer verification confirmation must be an object")
    if value.get("type") != "participant_verification" or value.get("v") != PROTOCOL_VERSION:
        raise ValueError("Peer verification confirmation has an unsupported format")
    received = str(value.get("code", ""))
    if not hmac.compare_digest(received, expected_safety_code):
        raise ValueError("Peer verification confirmation does not match this session")
