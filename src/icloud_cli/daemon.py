"""Background sync daemon for icloud-cli.

Provides one-shot sync and a background daemon that periodically
caches iCloud data to local JSON files.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from icloud_cli.auth import AuthManager
from icloud_cli.config import Config
from icloud_cli.output import error, info, success, warning


PID_FILE_NAME = "icloud-cli-daemon.pid"


def sync_all(auth: AuthManager, config: Config) -> None:
    """Run a one-shot sync of all services to local cache."""
    cache_dir = Path(config.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    info("Syncing iCloud data...")

    # Sync Calendar
    try:
        from icloud_cli.services.calendar import CalendarService

        cal_service = CalendarService(auth.api, config)
        now = datetime.now()
        events = cal_service.list_events(
            from_date=now.strftime("%Y-%m-%d"),
            to_date=(now + timedelta(days=30)).strftime("%Y-%m-%d"),
        )
        _save_cache(cache_dir / "calendar.json", events)
        success(f"Calendar: {len(events)} events synced.")
    except Exception as e:
        warning(f"Calendar sync failed: {e}")

    # Sync Reminders
    try:
        from icloud_cli.services.reminders import RemindersService

        rem_service = RemindersService(auth.api, config)
        reminders = rem_service.list_reminders(show_completed=True)
        _save_cache(cache_dir / "reminders.json", reminders)
        success(f"Reminders: {len(reminders)} items synced.")
    except Exception as e:
        warning(f"Reminders sync failed: {e}")

    # Sync Notes
    try:
        credentials = auth.get_imap_credentials()
        if credentials:
            from icloud_cli.services.notes import NotesService

            notes_service = NotesService(*credentials)
            notes = notes_service.list_notes()
            _save_cache(cache_dir / "notes.json", notes)
            success(f"Notes: {len(notes)} notes synced.")
        else:
            info("Notes: Skipped (IMAP not configured).")
    except Exception as e:
        warning(f"Notes sync failed: {e}")

    # Sync Find My
    try:
        from icloud_cli.services.findmy import FindMyService

        findmy_service = FindMyService(auth.api)
        devices = findmy_service.list_devices()
        _save_cache(cache_dir / "devices.json", devices)
        success(f"Find My: {len(devices)} devices synced.")
    except Exception as e:
        warning(f"Find My sync failed: {e}")

    # Write sync timestamp
    _save_cache(cache_dir / "last_sync.json", {
        "timestamp": datetime.now().isoformat(),
        "status": "ok",
    })

    success("Sync complete!")


def start_daemon(auth: AuthManager, config: Config) -> None:
    """Start the background sync daemon."""
    pid_file = Path(config.cache_dir) / PID_FILE_NAME

    # Check if already running
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)  # Check if process exists
            error(f"Daemon already running (PID {pid}).")
            return
        except (ProcessLookupError, ValueError):
            # Stale PID file
            pid_file.unlink(missing_ok=True)

    interval = config.sync_interval_minutes
    info(f"Starting daemon (sync every {interval} minutes)...")
    info("Press Ctrl+C to stop, or use 'icloud-cli daemon stop'.")

    # Write PID file
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()))

    # Handle graceful shutdown
    def _shutdown(signum, frame):
        info("\nDaemon stopping...")
        pid_file.unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        while True:
            try:
                sync_all(auth, config)
            except Exception as e:
                warning(f"Sync cycle failed: {e}")

            info(f"Next sync in {interval} minutes...")
            time.sleep(interval * 60)
    finally:
        pid_file.unlink(missing_ok=True)


def stop_daemon(config: Config) -> None:
    """Stop the background sync daemon."""
    pid_file = Path(config.cache_dir) / PID_FILE_NAME

    if not pid_file.exists():
        error("Daemon is not running.")
        return

    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        success(f"Daemon stopped (PID {pid}).")
        pid_file.unlink(missing_ok=True)
    except ProcessLookupError:
        warning("Daemon process not found (stale PID file).")
        pid_file.unlink(missing_ok=True)
    except ValueError:
        error("Invalid PID file.")
        pid_file.unlink(missing_ok=True)


def get_daemon_status(config: Config) -> dict[str, Any]:
    """Get daemon status information."""
    pid_file = Path(config.cache_dir) / PID_FILE_NAME
    cache_dir = Path(config.cache_dir)
    last_sync_file = cache_dir / "last_sync.json"

    # Check if daemon is running
    running = False
    pid = None
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            running = True
        except (ProcessLookupError, ValueError):
            pass

    # Last sync info
    last_sync = "Never"
    if last_sync_file.exists():
        try:
            data = json.loads(last_sync_file.read_text())
            last_sync = data.get("timestamp", "Unknown")
        except (json.JSONDecodeError, KeyError):
            pass

    return {
        "running": "Yes" if running else "No",
        "pid": str(pid) if pid and running else "N/A",
        "sync_interval": f"{config.sync_interval_minutes} minutes",
        "last_sync": last_sync,
        "cache_dir": config.cache_dir,
    }


def _save_cache(path: Path, data: Any) -> None:
    """Save data to a JSON cache file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
