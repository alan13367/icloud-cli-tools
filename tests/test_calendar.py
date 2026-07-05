"""Tests for the calendar service."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from pyicloud.services.calendar import EventObject

from icloud_cli.services.calendar import CalendarService, _format_datetime, _parse_date


class TestDateParsing:
    """Tests for date parsing utilities."""

    def test_parse_today(self):
        result = _parse_date("today")
        assert result is not None
        assert result.date() == datetime.now().date()

    def test_parse_tomorrow(self):
        result = _parse_date("tomorrow")
        assert result is not None
        assert result.date() > datetime.now().date()

    def test_parse_iso_date(self):
        result = _parse_date("2025-06-15")
        assert result is not None
        assert result.year == 2025
        assert result.month == 6
        assert result.day == 15

    def test_parse_iso_datetime(self):
        result = _parse_date("2025-06-15 14:30")
        assert result is not None
        assert result.hour == 14
        assert result.minute == 30

    def test_parse_none(self):
        default = datetime(2025, 1, 1)
        result = _parse_date(None, default=default)
        assert result == default

    def test_parse_invalid(self):
        result = _parse_date("not a date", default=None)
        assert result is None


class TestFormatDatetime:
    """Tests for datetime formatting."""

    def test_format_datetime_object(self):
        dt = datetime(2025, 6, 15, 14, 30)
        assert _format_datetime(dt) == "2025-06-15 14:30"

    def test_format_string(self):
        result = _format_datetime("2025-06-15T14:30:00")
        assert "2025-06-15" in result

    def test_format_none(self):
        assert _format_datetime(None) == ""


class TestCalendarService:
    """Tests for CalendarService with the pyicloud >=2.5 calendar API mocked."""

    def test_list_events_empty(self, mock_api, mock_config):
        mock_api.calendar.get_calendars.return_value = []
        mock_api.calendar.get_events.return_value = []
        service = CalendarService(mock_api, mock_config)
        events = service.list_events()
        assert events == []

    def test_list_events_returns_formatted_data(self, mock_api, mock_config):
        mock_api.calendar.get_calendars.return_value = [
            {"guid": "cal-1", "title": "Personal"}
        ]
        mock_api.calendar.get_events.return_value = [
            {
                "guid": "event-123",
                "title": "Team Meeting",
                "startDate": "2025-06-15T10:00:00",
                "endDate": "2025-06-15T11:00:00",
                "pGuid": "cal-1",
                "location": "Room A",
                "allDay": False,
            }
        ]
        service = CalendarService(mock_api, mock_config)
        events = service.list_events()

        assert len(events) == 1
        assert events[0]["title"] == "Team Meeting"
        assert events[0]["id"] == "event-123"
        assert events[0]["location"] == "Room A"
        # pGuid is resolved to the human-readable calendar title.
        assert events[0]["calendar"] == "Personal"

    def test_get_event_not_found(self, mock_api, mock_config):
        mock_api.calendar.get_events.return_value = []
        service = CalendarService(mock_api, mock_config)
        result = service.get_event("nonexistent-id")
        assert result is None

    def test_add_event_builds_event_object(self, mock_api, mock_config):
        mock_api.calendar.get_calendars.return_value = [
            {"guid": "cal-1", "title": "Personal"}
        ]
        service = CalendarService(mock_api, mock_config)

        ok = service.add_event(
            title="Lunch",
            start="2025-06-15 12:00",
            end="2025-06-15 13:00",
            calendar_name="Personal",
        )

        assert ok is True
        mock_api.calendar.add_event.assert_called_once()
        event_obj = mock_api.calendar.add_event.call_args.args[0]
        assert isinstance(event_obj, EventObject)
        assert event_obj.pguid == "cal-1"
        assert event_obj.title == "Lunch"

    def test_delete_event_success(self, mock_api, mock_config):
        mock_api.calendar.get_events.return_value = [
            {"guid": "event-123", "pGuid": "cal-1"}
        ]
        detail = MagicMock()
        mock_api.calendar.get_event_detail.return_value = detail
        service = CalendarService(mock_api, mock_config)

        assert service.delete_event("event-123") is True
        mock_api.calendar.get_event_detail.assert_called_once_with(
            "cal-1", "event-123", as_obj=True
        )
        mock_api.calendar.remove_event.assert_called_once_with(detail)

    def test_delete_event_not_found(self, mock_api, mock_config):
        mock_api.calendar.get_events.return_value = [
            {"guid": "other-event", "pGuid": "cal-1"}
        ]
        service = CalendarService(mock_api, mock_config)

        assert service.delete_event("event-123") is False
        mock_api.calendar.remove_event.assert_not_called()

    def test_delete_event_failure(self, mock_api, mock_config):
        mock_api.calendar.get_events.return_value = [
            {"guid": "event-123", "pGuid": "cal-1"}
        ]
        mock_api.calendar.remove_event.side_effect = Exception("boom")
        service = CalendarService(mock_api, mock_config)
        assert service.delete_event("event-123") is False
