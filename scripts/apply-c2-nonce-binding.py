from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one {label} block, found {count}")
    return text.replace(old, new, 1)


def replace_between(text: str, start: str, end: str, replacement: str, label: str) -> str:
    start_index = text.find(start)
    if start_index < 0:
        raise RuntimeError(f"Missing start marker for {label}")
    end_index = text.find(end, start_index)
    if end_index < 0:
        raise RuntimeError(f"Missing end marker for {label}")
    return text[:start_index] + replacement + text[end_index:]


main_path = ROOT / "backend" / "main.py"
main = main_path.read_text(encoding="utf-8")
main = replace_once(main, "import re\nimport shutil\n", "import re\nimport secrets\nimport shutil\n", "secrets import")
main = replace_once(
    main,
    "from participant_auth import (\n    PROTOCOL_VERSION,\n",
    "from participant_auth import (\n    HANDSHAKE_NONCE_BYTES,\n    PROTOCOL_VERSION,\n",
    "nonce constant import",
)

key_block = '''def _install_peer_public_key(value: str, expected_public_key: Optional[bytes] = None) -> None:
    global _peer_public_key, _box
    raw = base64.b64decode(value, validate=True)
    if len(raw) != 32:
        raise ValueError("Peer public key has an invalid length")
    if expected_public_key is not None and not hmac.compare_digest(raw, expected_public_key):
        raise ValueError("The host key does not match the authenticated invitation")
    with state_lock:
        if _private_key is None:
            raise RuntimeError("Local session key is unavailable")
        _peer_public_key = bytes(raw)
        _box = Box(_private_key, PublicKey(raw))
        handshake_event.set()
        verification_event.clear()


def _encode_handshake_nonce(value: bytes) -> str:
    if len(value) != HANDSHAKE_NONCE_BYTES:
        raise ValueError("Handshake nonce has an invalid length")
    return base64.b64encode(value).decode("ascii")


def _decode_handshake_nonce(value: str) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Peer handshake nonce is malformed") from exc
    if len(raw) != HANDSHAKE_NONCE_BYTES:
        raise ValueError("Peer handshake nonce has an invalid length")
    if not hmac.compare_digest(_encode_handshake_nonce(raw), value):
        raise ValueError("Peer handshake nonce is not canonically encoded")
    return raw


def _set_verification_code(mode: str, local_nonce: bytes, peer_nonce: bytes) -> None:
    global _verification_code
    onion = _room_onion_address()
    with state_lock:
        if _private_key is None or _peer_public_key is None:
            raise RuntimeError("Session keys are unavailable for participant verification")
        local_public_key = bytes(_private_key.public_key)
        peer_public_key = bytes(_peer_public_key)
        if mode == "host":
            host_key, guest_key = local_public_key, peer_public_key
            host_nonce, guest_nonce = local_nonce, peer_nonce
        elif mode == "guest":
            host_key, guest_key = peer_public_key, local_public_key
            host_nonce, guest_nonce = peer_nonce, local_nonce
        else:
            raise ValueError("Participant verification mode must be host or guest")
        _verification_code = derive_safety_code(
            host_key,
            guest_key,
            onion,
            host_nonce,
            guest_nonce,
        )


'''
main = replace_between(
    main,
    "def _install_peer_public_key(value: str, expected_public_key: Optional[bytes] = None) -> None:\n",
    "def encrypt_message(message: str) -> str:\n",
    key_block,
    "peer key and verification transcript",
)

old_handshake = '''def _perform_handshake(
    conn: socket.socket,
    mode: str,
    expected_host_public_key: Optional[bytes] = None,
) -> None:
    if mode not in {"host", "guest"}:
        raise ValueError("Handshake mode must be host or guest")
    peer_role = "guest" if mode == "host" else "host"
    _send_frame(
        conn,
        {
            "type": "hello",
            "v": PROTOCOL_VERSION,
            "role": mode,
            "public_key": _public_key_b64(),
        },
    )
    frame = _receive_handshake_frame(conn)
    kind = str(frame.get("type", ""))
    if kind == "error":
        raise RuntimeError(str(frame.get("message", "Peer refused the connection")))
    if kind != "hello":
        raise ValueError(f"Expected peer hello frame, received {kind or '<empty>'}")
    if frame.get("v") != PROTOCOL_VERSION:
        raise ValueError("Peer protocol version is incompatible")
    if frame.get("role") != peer_role:
        raise ValueError("Peer handshake role is invalid")
    expected_key = expected_host_public_key if mode == "guest" else None
    _install_peer_public_key(str(frame.get("public_key", "")), expected_key)
    if _box is None or not handshake_event.is_set() or not _verification_code:
        raise RuntimeError("Secure session handshake did not establish participant verification")


'''
new_handshake = '''def _perform_handshake(
    conn: socket.socket,
    mode: str,
    expected_host_public_key: Optional[bytes] = None,
) -> None:
    if mode not in {"host", "guest"}:
        raise ValueError("Handshake mode must be host or guest")
    peer_role = "guest" if mode == "host" else "host"
    local_nonce = secrets.token_bytes(HANDSHAKE_NONCE_BYTES)
    _send_frame(
        conn,
        {
            "type": "hello",
            "v": PROTOCOL_VERSION,
            "role": mode,
            "public_key": _public_key_b64(),
            "nonce": _encode_handshake_nonce(local_nonce),
        },
    )
    frame = _receive_handshake_frame(conn)
    kind = str(frame.get("type", ""))
    if kind == "error":
        raise RuntimeError(str(frame.get("message", "Peer refused the connection")))
    if kind != "hello":
        raise ValueError(f"Expected peer hello frame, received {kind or '<empty>'}")
    if frame.get("v") != PROTOCOL_VERSION:
        raise ValueError("Peer protocol version is incompatible")
    if frame.get("role") != peer_role:
        raise ValueError("Peer handshake role is invalid")
    peer_nonce = _decode_handshake_nonce(str(frame.get("nonce", "")))
    expected_key = expected_host_public_key if mode == "guest" else None
    _install_peer_public_key(str(frame.get("public_key", "")), expected_key)
    _set_verification_code(mode, local_nonce, peer_nonce)
    if _box is None or not handshake_event.is_set() or not _verification_code:
        raise RuntimeError("Secure session handshake did not establish participant verification")


'''
main = replace_once(main, old_handshake, new_handshake, "nonce-bound handshake")
main_path.write_text(main, encoding="utf-8")


