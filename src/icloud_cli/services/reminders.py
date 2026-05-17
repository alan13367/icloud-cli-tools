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
