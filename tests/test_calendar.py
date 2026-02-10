"""Tests for the calendar service."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from icloud_cli.services.calendar import CalendarService, _parse_date, _format_datetime


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
    """Tests for CalendarService with mocked API."""

    def test_list_events_empty(self, mock_api, mock_config):
        mock_api.calendar.events.return_value = []
        service = CalendarService(mock_api, mock_config)
        events = service.list_events()
        assert events == []

    def test_list_events_returns_formatted_data(self, mock_api, mock_config):
        mock_api.calendar.events.return_value = [
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

    def test_get_event_not_found(self, mock_api, mock_config):
        mock_api.calendar.events.return_value = []
        service = CalendarService(mock_api, mock_config)
        result = service.get_event("nonexistent-id")
        assert result is None

    def test_delete_event_success(self, mock_api, mock_config):
        mock_api.calendar.delete_event.return_value = None
        service = CalendarService(mock_api, mock_config)
        assert service.delete_event("event-123") is True

    def test_delete_event_failure(self, mock_api, mock_config):
        mock_api.calendar.delete_event.side_effect = Exception("Not found")
        service = CalendarService(mock_api, mock_config)
        assert service.delete_event("event-123") is False
