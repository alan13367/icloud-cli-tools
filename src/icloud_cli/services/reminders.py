"""Reminders service for icloud-cli.

Provides CRUD operations for iCloud Reminders via pyicloud.

Supports cursor-based incremental sync: the first call does a full CloudKit sync.
Subsequent calls use iter_changes(since=cursor) to fetch only changes.
State is persisted under config.cache_dir/reminders/.
"""

from __future__ import annotations

import json
import time
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any

from dateutil import parser as dateutil_parser
from pyicloud import PyiCloudService

from icloud_cli.config import Config


class RemindersService:
    """Manages iCloud Reminders."""

    def __init__(self, api: PyiCloudService, config: Config):
        self.api = api
        self.config = config
        self._reminders_service = api.reminders

        # Cursor-based incremental sync state
        self._cache_dir = Path(config.cache_dir) / "reminders"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._state_file = self._cache_dir / "state.json"

    def list_reminders(
        self,
        list_name: str | None = None,
        show_completed: bool = False,
    ) -> list[dict[str, Any]]:
        """List reminders with cursor-based incremental sync.

        First call triggers a full CloudKit sync (~5 min for 200 reminders).
        Subsequent calls fetch only changes since the last cursor (~1s).

        Args:
            list_name: Filter to specific reminder list.
            show_completed: Include completed reminders.

        Returns:
            List of reminder dictionaries.
        """

        state = self._load_sync_state()

        try:
            rlists = list(self._reminders_service.lists())
            list_map = {lst.id: lst.title for lst in rlists}

            # Capture an upper bound before reading any reminder records. If a
            # change arrives while the read is in progress, keeping this older
            # cursor makes the next invocation replay that change safely.
            next_cursor = self._reminders_service.sync_cursor()

            if state is None:
                data_map = self._full_reminder_snapshot(rlists, list_map)
            else:
                cursor, cached_data = state
                data_map = {entry["id"]: entry for entry in cached_data}

                # List changes are not emitted by iter_changes(), so refresh
                # cached display names from the lightweight list snapshot.
                for entry in data_map.values():
                    entry_list_id = entry.get("list_id")
                    if entry_list_id:
                        entry["list"] = list_map.get(entry_list_id, entry_list_id)

                try:
                    for change in self._reminders_service.iter_changes(since=cursor):
                        reminder_id = change.reminder_id
                        reminder = change.reminder
                        if change.type == "deleted" or not reminder or reminder.deleted:
                            data_map.pop(reminder_id, None)
                            continue

                        list_title = list_map.get(reminder.list_id, reminder.list_id)
                        data_map[reminder_id] = self._reminder_to_entry(
                            reminder, list_title
                        )
                except Exception:
                    # An expired or account-mismatched cursor requires a fresh
                    # snapshot. next_cursor was captured before this read, so
                    # later changes will still be replayed on the next call.
                    data_map = self._full_reminder_snapshot(rlists, list_map)
        except Exception as e:
            from icloud_cli.output import error
            error(f"Failed to fetch reminders: {e}")
            return []

        cached_data = list(data_map.values())
        # The old state remains intact on failure because replacement is
        # atomic, so the next invocation replays from its older cursor.
        with suppress(OSError):
            self._write_sync_state(next_cursor, cached_data)

        result = []
        for cached_entry in cached_data:
            entry = {key: value for key, value in cached_entry.items() if key != "list_id"}
            if list_name and entry["list"].lower() != list_name.lower():
                continue
            if not show_completed and entry["completed"]:
                continue
            result.append(entry)
        return result

    def _load_sync_state(self) -> tuple[str, list[dict[str, Any]]] | None:
        """Load a complete cursor/data generation, or request a full sync."""
        if not self._state_file.exists():
            return None
        try:
            state = json.loads(self._state_file.read_text())
            if state.get("version") != 1 or state.get("account") != self.config.apple_id:
                return None
            cursor = state["cursor"]
            entries = state["entries"]
            entries_are_valid = isinstance(entries, list) and all(
                isinstance(entry, dict)
                and isinstance(entry.get("id"), str)
                and isinstance(entry.get("list_id"), str)
                for entry in entries
            )
            if not isinstance(cursor, str) or not entries_are_valid:
                return None
            return cursor, entries
        except (json.JSONDecodeError, KeyError, OSError, TypeError, AttributeError):
            return None

    def _write_sync_state(self, cursor: str, entries: list[dict[str, Any]]) -> None:
        """Atomically persist cursor and entries as one cache generation."""
        state = {
            "version": 1,
            "account": self.config.apple_id,
            "cursor": cursor,
            "entries": entries,
        }
        temp_file = self._state_file.with_name(
            f".{self._state_file.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            temp_file.write_text(json.dumps(state, indent=2))
            temp_file.replace(self._state_file)
        finally:
            if temp_file.exists():
                temp_file.unlink()

    def _full_reminder_snapshot(
        self, rlists: list[Any], list_map: dict[str, str]
    ) -> dict[str, dict[str, Any]]:
        """Fetch a complete deduplicated reminder snapshot."""
        data_map: dict[str, dict[str, Any]] = {}
        for rlist in rlists:
            for reminder in self._reminders_service.reminders(list_id=rlist.id):
                if getattr(reminder, "deleted", False):
                    continue
                data_map[reminder.id] = self._reminder_to_entry(
                    reminder, list_map.get(reminder.list_id, reminder.list_id)
                )
        return data_map

    def list_reminder_lists(self) -> list[dict[str, Any]]:
        """List reminder lists."""
        try:
            lists = list(self._reminders_service.lists())
        except Exception as e:
            from icloud_cli.output import error
            error(f"Failed to fetch reminder lists: {e}")
            return []

        return [
            {
                "id": rlist.id,
                "title": rlist.title,
                "count": getattr(rlist, "count", 0),
                "color": getattr(rlist, "color", "") or "",
            }
            for rlist in lists
        ]

    def create_list(self, name: str, color: str = "blue") -> str | None:
        """Create a new iCloud Reminders list and return its record ID."""
        if not name.strip():
            from icloud_cli.output import error
            error("List name cannot be empty.")
            return None

        try:
            helpers = _load_reminders_cloudkit_helpers()
            list_id = f"List/{str(uuid.uuid4()).upper()}"
            fields = {
                "Name": {"type": "STRING", "value": name, "isEncrypted": True},
                "Color": {
                    "type": "STRING",
                    "value": _reminders_color_payload(color),
                },
                "Count": {"type": "INT64", "value": 0},
                "Deleted": {"type": "INT64", "value": 0},
                "Imported": {"type": "INT64", "value": 0},
                "IsGroup": {"type": "INT64", "value": 0},
                "IsLinkedToAccount": {"type": "INT64", "value": 1},
                "ReminderIDs": {"type": "STRING", "value": "[]"},
                "SortingStyle": {"type": "STRING", "value": "manual"},
                "ResolutionTokenMap": {
                    "type": "STRING",
                    "value": helpers.generate_resolution_token_map([
                        "name",
                        "color",
                        "deleted",
                        "imported",
                        "isGroup",
                        "isLinkedToAccount",
                        "reminderIDsMergeableOrdering",
                        "sortingStyle",
                        "minimumSupportedVersion",
                    ]),
                },
            }
            self._modify_reminders_record(
                helpers=helpers,
                operation_type="create",
                record_name=list_id,
                record_type="List",
                fields=fields,
            )
            return list_id
        except Exception as e:
            from icloud_cli.output import error
            error(f"Failed to create reminder list: {e}")
            return None

    def create_section(self, list_name: str, section_name: str) -> str | None:
        """Create a section inside an existing iCloud Reminders list."""
        if not section_name.strip():
            from icloud_cli.output import error
            error("Section name cannot be empty.")
            return None

        try:
            target_list_id = self._find_list_id(list_name)
            if target_list_id is None:
                from icloud_cli.output import error
                error(f"List '{list_name}' not found.")
                return None

            helpers = _load_reminders_cloudkit_helpers()
            section_id = f"ListSection/{str(uuid.uuid4()).upper()}"
            now_ms = int(time.time() * 1000)
            fields = {
                "DisplayName": {
                    "type": "STRING",
                    "value": section_name,
                    "isEncrypted": True,
                },
                "CreationDate": {"type": "TIMESTAMP", "value": now_ms},
                "Deleted": {"type": "INT64", "value": 0},
                "Imported": {"type": "INT64", "value": 0},
                "List": {
                    "type": "REFERENCE",
                    "value": {"recordName": target_list_id, "action": "VALIDATE"},
                },
                "ResolutionTokenMap": {
                    "type": "STRING",
                    "value": helpers.generate_resolution_token_map([
                        "displayName",
                        "creationDate",
                        "deleted",
                        "imported",
                        "list",
                        "minimumSupportedVersion",
                    ]),
                },
            }
            self._modify_reminders_record(
                helpers=helpers,
                operation_type="create",
                record_name=section_id,
                record_type="ListSection",
                fields=fields,
                parent_record_name=target_list_id,
            )
            return section_id
        except Exception as e:
            from icloud_cli.output import error
            error(f"Failed to create reminder section: {e}")
            return None

    def add_reminder(
        self,
        title: str,
        due_date: str | None = None,
        list_name: str | None = None,
        description: str | None = None,
    ) -> bool:
        """Add a new reminder.

        Args:
            title: Reminder title.
            due_date: Due date string (YYYY-MM-DD or YYYY-MM-DD HH:MM).
            list_name: Target reminder list name.
            description: Reminder description.

        Returns:
            True if reminder was created successfully.
        """
        try:
            # Find the target collection (list)
            target_list_id: str | None = None
            if list_name:
                for rlist in self._reminders_service.lists():
                    if rlist.title.lower() == list_name.lower():
                        target_list_id = rlist.id
                        break

                if target_list_id is None:
                    from icloud_cli.output import warning
                    warning(f"List '{list_name}' not found, using default list.")
                    for rlist in self._reminders_service.lists():
                        target_list_id = rlist.id
                        break
            else:
                # Use the first available list as default
                for rlist in self._reminders_service.lists():
                    target_list_id = rlist.id
                    break

            if target_list_id is None:
                from icloud_cli.output import error
                error("No reminder lists found.")
                return False

            # Parse due date. When the user gives a bare date with no time
            # (e.g. "2025-06-15"), create an all-day reminder so it shows the
            # date without a "12:00 AM" time, matching the Reminders app.
            due: datetime | None = None
            all_day = False
            if due_date:
                try:
                    due, all_day = _parse_due_date(due_date)
                except (ValueError, TypeError, OverflowError):
                    from icloud_cli.output import error
                    error("Invalid date format. Use YYYY-MM-DD or YYYY-MM-DD HH:MM.")
                    return False

            self._reminders_service.create(
                list_id=target_list_id,
                title=title,
                desc=description or "",
                due_date=due,
                all_day=all_day,
                priority=0,
            )
            return True

        except Exception as e:
            from icloud_cli.output import error
            error(f"Failed to create reminder: {e}")
            return False

    @staticmethod
    def _reminder_to_entry(r, list_title: str) -> dict[str, Any]:
        """Convert a pyicloud Reminder model to the icloud-cli dict format."""
        priority_map = {0: "", 1: "High", 5: "Medium", 9: "Low"}
        due_date = ""
        if r.due_date:
            due_date = _format_due_date(
                r.due_date,
                date_only=bool(getattr(r, "all_day", False)),
            )
        return {
            "id": r.id,
            "list_id": r.list_id,
            "title": r.title,
            "list": list_title,
            "due_date": due_date,
            "priority": priority_map.get(r.priority, ""),
            "completed": "✓" if r.completed else "",
            "description": r.desc,
        }

    def _find_list_id(self, list_name: str) -> str | None:
        for rlist in self._reminders_service.lists():
            if rlist.title.lower() == list_name.lower() or rlist.id == list_name:
                return rlist.id
        return None

    def _modify_reminders_record(
        self,
        *,
        helpers: _RemindersCloudKitHelpers,
        operation_type: str,
        record_name: str,
        record_type: str,
        fields: dict[str, Any],
        parent_record_name: str | None = None,
    ) -> None:
        parent = None
        if parent_record_name:
            parent = helpers.write_parent(recordName=parent_record_name)

        operation = helpers.modify_operation(
            operationType=operation_type,
            record=helpers.write_record(
                recordName=record_name,
                recordType=record_type,
                fields=fields,
                parent=parent,
            ),
        )

        raw = self._reminders_service._raw
        response = raw.modify(operations=[operation], zone_id=helpers.zone_req)
        records = getattr(response, "records", [])
        for record in records:
            if getattr(record, "serverErrorCode", None):
                reason = getattr(record, "reason", "") or record.serverErrorCode
                raise RuntimeError(reason)

    def complete_reminder(self, reminder_id: str) -> bool:
        """Mark a reminder as completed.

        Args:
            reminder_id: The reminder ID.

        Returns:
            True if reminder was marked as completed.
        """
        try:
            reminder = self._reminders_service.get(reminder_id)
            reminder.completed = True
            reminder.completed_date = datetime.now()
            self._reminders_service.update(reminder)
            return True
        except Exception as e:
            from icloud_cli.output import error
            error(f"Failed to complete reminder: {e}")
            return False

    def delete_reminder(self, reminder_id: str) -> bool:
        """Delete a reminder.

        Args:
            reminder_id: The reminder ID.

        Returns:
            True if reminder was deleted.
        """
        try:
            reminder = self._reminders_service.get(reminder_id)
            self._reminders_service.delete(reminder)
            return True
        except Exception as e:
            from icloud_cli.output import error
            error(f"Failed to delete reminder: {e}")
            return False


def _parse_due_date(due_date: str) -> tuple[datetime, bool]:
    """Parse a due-date string, detecting whether a time was supplied.

    Returns a ``(datetime, all_day)`` tuple. When the input carries no time
    component the reminder is treated as all-day and anchored to noon so the
    stored calendar date stays stable across time zones (pyicloud persists a
    naive datetime as UTC).

    Date fields the user omits fall back to today, matching ``dateutil``'s
    default. The two parse defaults share the same date and differ only in
    their time fields, so a time the user actually typed resolves identically
    against both while a time left to the default does not -- that is what
    distinguishes a bare date from a timed one.
    """
    today = datetime.now()
    default_a = today.replace(hour=0, minute=0, second=0, microsecond=0)
    default_b = today.replace(hour=23, minute=59, second=58, microsecond=0)
    parsed_a = dateutil_parser.parse(due_date, default=default_a)
    parsed_b = dateutil_parser.parse(due_date, default=default_b)
    has_time = (
        parsed_a.hour == parsed_b.hour
        or parsed_a.minute == parsed_b.minute
        or parsed_a.second == parsed_b.second
    )
    if has_time:
        return parsed_a, False
    anchored = parsed_a.replace(hour=12, minute=0, second=0, microsecond=0)
    return anchored, True


def _format_due_date(due_date: Any, date_only: bool = False) -> str:
    """Format a due date from the API response.

    When ``date_only`` is True (all-day reminders), the time component is
    omitted so the reminder shows just its date.
    """
    fmt = "%Y-%m-%d" if date_only else "%Y-%m-%d %H:%M"
    if isinstance(due_date, str):
        try:
            dt = dateutil_parser.parse(due_date)
            return dt.strftime(fmt)
        except (ValueError, TypeError):
            return due_date
    if isinstance(due_date, list) and len(due_date) >= 5:
        # iCloud format: [year, month, day, hour, minute]
        try:
            date_part = f"{due_date[0]:04d}-{due_date[1]:02d}-{due_date[2]:02d}"
            if date_only:
                return date_part
            time_part = f"{due_date[3]:02d}:{due_date[4]:02d}"
            return f"{date_part} {time_part}"
        except (IndexError, TypeError):
            return str(due_date)
    if isinstance(due_date, (int, float)):
        try:
            return datetime.fromtimestamp(due_date / 1000).strftime(fmt)
        except (ValueError, OSError):
            return str(due_date)
    if isinstance(due_date, datetime):
        return due_date.strftime(fmt)
    return str(due_date)


class _RemindersCloudKitHelpers:
    """Small import container for pyicloud's internal CloudKit write models."""

    def __init__(self):
        from pyicloud.common.cloudkit import CKModifyOperation, CKWriteParent, CKWriteRecord
        from pyicloud.services.reminders._constants import _REMINDERS_ZONE_REQ
        from pyicloud.services.reminders._protocol import _generate_resolution_token_map

        self.modify_operation = CKModifyOperation
        self.write_parent = CKWriteParent
        self.write_record = CKWriteRecord
        self.zone_req = _REMINDERS_ZONE_REQ
        self.generate_resolution_token_map = _generate_resolution_token_map


def _load_reminders_cloudkit_helpers() -> _RemindersCloudKitHelpers:
    return _RemindersCloudKitHelpers()


def _reminders_color_payload(color: str) -> str:
    """Return the JSON string Apple stores in Reminders List.Color."""
    palette = {
        "blue": {"red": 0.0, "green": 0.478, "blue": 1.0, "alpha": 1.0},
        "green": {"red": 0.204, "green": 0.78, "blue": 0.349, "alpha": 1.0},
        "red": {"red": 1.0, "green": 0.231, "blue": 0.188, "alpha": 1.0},
        "orange": {"red": 1.0, "green": 0.584, "blue": 0.0, "alpha": 1.0},
        "yellow": {"red": 1.0, "green": 0.8, "blue": 0.0, "alpha": 1.0},
        "purple": {"red": 0.686, "green": 0.322, "blue": 0.871, "alpha": 1.0},
        "gray": {"red": 0.557, "green": 0.557, "blue": 0.576, "alpha": 1.0},
    }
    return json.dumps(palette.get(color.lower(), palette["blue"]), separators=(",", ":"))
