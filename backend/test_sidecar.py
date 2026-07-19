import unittest

import main as backend
import sidecar


class SidecarConfigurationTestCase(unittest.TestCase):
    def test_install_sets_windows_timeouts_without_replacing_protocol(self):
        original_join = backend.join_room
        original_handle_guest = backend._handle_guest
        original_peer_session = backend._peer_session

        sidecar.install()

        self.assertIs(backend.join_room, original_join)
        self.assertIs(backend._handle_guest, original_handle_guest)
        self.assertIs(backend._peer_session, original_peer_session)
        self.assertEqual(60, backend.CONNECT_TIMEOUT)
        self.assertEqual(30, backend.HANDSHAKE_TIMEOUT)


if __name__ == "__main__":
    unittest.main()
