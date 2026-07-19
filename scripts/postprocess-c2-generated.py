from pathlib import Path

root = Path(__file__).resolve().parents[1]

main_path = root / "backend" / "main.py"
main = main_path.read_text(encoding="utf-8")
old = '''def _release_failed_host_connection(conn: socket.socket, exc: Exception) -> None:
    global _peer_count
    with peer_lock:
        if active_peer_socket is conn:
            globals()["active_peer_socket"] = None
'''
new = '''def _release_failed_host_connection(conn: socket.socket, exc: Exception) -> None:
    global active_peer_socket, _peer_count
    with peer_lock:
        if active_peer_socket is conn:
            active_peer_socket = None
'''
if old not in main:
    raise RuntimeError("Generated host-connection cleanup block was not found")
main_path.write_text(main.replace(old, new, 1), encoding="utf-8")

test_path = root / "backend" / "test_main.py"
test = test_path.read_text(encoding="utf-8")
if "from participant_auth import build_confirmation_payload" not in test:
    test = test.replace(
        "from nacl.public import Box, PrivateKey\n\nimport main as backend\n",
        "from nacl.public import Box, PrivateKey\n\nfrom participant_auth import build_confirmation_payload\nimport main as backend\n",
        1,
    )

marker = "    def test_disconnect_frame_stops_reader(self):\n"
extra_tests = '''    def test_encrypted_peer_confirmation_completes_verification(self):
        alice = PrivateKey.generate()
        bob = PrivateKey.generate()
        backend._private_key = alice
        backend._active_room = {"onion_address": "a" * 56 + ".onion"}
        backend._install_peer_public_key(
            base64.b64encode(bytes(bob.public_key)).decode("ascii")
        )
        backend._verification_local_confirmed = True
        code = backend.poll_messages()["verification_code"]
        bob_box = Box(bob, alice.public_key)
        ciphertext = base64.b64encode(
            bytes(bob_box.encrypt(build_confirmation_payload(code).encode("utf-8")))
        ).decode("ascii")

        backend._handle_peer_verification(ciphertext)

        state = backend.poll_messages()
        self.assertTrue(state["verified"])
        self.assertTrue(state["verification_local_confirmed"])
        self.assertTrue(state["verification_peer_confirmed"])

    def test_verified_message_is_sent_as_ciphertext(self):
        alice = PrivateKey.generate()
        bob = PrivateKey.generate()
        left, right = socket.socketpair()
        try:
            backend._private_key = alice
            backend._active_room = {"onion_address": "a" * 56 + ".onion"}
            backend._install_peer_public_key(
                base64.b64encode(bytes(bob.public_key)).decode("ascii")
            )
            backend.active_peer_socket = left
            backend.verification_event.set()

            result = backend.send_message("secret")
            raw = right.recv(4096).split(b"\\n", 1)[0]
            frame = json.loads(raw.decode("utf-8"))
            self.assertEqual({"status": "sent"}, result)
            self.assertEqual("message", frame["type"])
            self.assertNotIn("secret", raw.decode("utf-8"))
            plaintext = Box(bob, alice.public_key).decrypt(
                base64.b64decode(frame["ciphertext"], validate=True)
            ).decode("utf-8")
            self.assertEqual("secret", plaintext)
        finally:
            backend.active_peer_socket = None
            left.close()
            right.close()

    def test_raw_onion_join_is_rejected_before_network_access(self):
        response = backend.handle_json_command(
            {"cmd": "join_room", "message": "a" * 56 + ".onion"}
        )
        self.assertIn("authenticated", response["error"].lower())

'''
if "test_encrypted_peer_confirmation_completes_verification" not in test:
    if marker not in test:
        raise RuntimeError("Could not find test insertion marker")
    test = test.replace(marker, extra_tests + marker, 1)

test = test.replace(
    "        self.assertFalse(backend.handshake_event.is_set())\n",
    "        self.assertFalse(backend.handshake_event.is_set())\n        self.assertFalse(backend.verification_event.is_set())\n",
    1,
)
test_path.write_text(test, encoding="utf-8")

print("Postprocessed generated participant-authentication files.")
