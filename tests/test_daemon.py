"""Tests for the sync daemon."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from icloud_cli.daemon import sync_all


@pytest.fixture
def calendar_service():
    """Patch out every service sync_all touches; return the CalendarService mock."""
    with patch("icloud_cli.services.calendar.CalendarService") as cal_cls, \
         patch("icloud_cli.services.reminders.RemindersService") as rem_cls, \
         patch("icloud_cli.services.findmy.FindMyService") as findmy_cls:
        cal_cls.return_value.list_events.return_value = [{"title": "Dentist"}]
        rem_cls.return_value.list_reminders.return_value = []
        findmy_cls.return_value.list_devices.return_value = []
        yield cal_cls.return_value


def _window_days(service) -> int:
    kwargs = service.list_events.call_args.kwargs
    start = date.fromisoformat(kwargs["from_date"])
    end = date.fromisoformat(kwargs["to_date"])
    return (end - start).days


class TestSyncCalendarWindow:
    def test_defaults_to_30_days(self, mock_auth, mock_config, calendar_service):
        mock_auth.get_imap_credentials.return_value = None
        sync_all(mock_auth, mock_config)
        assert _window_days(calendar_service) == 30

    def test_uses_configured_days_ahead(self, mock_auth, mock_config, calendar_service):
        mock_auth.get_imap_credentials.return_value = None
        mock_config.calendar_days_ahead = 62
        sync_all(mock_auth, mock_config)
        assert _window_days(calendar_service) == 62

    def test_writes_events_to_cache(self, mock_auth, mock_config, calendar_service):
        mock_auth.get_imap_credentials.return_value = None
        sync_all(mock_auth, mock_config)
        cached = json.loads((Path(mock_config.cache_dir) / "calendar.json").read_text())
        assert cached == [{"title": "Dentist"}]
