from pathlib import Path

path = Path(__file__).resolve().parent / "apply-c2-participant-auth.py"
text = path.read_text(encoding="utf-8")
start_marker = '''test_main = replace_once(
    test_main,
    "        backend._private_key = alice\\n"'''
end_marker = '''    "wrong-key active room",
)
'''
start = text.find(start_marker)
if start < 0:
    raise RuntimeError("Could not find duplicate test patch start")
end = text.find(end_marker, start)
if end < 0:
    raise RuntimeError("Could not find duplicate test patch end")
end += len(end_marker)
replacement = '''peer_install_block = (
    "        backend._private_key = alice\\n"
    "        backend._install_peer_public_key(base64.b64encode(bytes(bob.public_key)).decode(\\"ascii\\"))\\n"
)
peer_install_with_room = (
    "        backend._private_key = alice\\n"
    "        backend._active_room = {\\"onion_address\\": \\"a\\" * 56 + \\".onion\\"}\\n"
    "        backend._install_peer_public_key(base64.b64encode(bytes(bob.public_key)).decode(\\"ascii\\"))\\n"
)
if test_main.count(peer_install_block) != 2:
    raise RuntimeError(
        f"Expected two peer-key test blocks, found {test_main.count(peer_install_block)}"
    )
test_main = test_main.replace(peer_install_block, peer_install_with_room, 2)
'''
path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")
print("Updated C2 patch script duplicate-test handling.")
