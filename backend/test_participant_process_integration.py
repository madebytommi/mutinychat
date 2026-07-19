import json
import socket
import subprocess
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent
HELPER = BACKEND_DIR / "participant_process_helper.py"
PROCESS_TIMEOUT = 20


def _pick_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _last_json_line(output: str) -> dict:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        raise AssertionError("Protocol helper produced no output")
    return json.loads(lines[-1])


class ParticipantProcessIntegrationTestCase(unittest.TestCase):
    def test_two_independent_processes_verify_and_exchange_encrypted_messages(self):
        port = _pick_port()
        host = subprocess.Popen(
            [sys.executable, str(HELPER), "--role", "host", "--port", str(port)],
            cwd=BACKEND_DIR,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(lambda: host.poll() is None and host.kill())

        self.assertIsNotNone(host.stdout)
        ready_line = host.stdout.readline().strip()
        ready = json.loads(ready_line)
        self.assertTrue(ready["ready"])
        self.assertRegex(ready["host_public_key"], r"^[A-Za-z0-9+/]{43}=$")

        guest = subprocess.Popen(
            [
                sys.executable,
                str(HELPER),
                "--role",
                "guest",
                "--port",
                str(port),
                "--expected-host-key",
                ready["host_public_key"],
            ],
            cwd=BACKEND_DIR,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(lambda: guest.poll() is None and guest.kill())

        guest_stdout, guest_stderr = guest.communicate(timeout=PROCESS_TIMEOUT)
        host_stdout, host_stderr = host.communicate(timeout=PROCESS_TIMEOUT)

        self.assertEqual(0, host.returncode, host_stderr)
        self.assertEqual(0, guest.returncode, guest_stderr)
        host_result = _last_json_line(host_stdout)
        guest_result = _last_json_line(guest_stdout)

        self.assertTrue(host_result["encrypted"])
        self.assertTrue(guest_result["encrypted"])
        self.assertTrue(host_result["verified"])
        self.assertTrue(guest_result["verified"])
        self.assertEqual(host_result["verification_code"], guest_result["verification_code"])
        self.assertRegex(
            host_result["verification_code"],
            r"^\d{5} \d{5} \d{5} \d{5}$",
        )
        self.assertEqual("guest-message", host_result["received"])
        self.assertEqual("host-message", guest_result["received"])


if __name__ == "__main__":
    unittest.main()