test_main_path = ROOT / "backend" / "test_main.py"
test_main = test_main_path.read_text(encoding="utf-8")
old_code_test = '''        backend._install_peer_public_key(
            base64.b64encode(bytes(remote.public_key)).decode("ascii")
        )
        state = backend.poll_messages()
'''
new_code_test = '''        backend._install_peer_public_key(
            base64.b64encode(bytes(remote.public_key)).decode("ascii")
        )
        backend._set_verification_code("host", b"h" * 32, b"g" * 32)
        state = backend.poll_messages()
'''
test_main = replace_once(test_main, old_code_test, new_code_test, "verification-code test setup")
old_confirmation_test = '''        backend._install_peer_public_key(
            base64.b64encode(bytes(bob.public_key)).decode("ascii")
        )
        backend._verification_local_confirmed = True
        code = backend.poll_messages()["verification_code"]
'''
new_confirmation_test = '''        backend._install_peer_public_key(
            base64.b64encode(bytes(bob.public_key)).decode("ascii")
        )
        backend._set_verification_code("host", b"h" * 32, b"g" * 32)
        backend._verification_local_confirmed = True
        code = backend.poll_messages()["verification_code"]
'''
test_main = replace_once(test_main, old_confirmation_test, new_confirmation_test, "confirmation test setup")
test_main_path.write_text(test_main, encoding="utf-8")


handshake_test_path = ROOT / "backend" / "test_participant_handshake.py"
handshake_test = handshake_test_path.read_text(encoding="utf-8")
handshake_test = replace_once(
    handshake_test,
    "import socket\nimport threading\n",
    "import socket\nimport threading\n",
    "stable import anchor",
)
old_send_hello = '''def _send_hello(
    sock: socket.socket,
    key: PrivateKey,
    *,
    version: int = PROTOCOL_VERSION,
    role: str = "host",
) -> None:
    _read_line(sock)
    frame = {
        "type": "hello",
        "v": version,
        "role": role,
        "public_key": base64.b64encode(bytes(key.public_key)).decode("ascii"),
    }
    sock.sendall((json.dumps(frame, separators=(",", ":")) + "\\n").encode("utf-8"))
'''
new_send_hello = '''def _send_hello(
    sock: socket.socket,
    key: PrivateKey,
    *,
    version: int = PROTOCOL_VERSION,
    role: str = "host",
    nonce: bytes = b"r" * 32,
) -> None:
    _read_line(sock)
    frame = {
        "type": "hello",
        "v": version,
        "role": role,
        "public_key": base64.b64encode(bytes(key.public_key)).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
    }
    sock.sendall((json.dumps(frame, separators=(",", ":")) + "\\n").encode("utf-8"))
'''
handshake_test = replace_once(handshake_test, old_send_hello, new_send_hello, "test hello nonce")
replay_test = '''    def test_replayed_guest_hello_gets_a_fresh_safety_code(self):
        guest_key = PrivateKey.generate()
        replayed_nonce = b"g" * 32
        codes = []
        for _ in range(2):
            backend._reset_participant_verification(preserve_private_key=True)
            local, remote = socket.socketpair()
            thread = threading.Thread(
                target=_send_hello,
                args=(remote, guest_key),
                kwargs={"role": "guest", "nonce": replayed_nonce},
            )
            thread.start()
            try:
                backend._perform_handshake(local, "host")
                codes.append(backend.poll_messages()["verification_code"])
            finally:
                local.close()
                remote.close()
                thread.join(timeout=2)
        self.assertNotEqual(codes[0], codes[1])

'''
marker = "    def test_host_session_key_remains_bound_to_existing_invitation(self):\n"
if replay_test.strip() not in handshake_test:
    if marker not in handshake_test:
        raise RuntimeError("Handshake replay-test insertion marker missing")
    handshake_test = handshake_test.replace(marker, replay_test + marker, 1)
handshake_test_path.write_text(handshake_test, encoding="utf-8")

print("Applied fresh-nonce binding to the participant handshake.")
