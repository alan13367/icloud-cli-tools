"""Tests for config loading and saving."""

from __future__ import annotations

from icloud_cli.config import Config


class TestCalendarDaysAhead:
    def test_default_is_30(self, tmp_path):
        config = Config.load(tmp_path / "missing.toml")
        assert config.calendar_days_ahead == 30

    def test_read_from_sync_section(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text("[sync]\ncalendar_days_ahead = 62\n")
        assert Config.load(path).calendar_days_ahead == 62

    def test_missing_key_keeps_default(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text("[sync]\nsync_interval_minutes = 5\n")
        assert Config.load(path).calendar_days_ahead == 30

    def test_round_trips_through_save(self, tmp_path):
        path = tmp_path / "config.toml"
        Config(config_file=path, calendar_days_ahead=45).save()
        assert Config.load(path).calendar_days_ahead == 45
