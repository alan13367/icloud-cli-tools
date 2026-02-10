"""Tests for the Find My service."""

from __future__ import annotations

from unittest.mock import MagicMock

from icloud_cli.services.findmy import FindMyService


def _make_mock_device(name="iPhone", model="iPhone 15", battery=0.85, lat=40.7128, lon=-74.0060):
    """Create a mock device."""
    device = MagicMock()
    device.status.return_value = {
        "name": name,
        "deviceDisplayName": model,
        "batteryLevel": battery,
        "deviceStatus": "Online",
    }
    device.location.return_value = {
        "latitude": lat,
        "longitude": lon,
        "horizontalAccuracy": 10,
        "timeStamp": "2025-06-15T14:30:00",
    }
    return device


class TestFindMyService:
    """Tests for FindMyService with mocked API."""

    def test_list_devices(self, mock_api):
        mock_api.devices = [_make_mock_device(), _make_mock_device("MacBook", "MacBook Pro", 0.62)]
        service = FindMyService(mock_api)
        devices = service.list_devices()

        assert len(devices) == 2
        assert devices[0]["name"] == "iPhone"
        assert devices[0]["battery"] == "85%"
        assert devices[1]["name"] == "MacBook"

    def test_list_devices_empty(self, mock_api):
        mock_api.devices = []
        service = FindMyService(mock_api)
        assert service.list_devices() == []

    def test_locate_device_found(self, mock_api):
        mock_api.devices = [_make_mock_device()]
        service = FindMyService(mock_api)
        result = service.locate_device("iPhone")

        assert result is not None
        assert "40.7128" in result["latitude"]
        assert "google.com/maps" in result["maps_url"]

    def test_locate_device_not_found(self, mock_api):
        mock_api.devices = []
        service = FindMyService(mock_api)
        assert service.locate_device("NonExistent") is None

    def test_locate_device_partial_match(self, mock_api):
        mock_api.devices = [_make_mock_device("Alan's iPhone 15 Pro")]
        service = FindMyService(mock_api)
        result = service.locate_device("iphone")

        assert result is not None
        assert result["device"] == "Alan's iPhone 15 Pro"

    def test_play_sound(self, mock_api):
        device = _make_mock_device()
        mock_api.devices = [device]
        service = FindMyService(mock_api)

        assert service.play_sound("iPhone") is True
        device.play_sound.assert_called_once()

    def test_play_sound_not_found(self, mock_api):
        mock_api.devices = []
        service = FindMyService(mock_api)
        assert service.play_sound("NonExistent") is False

    def test_lost_mode(self, mock_api):
        device = _make_mock_device()
        mock_api.devices = [device]
        service = FindMyService(mock_api)

        assert service.lost_mode("iPhone", phone="123456", message="Lost!") is True
        device.lost_device.assert_called_once_with(number="123456", text="Lost!")
