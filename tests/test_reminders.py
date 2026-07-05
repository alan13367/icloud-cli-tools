"""Tests for the reminders service."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from icloud_cli.services.reminders import RemindersService, _format_due_date


class TestFormatDueDate:
    """Tests for due date formatting."""

    def test_format_string_date(self):
        result = _format_due_date("2025-06-15T14:30:00")
        assert "2025-06-15" in result

    def test_format_list_date(self):
        result = _format_due_date([2025, 6, 15, 14, 30])
        assert result == "2025-06-15 14:30"

    def test_format_datetime(self):
        result = _format_due_date(datetime(2025, 6, 15, 14, 30))
        assert result == "2025-06-15 14:30"

    def test_format_none(self):
        result = _format_due_date(None)
        assert result == "None"


class TestRemindersService:
    """Tests for RemindersService with mocked API."""

    def _make_service(self, mock_api, mock_config):
        return RemindersService(mock_api, mock_config)

    def _make_list_model(self, list_id="list-1", title="Personal"):
        """Create a mock RemindersList-like object."""
        lst = MagicMock()
        lst.id = list_id
        lst.title = title
        lst.guid = list_id
        return lst

    def _make_reminder_model(
        self, reminder_id="rem-1", title="Buy groceries",
        completed=False, due_date=None, priority=0, desc="",
    ):
        """Create a mock Reminder-like object."""
        r = MagicMock()
        r.id = reminder_id
        r.title = title
        r.completed = completed
        r.due_date = due_date
        r.priority = priority
        r.desc = desc
        r.list_id = "list-1"
        r.flagged = False
        return r

    def test_list_reminders_empty(self, mock_api, mock_config):
        mock_api.reminders.lists.return_value = []
        mock_api.reminders.reminders.return_value = []
        service = self._make_service(mock_api, mock_config)
        result = service.list_reminders()
        assert result == []

    def test_list_reminders_with_items(self, mock_api, mock_config):
        lst = self._make_list_model()
        mock_api.reminders.lists.return_value = [lst]

        reminder = self._make_reminder_model(
            due_date=datetime(2025, 6, 15, 10, 0),
            priority=1,
        )
        mock_api.reminders.reminders.return_value = [reminder]

        service = self._make_service(mock_api, mock_config)
        result = service.list_reminders()

        assert len(result) == 1
        assert result[0]["title"] == "Buy groceries"
        assert result[0]["list"] == "Personal"
        assert result[0]["priority"] == "High"

    def test_list_reminders_filters_completed(self, mock_api, mock_config):
        lst = self._make_list_model(list_id="list-1", title="Work")
        mock_api.reminders.lists.return_value = [lst]

        rem1 = self._make_reminder_model(
            reminder_id="rem-1", title="Done task", completed=True,
        )
        rem2 = self._make_reminder_model(
            reminder_id="rem-2", title="Open task", completed=False,
        )
        mock_api.reminders.reminders.return_value = [rem1, rem2]

        service = self._make_service(mock_api, mock_config)

        # Without completed
        result = service.list_reminders(show_completed=False)
        assert len(result) == 1
        assert result[0]["title"] == "Open task"

        # With completed
        result = service.list_reminders(show_completed=True)
        assert len(result) == 2

    def test_add_reminder_success(self, mock_api, mock_config):
        lst = self._make_list_model()
        mock_api.reminders.lists.return_value = [lst]
        mock_api.reminders.create.return_value = MagicMock()

        service = self._make_service(mock_api, mock_config)
        assert service.add_reminder(title="New task") is True
        mock_api.reminders.create.assert_called_once()

    def test_add_reminder_with_list_name(self, mock_api, mock_config):
        lst1 = self._make_list_model(list_id="list-1", title="Personal")
        lst2 = self._make_list_model(list_id="list-2", title="Shopping")
        mock_api.reminders.lists.return_value = [lst1, lst2]
        mock_api.reminders.create.return_value = MagicMock()

        service = self._make_service(mock_api, mock_config)
        assert service.add_reminder(title="Buy milk", list_name="Shopping") is True

        # Verify create was called with the correct list_id
        call_kwargs = mock_api.reminders.create.call_args[1]
        assert call_kwargs["list_id"] == "list-2"

    def test_delete_reminder_success(self, mock_api, mock_config):
        reminder = self._make_reminder_model()
        mock_api.reminders.get.return_value = reminder
        mock_api.reminders.delete.return_value = None

        service = self._make_service(mock_api, mock_config)
        assert service.delete_reminder("rem-1") is True
        mock_api.reminders.delete.assert_called_once_with(reminder)

    def test_delete_reminder_failure(self, mock_api, mock_config):
        mock_api.reminders.get.side_effect = Exception("not found")

        service = self._make_service(mock_api, mock_config)
        assert service.delete_reminder("rem-1") is False

    def test_complete_reminder_success(self, mock_api, mock_config):
        reminder = self._make_reminder_model(completed=False)
        mock_api.reminders.get.return_value = reminder
        mock_api.reminders.update.return_value = None

        service = self._make_service(mock_api, mock_config)
        assert service.complete_reminder("rem-1") is True
        assert reminder.completed is True
        assert reminder.completed_date is not None
        mock_api.reminders.update.assert_called_once_with(reminder)

    def test_complete_reminder_failure(self, mock_api, mock_config):
        mock_api.reminders.get.side_effect = Exception("not found")

        service = self._make_service(mock_api, mock_config)
        assert service.complete_reminder("rem-1") is False
