"""Reminders service for icloud-cli.

Provides CRUD operations for iCloud Reminders via pyicloud.
"""

from __future__ import annotations

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
            self._reminders_service.refresh()
            lists = self._reminders_service.lists
        except Exception as e:
            from icloud_cli.output import error
            error(f"Failed to fetch reminders: {e}")
            return []

        result = []
        for rlist in lists.values():
            rlist_title = rlist.get("title", "Untitled List")

            if list_name and rlist_title.lower() != list_name.lower():
                continue

            rlist_guid = rlist.get("guid", "")
            reminders = self._reminders_service.get(rlist_guid) or []

            for reminder in reminders:
                is_completed = reminder.get("completedDate") is not None

                if not show_completed and is_completed:
                    continue

                due_date = ""
                if reminder.get("dueDate"):
                    due_date = _format_due_date(reminder["dueDate"])

                priority_map = {0: "", 1: "High", 5: "Medium", 9: "Low"}
                priority = priority_map.get(reminder.get("priority", 0), "")

                result.append({
                    "id": reminder.get("guid", ""),
                    "title": reminder.get("title", "Untitled"),
                    "list": rlist_title,
                    "due_date": due_date,
                    "priority": priority,
                    "completed": "✓" if is_completed else "",
                    "description": reminder.get("description", ""),
                })

        return result

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
            collection = None
            if list_name:
                self._reminders_service.refresh()
                for rlist in self._reminders_service.lists.values():
                    if rlist.get("title", "").lower() == list_name.lower():
                        collection = rlist.get("guid")
                        break

                if collection is None:
                    from icloud_cli.output import warning
                    warning(f"List '{list_name}' not found, using default list.")

            # Parse due date
            due = None
            if due_date:
                try:
                    due = dateutil_parser.parse(due_date)
                except (ValueError, TypeError):
                    from icloud_cli.output import error
                    error("Invalid date format. Use YYYY-MM-DD or YYYY-MM-DD HH:MM.")
                    return False

            # Build post data
            kwargs = {"title": title}
            if description:
                kwargs["description"] = description
            if collection:
                kwargs["collection"] = collection
            if due:
                kwargs["due_date"] = due

            self._reminders_service.post(**kwargs)
            return True

        except Exception as e:
            from icloud_cli.output import error
            error(f"Failed to create reminder: {e}")
            return False

    def complete_reminder(self, reminder_id: str) -> bool:
        """Mark a reminder as completed.

        Args:
            reminder_id: The reminder GUID.

        Returns:
            True if reminder was marked as completed.
        """
        try:
            # Find the reminder across all lists
            self._reminders_service.refresh()
            for rlist in self._reminders_service.lists.values():
                rlist_guid = rlist.get("guid", "")
                reminders = self._reminders_service.get(rlist_guid) or []

                for reminder in reminders:
                    if reminder.get("guid") == reminder_id:
                        reminder["completedDate"] = datetime.now().strftime(
                            "%Y-%m-%dT%H:%M:%S"
                        )
                        # Use the API to update
                        self._reminders_service.post(
                            title=reminder.get("title", ""),
                            guid=reminder_id,
                            completed_date=datetime.now(),
                        )
                        return True

            from icloud_cli.output import error
            error(f"Reminder '{reminder_id}' not found.")
            return False

        except Exception as e:
            from icloud_cli.output import error
            error(f"Failed to complete reminder: {e}")
            return False

    def delete_reminder(self, reminder_id: str) -> bool:
        """Delete a reminder.

        Args:
            reminder_id: The reminder GUID.

        Returns:
            True if reminder was deleted.
        """
        try:
            self._reminders_service.delete(reminder_id)
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
    return str(due_date)
