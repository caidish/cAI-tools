#!/usr/bin/env python3
"""
Escalation Client - Shared library for communicating with the escalation service.

Provides functions for connecting to the service, sending commands,
and starting the service if needed.
"""
from __future__ import annotations

import fcntl
import json
import os
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path


# Default configuration - use ~/.claude/run for runtime files
DEFAULT_SOCKET = Path("~/.claude/run/escalation.sock").expanduser()
DEFAULT_LOCKFILE = Path("~/.claude/run/escalation.lock").expanduser()
# Service script is relative to this file
SERVICE_SCRIPT = Path(__file__).parent / "escalation_service.py"


class EscalationClient:
    """Client for communicating with the escalation service."""

    def __init__(self, socket_path: Path = DEFAULT_SOCKET):
        self.socket_path = socket_path
        self.lockfile_path = DEFAULT_LOCKFILE

    def connect(self, timeout: float = 5.0, retries: int = 2) -> socket.socket | None:
        """Connect to the escalation service with retry logic."""
        for attempt in range(retries + 1):
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                sock.connect(str(self.socket_path))
                return sock
            except (ConnectionRefusedError, FileNotFoundError, OSError) as e:
                if attempt < retries:
                    # Wait with exponential backoff
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                return None
        return None

    def _recv_exact(self, sock: socket.socket, n: int) -> bytes | None:
        """Receive exactly n bytes, handling partial reads."""
        data = b""
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def send_command(self, sock: socket.socket, command: dict) -> dict | None:
        """Send a command and receive response using length-prefixed framing."""
        try:
            # Send command
            encoded = json.dumps(command).encode("utf-8")
            length = struct.pack("!I", len(encoded))
            sock.sendall(length + encoded)

            # Receive response (handle partial reads)
            length_data = self._recv_exact(sock, 4)
            if length_data is None:
                return None

            length = struct.unpack("!I", length_data)[0]
            if length > 1024 * 1024:  # Max 1MB
                return None

            data = self._recv_exact(sock, length)
            if data is None:
                return None

            return json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, struct.error, socket.timeout, OSError):
            return None
        finally:
            sock.close()

    def is_running(self) -> bool:
        """Check if the service is running."""
        sock = self.connect(timeout=2, retries=0)
        if sock:
            sock.close()
            return True
        return False

    def start_service_if_needed(self) -> bool:
        """Start the escalation service if not already running.

        Uses a lockfile to prevent race conditions when multiple hooks
        try to start the service simultaneously.
        """
        if self.is_running():
            return True

        # Ensure lockfile directory exists
        self.lockfile_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Use lockfile to prevent concurrent starts
            lockfile = open(self.lockfile_path, "w")
            try:
                fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                # Another process is starting the service
                lockfile.close()
                time.sleep(1)
                return self.is_running()

            try:
                # Double-check after acquiring lock
                if self.is_running():
                    return True

                # Start the service
                if not SERVICE_SCRIPT.exists():
                    print(f"Service script not found: {SERVICE_SCRIPT}", file=sys.stderr)
                    return False

                # Start in background, detached
                subprocess.Popen(
                    [sys.executable, str(SERVICE_SCRIPT)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )

                # Wait for service to be ready
                for _ in range(20):  # Wait up to 2 seconds
                    time.sleep(0.1)
                    if self.is_running():
                        return True

                return False
            finally:
                fcntl.flock(lockfile.fileno(), fcntl.LOCK_UN)
                lockfile.close()
        except Exception as e:
            print(f"Error starting service: {e}", file=sys.stderr)
            return False

    def add_escalation(
        self,
        escalation_id: str,
        message: str,
        delays: list[int] | None = None,
        auto_start: bool = True,
    ) -> dict | None:
        """Add an escalation timer."""
        if auto_start:
            self.start_service_if_needed()

        sock = self.connect()
        if not sock:
            return None

        command = {
            "command": "add",
            "escalation_id": escalation_id,
            "message": message,
        }
        if delays:
            command["delays"] = delays

        return self.send_command(sock, command)

    def cancel_escalation(self, escalation_id: str) -> dict | None:
        """Cancel an escalation timer."""
        sock = self.connect()
        if not sock:
            return None

        return self.send_command(sock, {
            "command": "cancel",
            "escalation_id": escalation_id,
        })

    def get_status(self) -> dict | None:
        """Get list of pending escalations."""
        sock = self.connect()
        if not sock:
            return None

        return self.send_command(sock, {"command": "status"})

    def shutdown_service(self) -> dict | None:
        """Request service shutdown."""
        sock = self.connect()
        if not sock:
            return None

        return self.send_command(sock, {"command": "shutdown"})

    def register_session(self, session_id: str | None = None, pid: int | None = None) -> dict | None:
        """Register a new session with optional PID for tracking."""
        sock = self.connect()
        if not sock:
            return None

        cmd = {"command": "register_session"}
        if session_id:
            cmd["session_id"] = session_id
        if pid:
            cmd["pid"] = pid

        return self.send_command(sock, cmd)

    def unregister_session(self, session_id: str | None = None) -> dict | None:
        """Unregister a session (decrement ref count, may shutdown if 0)."""
        sock = self.connect()
        if not sock:
            return None

        cmd = {"command": "unregister_session"}
        if session_id:
            cmd["session_id"] = session_id

        return self.send_command(sock, cmd)


# Convenience functions for simple usage
_client: EscalationClient | None = None


def get_client() -> EscalationClient:
    """Get or create a shared client instance."""
    global _client
    if _client is None:
        _client = EscalationClient()
    return _client


def add_escalation(escalation_id: str, message: str, delays: list[int] | None = None) -> dict | None:
    """Add an escalation timer (convenience function)."""
    return get_client().add_escalation(escalation_id, message, delays)


def cancel_escalation(escalation_id: str) -> dict | None:
    """Cancel an escalation timer (convenience function)."""
    return get_client().cancel_escalation(escalation_id)


def start_service() -> bool:
    """Start the escalation service if needed (convenience function)."""
    return get_client().start_service_if_needed()


def shutdown_service() -> dict | None:
    """Shutdown the escalation service (convenience function)."""
    return get_client().shutdown_service()


def get_status() -> dict | None:
    """Get service status (convenience function)."""
    return get_client().get_status()


def register_session(session_id: str | None = None, pid: int | None = None) -> dict | None:
    """Register a session (convenience function)."""
    return get_client().register_session(session_id=session_id, pid=pid)


def unregister_session(session_id: str | None = None) -> dict | None:
    """Unregister a session (convenience function)."""
    return get_client().unregister_session(session_id=session_id)
