#!/usr/bin/env python3
"""
Escalation Service - Persistent notification escalation manager for Claude Code.

Listens on a Unix socket for commands to add/cancel escalation timers.
Uses a single scheduler thread with a heap for efficient timer management.

Commands (JSON over socket with 4-byte length prefix):
- add: Start escalation timers for a session
- cancel: Cancel pending timers for a session
- status: Return list of pending escalations
- shutdown: Graceful shutdown

Usage:
    python3 escalation_service.py [--socket PATH] [--log PATH]
"""

from __future__ import annotations

import argparse
import heapq
import json
import logging
import os
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


# Default configuration - use ~/.claude/run for runtime files
DEFAULT_SOCKET = Path("~/.claude/run/escalation.sock").expanduser()
DEFAULT_LOG = Path("~/.claude/logs/escalation.log").expanduser()
DEFAULT_DELAYS = [60, 3600]  # 1 min, 1 hour
PRIORITIES = {60: 0, 3600: 2}  # delay -> priority mapping
PID_CHECK_INTERVAL = 60  # Check for dead PIDs every 60 seconds

# po_notify relative to plugin root (scripts/service -> tools/pushover-notify)
PO_NOTIFY_SCRIPT = Path(__file__).parent.parent.parent / "tools" / "pushover-notify" / "po_notify.py"


@dataclass(order=True)
class ScheduledEvent:
    """A scheduled notification event."""
    fire_time: float
    escalation_id: str = field(compare=False)
    message: str = field(compare=False)
    priority: int = field(compare=False)
    cancelled: bool = field(default=False, compare=False)


class EscalationScheduler:
    """Single-threaded scheduler using a heap and condition variable."""

    def __init__(self, notify_callback):
        self.heap: list[ScheduledEvent] = []
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.running = True
        self.notify_callback = notify_callback
        self.events_by_id: dict[str, list[ScheduledEvent]] = {}
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def add(self, escalation_id: str, message: str, delays: list[int]) -> None:
        """Add escalation timers for the given ID."""
        with self.condition:
            # Cancel existing timers for this ID
            self._cancel_internal(escalation_id)

            # Create new events
            now = time.time()
            events = []
            for delay in delays:
                priority = PRIORITIES.get(delay, 0)
                event = ScheduledEvent(
                    fire_time=now + delay,
                    escalation_id=escalation_id,
                    message=message,
                    priority=priority,
                )
                heapq.heappush(self.heap, event)
                events.append(event)

            self.events_by_id[escalation_id] = events
            self.condition.notify()

    def cancel(self, escalation_id: str) -> bool:
        """Cancel all pending timers for the given ID."""
        with self.condition:
            return self._cancel_internal(escalation_id)

    def _cancel_internal(self, escalation_id: str) -> bool:
        """Internal cancel without lock (must be called with lock held)."""
        if escalation_id in self.events_by_id:
            for event in self.events_by_id[escalation_id]:
                event.cancelled = True
            del self.events_by_id[escalation_id]
            return True
        return False

    def status(self) -> list[dict]:
        """Return list of pending escalations."""
        with self.lock:
            result = []
            # Build set of event IDs still in heap for O(1) lookup (using id() for identity)
            heap_ids = {id(e) for e in self.heap}
            for eid, events in self.events_by_id.items():
                # Only count events that are not cancelled AND still in heap (not yet fired)
                active_events = [e for e in events if not e.cancelled and id(e) in heap_ids]
                if active_events:
                    next_fire = min(e.fire_time for e in active_events)
                    result.append({
                        "escalation_id": eid,
                        "message": active_events[0].message,
                        "pending_count": len(active_events),
                        "next_fire_in": max(0, next_fire - time.time()),
                    })
            return result

    def shutdown(self) -> None:
        """Stop the scheduler thread."""
        with self.condition:
            self.running = False
            self.condition.notify()
        self.thread.join(timeout=5)

    def _cleanup_fired_events(self, escalation_id: str) -> None:
        """Remove escalation from events_by_id if all events have fired."""
        if escalation_id in self.events_by_id:
            events = self.events_by_id[escalation_id]
            # Check if all events are cancelled or have fired (not in heap)
            # Use id() for identity-based check since ScheduledEvent is unhashable
            heap_ids = {id(e) for e in self.heap}
            active = [e for e in events if not e.cancelled and id(e) in heap_ids]
            if not active:
                del self.events_by_id[escalation_id]

    def _run(self) -> None:
        """Main scheduler loop."""
        while True:
            with self.condition:
                if not self.running:
                    break

                # Find next event to fire
                while self.heap and self.heap[0].cancelled:
                    heapq.heappop(self.heap)

                if not self.heap:
                    # No events, wait indefinitely
                    self.condition.wait()
                    continue

                next_event = self.heap[0]
                wait_time = next_event.fire_time - time.time()

                if wait_time > 0:
                    # Wait until next event or notification
                    self.condition.wait(timeout=wait_time)
                    continue

                # Time to fire
                heapq.heappop(self.heap)
                escalation_id = next_event.escalation_id

                # Clean up fired events from memory
                self._cleanup_fired_events(escalation_id)

            # Fire event outside the lock
            if not next_event.cancelled:
                self.notify_callback(
                    next_event.escalation_id,
                    next_event.message,
                    next_event.priority,
                )


