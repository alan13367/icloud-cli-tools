"""Calendar service for icloud-cli.

Provides CRUD operations for iCloud Calendar events via pyicloud.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from dateutil import parser as dateutil_parser
from pyicloud import PyiCloudService
from pyicloud.services.calendar import EventObject

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
    if isinstance(dt, list) and len(dt) >= 4:
        # iCloud format: [packed, year, month, day, hour, minute, tz_offset_minutes]
        try:
            parsed = datetime(
                dt[1],
                dt[2],
                dt[3],
                dt[4] if len(dt) > 4 else 0,
                dt[5] if len(dt) > 5 else 0,
            )
            return parsed.strftime("%Y-%m-%d %H:%M")
        except (IndexError, TypeError, ValueError):
            return str(dt)
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
            cal_name = {
                cal.get("guid"): cal.get("title", "")
                for cal in self.api.calendar.get_calendars()
            }
            events = self.api.calendar.get_events(from_dt=start, to_dt=end)
        except Exception as e:
            from icloud_cli.output import error
            error(f"Failed to fetch events: {e}")
            return []

        result = []
        for event in events:
            pguid = event.get("pGuid", "")
            result.append({
                "id": event.get("guid", ""),
                "title": event.get("title", "Untitled"),
                "start": _format_datetime(
                    event.get("startDate") or event.get("localStartDate")
                ),
                "end": _format_datetime(
                    event.get("endDate") or event.get("localEndDate")
                ),
                "calendar": cal_name.get(pguid, pguid),
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
            events = self.api.calendar.get_events(from_dt=start, to_dt=end)
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
            calendars = self.api.calendar.get_calendars()
            cal_guid = None
            if calendar_name:
                for cal in calendars:
                    if cal.get("title", "").lower() == calendar_name.lower():
                        cal_guid = cal.get("guid")
                        break
            if not cal_guid and calendars:
                cal_guid = calendars[0].get("guid")
            if not cal_guid:
                from icloud_cli.output import error
                error("No calendars found.")
                return False

            event_obj = EventObject(
                pguid=cal_guid,
                title=title,
                start_date=start_dt,
                end_date=end_dt,
                location=location or "",
            )
            self.api.calendar.add_event(event_obj)
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
            now = datetime.now()
            events = self.api.calendar.get_events(
                from_dt=now - timedelta(days=365),
                to_dt=now + timedelta(days=365),
            )
            pguid = None
            for ev in events:
                if ev.get("guid") == event_id:
                    pguid = ev.get("pGuid")
                    break
            if not pguid:
                from icloud_cli.output import error
                error(f"Event '{event_id}' not found.")
                return False

            event_obj = self.api.calendar.get_event_detail(pguid, event_id, as_obj=True)
            self.api.calendar.remove_event(event_obj)
            return True
        except Exception as e:
            from icloud_cli.output import error
            error(f"Failed to delete event: {e}")
            return False
