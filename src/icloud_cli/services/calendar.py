"""Calendar service for icloud-cli.

Provides CRUD operations for iCloud Calendar events via pyicloud.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from dateutil import parser as dateutil_parser
from pyicloud import PyiCloudService

from icloud_cli.config import Config


def _parse_date(date_str: str | None, default: datetime | None = None) -> datetime | None:
    """Parse a date string with natural language support."""
    if date_str is None:
        return default

    # Natural language shortcuts
    now = datetime.now()
    shortcuts = {
        "today": now.replace(hour=0, minute=0, second=0, microsecond=0),
        "tomorrow": (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
        "yesterday": (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
    }

    if date_str.lower() in shortcuts:
        return shortcuts[date_str.lower()]

    try:
        return dateutil_parser.parse(date_str)
    except (ValueError, TypeError):
        return default


def _format_datetime(dt: Any) -> str:
    """Format a datetime-like object for display."""
    if dt is None:
        return ""
    if isinstance(dt, str):
        try:
            dt = dateutil_parser.parse(dt)
        except (ValueError, TypeError):
            return dt
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M")
    if isinstance(dt, (int, float)):
        # Unix timestamp in milliseconds
        try:
            return datetime.fromtimestamp(dt / 1000).strftime("%Y-%m-%d %H:%M")
        except (ValueError, OSError):
            return str(dt)
    return str(dt)


class CalendarService:
    """Manages iCloud Calendar events."""

    def __init__(self, api: PyiCloudService, config: Config):
        self.api = api
        self.config = config

    def list_events(
        self, from_date: str | None = None, to_date: str | None = None
    ) -> list[dict[str, Any]]:
        """List calendar events within a date range.

        Args:
            from_date: Start date string (default: today).
            to_date: End date string (default: 7 days from start).

        Returns:
            List of event dictionaries.
        """
        now = datetime.now()
        start = _parse_date(from_date, default=now.replace(hour=0, minute=0, second=0))
        end = _parse_date(to_date, default=start + timedelta(days=7))

        try:
            events = self.api.calendar.events(from_dt=start, to_dt=end)
        except Exception as e:
            from icloud_cli.output import error
            error(f"Failed to fetch events: {e}")
            return []

        result = []
        for event in events:
            result.append({
                "id": event.get("guid", ""),
                "title": event.get("title", "Untitled"),
                "start": _format_datetime(
                    event.get("startDate") or event.get("localStartDate")
                ),
                "end": _format_datetime(
                    event.get("endDate") or event.get("localEndDate")
                ),
                "calendar": event.get("pGuid", ""),
                "location": event.get("location", ""),
                "all_day": event.get("allDay", False),
            })

        # Sort by start date
        result.sort(key=lambda x: x.get("start", ""))
        return result

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        """Get detailed info for a specific event.

        Args:
            event_id: The event GUID.

        Returns:
            Event dictionary or None if not found.
        """
        now = datetime.now()
        start = now - timedelta(days=365)
        end = now + timedelta(days=365)

        try:
            events = self.api.calendar.events(from_dt=start, to_dt=end)
        except Exception:
            return None

        for event in events:
            if event.get("guid") == event_id:
                return {
                    "id": event.get("guid", ""),
                    "title": event.get("title", "Untitled"),
                    "start": _format_datetime(
                        event.get("startDate") or event.get("localStartDate")
                    ),
                    "end": _format_datetime(
                        event.get("endDate") or event.get("localEndDate")
                    ),
                    "calendar": event.get("pGuid", ""),
                    "location": event.get("location", ""),
                    "description": event.get("description", ""),
                    "all_day": event.get("allDay", False),
                    "url": event.get("url", ""),
                }

        return None

    def add_event(
        self,
        title: str,
        start: str,
        end: str,
        calendar_name: str | None = None,
        location: str | None = None,
        description: str | None = None,
    ) -> bool:
        """Add a new calendar event.

        Args:
            title: Event title.
            start: Start datetime string.
            end: End datetime string.
            calendar_name: Target calendar name (uses default if None).
            location: Event location.
            description: Event description/notes.

        Returns:
            True if event was created successfully.
        """
        start_dt = _parse_date(start)
        end_dt = _parse_date(end)

        if not start_dt or not end_dt:
            from icloud_cli.output import error
            error("Invalid date format. Use YYYY-MM-DD HH:MM or natural language.")
            return False

        try:
            # Build event payload
            event_data = {
                "title": title,
                "startDate": _datetime_to_icloud(start_dt),
                "endDate": _datetime_to_icloud(end_dt),
            }

            if location:
                event_data["location"] = location
            if description:
                event_data["description"] = description

            self.api.calendar.create_event(**event_data)
            return True
        except Exception as e:
            from icloud_cli.output import error
            error(f"Failed to create event: {e}")
            return False

    def delete_event(self, event_id: str) -> bool:
        """Delete a calendar event by ID.

        Args:
            event_id: The event GUID.

        Returns:
            True if event was deleted successfully.
        """
        try:
            self.api.calendar.delete_event(event_id)
            return True
        except Exception as e:
            from icloud_cli.output import error
            error(f"Failed to delete event: {e}")
            return False


def _datetime_to_icloud(dt: datetime) -> list[int]:
    """Convert a datetime to iCloud's date format [year, month, day, hour, minute]."""
    return [dt.year, dt.month, dt.day, dt.hour, dt.minute]
