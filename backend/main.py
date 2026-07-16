"""MutinyChat peer-to-peer backend.

The backend owns Tor lifecycle, a single peer socket, ephemeral session keys,
and the newline-delimited JSON protocol used by the Tauri process over stdio.
The peer protocol is also newline-delimited JSON, with messages encrypted using
an ephemeral PyNaCl Box after both peers exchange public keys.
"""

from __future__ import annotations

import argparse
import atexit
import base64
import