"""
engine/local_server.py — local HTTP server for the Vahaduo static site.

Spawns a Python http.server subprocess pointed at the cloned engine directory,
on an automatically selected free port. Use as a context manager.

Example
-------
    with LocalVahaduoServer(engine_path) as url:
        # url = "http://localhost:54321"
        run_vahaduo(url, ...)
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


class LocalVahaduoServer:
    """
    Context manager that serves the Vahaduo static site over localhost HTTP.

    Parameters
    ----------
    engine_path:
        Root directory of the cloned Vahaduo site (data/vahaduo_engine/).
    port:
        Port to bind to. Pass 0 to auto-select a free port (default).
    startup_timeout:
        Seconds to wait for the server to respond before raising RuntimeError.
    """

    def __init__(
        self,
        engine_path: Path,
        port: int = 0,
        startup_timeout: float = 10.0,
    ) -> None:
        if not engine_path.exists():
            raise FileNotFoundError(
                f"Vahaduo engine not found at {engine_path}. "
                "Run 'python scripts/bootstrap.py' first."
            )
        self._engine_path = engine_path
        self._port = port
        self._startup_timeout = startup_timeout
        self._process: subprocess.Popen | None = None
        self._url: str = ""

    # ------------------------------------------------------------------
    # Context manager interface
    # ------------------------------------------------------------------

    def __enter__(self) -> str:
        port = self._resolve_port()
        self._process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "http.server",
                str(port),
                "--directory",
                str(self._engine_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._url = f"http://localhost:{port}"
        self._wait_for_ready()
        return self._url

    def __exit__(self, *args: object) -> None:
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_port(self) -> int:
        """Return the configured port, or find a free one if port=0."""
        if self._port != 0:
            return self._port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    def _wait_for_ready(self) -> None:
        """Poll the server URL until it responds or the timeout expires."""
        deadline = time.monotonic() + self._startup_timeout
        while time.monotonic() < deadline:
            try:
                urllib.request.urlopen(self._url, timeout=1)
                return  # server is up
            except (urllib.error.URLError, ConnectionRefusedError):
                time.sleep(0.1)
        raise RuntimeError(
            f"Local Vahaduo server did not respond within "
            f"{self._startup_timeout}s at {self._url}"
        )
