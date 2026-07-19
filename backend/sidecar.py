"""Windows sidecar entrypoint using the shared authenticated backend protocol."""
from __future__ import annotations

import main as backend

CONNECT_TIMEOUT = 60
HANDSHAKE_TIMEOUT = 30


def install() -> None:
    """Use Windows-friendly timeouts without replacing protocol functions."""
    backend.CONNECT_TIMEOUT = CONNECT_TIMEOUT
    backend.HANDSHAKE_TIMEOUT = HANDSHAKE_TIMEOUT


if __name__ == "__main__":
    install()
    backend.main()