class EscalationService:
    """Unix socket server for escalation management."""

    def __init__(self, socket_path: Path, log_path: Path):
        self.socket_path = socket_path
        self.log_path = log_path
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.scheduler: Optional[EscalationScheduler] = None
        # PID-tracked sessions: {session_id: {"pid": int, "registered_at": float}}
        self.sessions: dict[str, dict] = {}
        self.session_lock = threading.Lock()
        self._setup_logging()

    def _setup_logging(self) -> None:
        """Configure logging with rotation."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        handler = RotatingFileHandler(
            self.log_path,
            maxBytes=1024 * 1024,  # 1MB
            backupCount=3,
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s"
        ))

        self.logger = logging.getLogger("escalation")
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(handler)

        # Also log to stderr for debugging
        stderr_handler = logging.StreamHandler()
        stderr_handler.setFormatter(logging.Formatter(
            "[%(levelname)s] %(message)s"
        ))
        self.logger.addHandler(stderr_handler)

    def _is_pid_alive(self, pid: int) -> bool:
        """Check if a PID is still running."""
        try:
            os.kill(pid, 0)  # Signal 0 = check existence without killing
            return True
        except OSError:
            return False

    def _is_session_busy(self, session_id: str) -> bool:
        """Check if a session's process is busy (tool running).

        A session is considered busy if:
        1. The main Claude process CPU > 10%, OR
        2. There are child processes (bash commands, etc.)
        """
        if not HAS_PSUTIL:
            return False

        with self.session_lock:
            session = self.sessions.get(session_id)
            if not session or not session.get("pid"):
                return False
            pid = session["pid"]

        try:
            proc = psutil.Process(pid)

            # Check 1: Does the main process have high CPU?
            cpu = proc.cpu_percent(interval=0.5)
            cpu_busy = cpu > 10

            # Check 2: Are there child processes?
            children = proc.children(recursive=True)
            has_children = len(children) > 0

            is_busy = cpu_busy or has_children
            self.logger.info(
                f"Busy check for {session_id[:8]}...: cpu={cpu:.1f}%, children={len(children)}, busy={is_busy}"
            )
            return is_busy
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False

    def _cleanup_dead_sessions(self) -> None:
        """Remove sessions whose PIDs are no longer alive."""
        with self.session_lock:
            dead = []
            for session_id, info in self.sessions.items():
                pid = info.get("pid")
                if pid and not self._is_pid_alive(pid):
                    dead.append((session_id, pid))

            for session_id, pid in dead:
                del self.sessions[session_id]
                self.logger.info(f"Auto-unregistered dead session: {session_id} (pid={pid})")

            if not self.sessions and dead:
                self.logger.info("No sessions remaining after cleanup, shutting down")
                self.running = False

    def _start_pid_checker(self) -> None:
        """Start background thread to check for dead PIDs."""
        def checker():
            while self.running:
                time.sleep(PID_CHECK_INTERVAL)
                if self.running:
                    self._cleanup_dead_sessions()

        thread = threading.Thread(target=checker, daemon=True)
        thread.start()
        self.logger.info(f"PID checker started (interval={PID_CHECK_INTERVAL}s)")

    def _cleanup_socket(self) -> None:
        """Remove stale socket file if it exists."""
        if self.socket_path.exists():
            # Verify it's actually a socket file before attempting cleanup
            import stat
            try:
                mode = self.socket_path.stat().st_mode
                if not stat.S_ISSOCK(mode):
                    self.logger.error(f"Path exists but is not a socket: {self.socket_path}")
                    sys.exit(1)
            except OSError as e:
                self.logger.error(f"Cannot stat socket path: {e}")
                sys.exit(1)

            # Try to connect to see if another instance is running
            test_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                test_sock.settimeout(1)
                test_sock.connect(str(self.socket_path))
                # Another instance is running
                self.logger.error("Another instance is already running")
                sys.exit(1)
            except (ConnectionRefusedError, socket.timeout, OSError):
                # Stale socket, remove it
                self.logger.info("Removing stale socket file")
                self.socket_path.unlink()
            finally:
                test_sock.close()

    def _send_notification(self, escalation_id: str, message: str, priority: int) -> None:
        """Send notification via po_notify."""
        # Check if session is busy (tool running) - skip notification if so
        if self._is_session_busy(escalation_id):
            self.logger.info(f"Skipping notification for {escalation_id[:8]}... (session busy, tool running)")
            return

        po_notify = PO_NOTIFY_SCRIPT

        title = "Claude Permission" if priority < 2 else "Claude Permission (1hr)"

        self.logger.info(f"Sending notification: {title} - {message[:50]}... (priority {priority})")

        try:
            cmd = [str(po_notify), title, message, "--priority", str(priority)]
            if priority == 2:
                cmd.extend(["--retry", "60", "--expire", "3600"])

            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                timeout=10,
            )
            self.logger.info(f"Notification sent for {escalation_id}")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Notification failed: {e.stderr.decode()}")
        except FileNotFoundError:
            self.logger.error("po_notify not found")
        except Exception as e:
            self.logger.error(f"Notification error: {e}")

    def _recv_exact(self, conn: socket.socket, n: int) -> Optional[bytes]:
        """Receive exactly n bytes, handling partial reads."""
        data = b""
        while len(data) < n:
            chunk = conn.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def _recv_message(self, conn: socket.socket) -> Optional[dict]:
        """Receive a length-prefixed JSON message."""
        try:
            # Read 4-byte length prefix (handle partial reads)
            length_data = self._recv_exact(conn, 4)
            if length_data is None:
                return None

            length = struct.unpack("!I", length_data)[0]
            if length > 1024 * 1024:  # Max 1MB message
                return None

            # Read message data (handle partial reads)
            data = self._recv_exact(conn, length)
            if data is None:
                return None

            return json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, struct.error, OSError):
            return None

    def _send_message(self, conn: socket.socket, data: dict) -> bool:
        """Send a length-prefixed JSON message."""
        try:
            encoded = json.dumps(data).encode("utf-8")
            length = struct.pack("!I", len(encoded))
            conn.sendall(length + encoded)
            return True
        except OSError:
            return False

    def _handle_command(self, cmd: dict) -> dict:
        """Process a command and return response."""
        assert self.scheduler is not None, "Scheduler not initialized"
        command = cmd.get("command", "")

        if command == "add":
            escalation_id = cmd.get("escalation_id") or cmd.get("session_id", "unknown")
            message = cmd.get("message", "Awaiting permission")
            delays = cmd.get("delays", DEFAULT_DELAYS)

            self.scheduler.add(escalation_id, message, delays)
            self.logger.info(f"Added escalation: {escalation_id}")
            return {"status": "ok", "escalation_id": escalation_id}

        elif command == "cancel":
            escalation_id = cmd.get("escalation_id") or cmd.get("session_id", "")
            cancelled = self.scheduler.cancel(escalation_id)
            self.logger.info(f"Cancel escalation: {escalation_id} (found={cancelled})")
            return {"status": "ok", "cancelled": cancelled}

        elif command == "status":
            pending = self.scheduler.status()
            with self.session_lock:
                sessions_info = {
                    sid: {
                        "pid": info.get("pid"),
                        "registered_at": info.get("registered_at"),
                        "age": time.time() - info.get("registered_at", time.time()),
                    }
                    for sid, info in self.sessions.items()
                }
            return {
                "status": "ok",
                "pending": pending,
                "session_count": len(sessions_info),
                "sessions": sessions_info,
            }

        elif command == "register_session":
            session_id = cmd.get("session_id", f"session-{time.time()}")
            pid = cmd.get("pid")
            with self.session_lock:
                self.sessions[session_id] = {
                    "pid": pid,
                    "registered_at": time.time(),
                }
                count = len(self.sessions)
            self.logger.info(f"Session registered: {session_id} (pid={pid}, count={count})")
            return {"status": "ok", "session_id": session_id, "session_count": count}

        elif command == "unregister_session":
            session_id = cmd.get("session_id")
            should_shutdown = False
            with self.session_lock:
                if session_id and session_id in self.sessions:
                    del self.sessions[session_id]
                elif self.sessions:
                    # Fallback: remove oldest session if no ID specified
                    oldest = min(self.sessions.items(), key=lambda x: x[1].get("registered_at", 0))
                    del self.sessions[oldest[0]]
                    session_id = oldest[0]
                count = len(self.sessions)
                if count == 0:
                    should_shutdown = True
            self.logger.info(f"Session unregistered: {session_id} (count={count})")
            if should_shutdown:
                self.logger.info("No more sessions, shutting down")
                self.running = False
            return {"status": "ok", "session_id": session_id, "session_count": count, "shutting_down": should_shutdown}

        elif command == "shutdown":
            # Force shutdown regardless of session count
            self.logger.info("Force shutdown requested")
            self.running = False
            return {"status": "ok", "message": "shutting down"}

        else:
            return {"status": "error", "message": f"unknown command: {command}"}

    def _handle_client(self, conn: socket.socket, _addr: Any) -> None:
        """Handle a single client connection."""
        try:
            conn.settimeout(30)
            msg = self._recv_message(conn)
            if msg:
                response = self._handle_command(msg)
                self._send_message(conn, response)
        except socket.timeout:
            self.logger.warning("Client connection timed out")
        except Exception as e:
            self.logger.error(f"Error handling client: {e}")
        finally:
            conn.close()

    def start(self) -> None:
        """Start the escalation service."""
        self._cleanup_socket()

        # Create parent directory if needed
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        # Create scheduler
        self.scheduler = EscalationScheduler(self._send_notification)

        # Create server socket
        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(str(self.socket_path))

        # Harden socket permissions - only owner can read/write (0600)
        os.chmod(self.socket_path, 0o600)

        self.server_socket.listen(5)
        self.server_socket.settimeout(1)  # Allow periodic shutdown check

        self.running = True
        self.logger.info(f"Escalation service started on {self.socket_path}")

        # Start PID checker thread
        self._start_pid_checker()

        # Handle signals
        def signal_handler(signum, _frame):
            self.logger.info(f"Received signal {signum}")
            self.running = False

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        # Main accept loop
        try:
            while self.running:
                try:
                    conn, addr = self.server_socket.accept()
                    # Handle each client in a thread to avoid blocking
                    threading.Thread(
                        target=self._handle_client,
                        args=(conn, addr),
                        daemon=True,
                    ).start()
                except socket.timeout:
                    continue
                except OSError:
                    if self.running:
                        raise
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """Clean shutdown of the service."""
        self.logger.info("Shutting down...")

        if self.scheduler:
            self.scheduler.shutdown()

        if self.server_socket:
            self.server_socket.close()

        if self.socket_path.exists():
            self.socket_path.unlink()

        self.logger.info("Shutdown complete")


def main():
    parser = argparse.ArgumentParser(description="Escalation service for Claude Code")
    parser.add_argument(
        "--socket",
        type=Path,
        default=DEFAULT_SOCKET,
        help=f"Unix socket path (default: {DEFAULT_SOCKET})",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=DEFAULT_LOG,
        help=f"Log file path (default: {DEFAULT_LOG})",
    )
    args = parser.parse_args()

    service = EscalationService(args.socket, args.log)
    service.start()


if __name__ == "__main__":
    main()
