"""Reminders service for icloud-cli.

Provides CRUD operations for iCloud Reminders via pyicloud.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
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

    def list_reminders(
        self,
        list_name: str | None = None,
        show_completed: bool = False,
    ) -> list[dict[str, Any]]:
        """List reminders, optionally filtered by list.

        Args:
            list_name: Filter to specific reminder list.
            show_completed: Include completed reminders.

        Returns:
            List of reminder dictionaries.
        """
        try:
            lists = list(self._reminders_service.lists())
        except Exception as e:
            from icloud_cli.output import error
            error(f"Failed to fetch reminders: {e}")
            return []

        result = []
        for rlist in lists:
            rlist_title = rlist.title
            rlist_id = rlist.id

            if list_name and rlist_title.lower() != list_name.lower():
                continue

            reminders = list(self._reminders_service.reminders(list_id=rlist_id))

            for reminder in reminders:
                if not show_completed and reminder.completed:
                    continue

                due_date = ""
                if reminder.due_date:
                    due_date = _format_due_date(reminder.due_date)

                priority_map = {0: "", 1: "High", 5: "Medium", 9: "Low"}
                priority = priority_map.get(reminder.priority, "")

                result.append({
                    "id": reminder.id,
                    "title": reminder.title,
                    "list": rlist_title,
                    "due_date": due_date,
                    "priority": priority,
                    "completed": "✓" if reminder.completed else "",
                    "description": reminder.desc,
                })

        return result

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

            # Parse due date
            due: datetime | None = None
            if due_date:
                try:
                    due = dateutil_parser.parse(due_date)
                except (ValueError, TypeError):
                    from icloud_cli.output import error
                    error("Invalid date format. Use YYYY-MM-DD or YYYY-MM-DD HH:MM.")
                    return False

            self._reminders_service.create(
                list_id=target_list_id,
                title=title,
                desc=description or "",
                due_date=due,
                priority=0,
            )
            return True

        except Exception as e:
            from icloud_cli.output import error
            error(f"Failed to create reminder: {e}")
            return False

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


def _format_due_date(due_date: Any) -> str:
    """Format a due date from the API response."""
    if isinstance(due_date, str):
        try:
            dt = dateutil_parser.parse(due_date)
            return dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            return due_date
    if isinstance(due_date, list) and len(due_date) >= 4:
        # iCloud format: [year, month, day, hour, minute]
        try:
            date_part = f"{due_date[0]:04d}-{due_date[1]:02d}-{due_date[2]:02d}"
            time_part = f"{due_date[3]:02d}:{due_date[4]:02d}"
            return f"{date_part} {time_part}"
        except (IndexError, TypeError):
            return str(due_date)
    if isinstance(due_date, (int, float)):
        try:
            return datetime.fromtimestamp(due_date / 1000).strftime("%Y-%m-%d %H:%M")
        except (ValueError, OSError):
            return str(due_date)
    if isinstance(due_date, datetime):
        return due_date.strftime("%Y-%m-%d %H:%M")
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
