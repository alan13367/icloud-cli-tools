"""Tests for the reminders service."""

from __future__ import annotations

from icloud_cli.services.reminders import RemindersService, _format_due_date


class TestFormatDueDate:
    """Tests for due date formatting."""

    def test_format_string_date(self):
        result = _format_due_date("2025-06-15T14:30:00")
        assert "2025-06-15" in result

    def test_format_list_date(self):
        result = _format_due_date([2025, 6, 15, 14, 30])
        assert result == "2025-06-15 14:30"

    def test_format_none(self):
        result = _format_due_date(None)
        assert result == "None"


class TestRemindersService:
    """Tests for RemindersService with mocked API."""

    def _make_service(self, mock_api, mock_config):
        return RemindersService(mock_api, mock_config)

    def test_list_reminders_empty(self, mock_api, mock_config):
        mock_api.reminders.lists = {}
        service = self._make_service(mock_api, mock_config)
        result = service.list_reminders()
        assert result == []

    def test_list_reminders_with_items(self, mock_api, mock_config):
        mock_api.reminders.lists = {
            "list-1": {"title": "Personal", "guid": "list-1"}
        }
        mock_api.reminders.get.return_value = [
            {
                "guid": "rem-1",
                "title": "Buy groceries",
                "completedDate": None,
                "dueDate": [2025, 6, 15, 10, 0],
                "priority": 1,
                "description": "",
            }
        ]

        service = self._make_service(mock_api, mock_config)
        result = service.list_reminders()

        assert len(result) == 1
        assert result[0]["title"] == "Buy groceries"
        assert result[0]["list"] == "Personal"
        assert result[0]["priority"] == "High"

    def test_list_reminders_filters_completed(self, mock_api, mock_config):
        mock_api.reminders.lists = {
            "list-1": {"title": "Work", "guid": "list-1"}
        }
        mock_api.reminders.get.return_value = [
            {"guid": "rem-1", "title": "Done task", "completedDate": "2025-06-14", "priority": 0},
            {"guid": "rem-2", "title": "Open task", "completedDate": None, "priority": 0},
        ]

        service = self._make_service(mock_api, mock_config)

        # Without completed
        result = service.list_reminders(show_completed=False)
        assert len(result) == 1
        assert result[0]["title"] == "Open task"

        # With completed
        result = service.list_reminders(show_completed=True)
        assert len(result) == 2

    def test_add_reminder_success(self, mock_api, mock_config):
        mock_api.reminders.post.return_value = None
        service = self._make_service(mock_api, mock_config)
        assert service.add_reminder(title="New task") is True

    def test_delete_reminder_success(self, mock_api, mock_config):
        mock_api.reminders.delete.return_value = None
        service = self._make_service(mock_api, mock_config)
        assert service.delete_reminder("rem-1") is True

    def test_delete_reminder_failure(self, mock_api, mock_config):
        mock_api.reminders.delete.side_effect = Exception("not found")
        service = self._make_service(mock_api, mock_config)
        assert service.delete_reminder("rem-1") is False
