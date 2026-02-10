"""Find My service for icloud-cli.

Provides device tracking, sound playing, and lost mode via pyicloud.
"""

from __future__ import annotations

from typing import Any

from pyicloud import PyiCloudService


class FindMyService:
    """Manages Find My devices."""

    def __init__(self, api: PyiCloudService):
        self.api = api

    def list_devices(self) -> list[dict[str, Any]]:
        """List all devices associated with the iCloud account.

        Returns:
            List of device dictionaries.
        """
        try:
            devices = self.api.devices
        except Exception as e:
            from icloud_cli.output import error
            error(f"Failed to fetch devices: {e}")
            return []

        result = []
        for device in devices:
            status_data = device.status()
            location = device.location()

            loc_str = ""
            if location and location.get("latitude") and location.get("longitude"):
                lat = location["latitude"]
                lon = location["longitude"]
                loc_str = f"{lat:.6f}, {lon:.6f}"

            battery = ""
            battery_level = status_data.get("batteryLevel")
            if battery_level is not None:
                battery = f"{battery_level * 100:.0f}%"

            result.append({
                "name": status_data.get("name", "Unknown"),
                "model": status_data.get("deviceDisplayName", "Unknown"),
                "battery": battery,
                "status": status_data.get("deviceStatus", "Unknown"),
                "location": loc_str,
            })

        return result

    def locate_device(self, device_name: str) -> dict[str, Any] | None:
        """Get detailed location of a device.

        Args:
            device_name: Name of the device to locate.

        Returns:
            Location details dict, or None if not found.
        """
        device = self._find_device(device_name)
        if not device:
            return None

        status_data = device.status()
        location = device.location()

        if not location:
            from icloud_cli.output import warning
            warning(f"Location unavailable for '{device_name}'.")
            return {
                "device": status_data.get("name", "Unknown"),
                "status": "Location unavailable",
            }

        lat = location.get("latitude", 0)
        lon = location.get("longitude", 0)
        maps_url = f"https://www.google.com/maps?q={lat},{lon}"

        return {
            "device": status_data.get("name", "Unknown"),
            "model": status_data.get("deviceDisplayName", "Unknown"),
            "latitude": f"{lat:.6f}",
            "longitude": f"{lon:.6f}",
            "accuracy": f"{location.get('horizontalAccuracy', 'N/A')}m",
            "timestamp": location.get("timeStamp", ""),
            "maps_url": maps_url,
            "battery": f"{status_data.get('batteryLevel', 0) * 100:.0f}%",
        }

    def play_sound(self, device_name: str) -> bool:
        """Play a sound on a device.

        Args:
            device_name: Name of the device.

        Returns:
            True if sound was triggered.
        """
        device = self._find_device(device_name)
        if not device:
            return False

        try:
            device.play_sound()
            return True
        except Exception as e:
            from icloud_cli.output import error
            error(f"Failed to play sound: {e}")
            return False

    def lost_mode(
        self, device_name: str, phone: str, message: str
    ) -> bool:
        """Activate Lost Mode on a device.

        Args:
            device_name: Name of the device.
            phone: Contact phone number.
            message: Lock screen message.

        Returns:
            True if Lost Mode was activated.
        """
        device = self._find_device(device_name)
        if not device:
            return False

        try:
            device.lost_device(number=phone, text=message)
            return True
        except Exception as e:
            from icloud_cli.output import error
            error(f"Failed to activate Lost Mode: {e}")
            return False

    def _find_device(self, name: str) -> Any | None:
        """Find a device by name (case-insensitive partial match).

        Args:
            name: Device name to search for.

        Returns:
            Device object or None.
        """
        try:
            devices = self.api.devices
        except Exception:
            return None

        name_lower = name.lower()

        # Exact match first
        for device in devices:
            status = device.status()
            if status.get("name", "").lower() == name_lower:
                return device

        # Partial match
        for device in devices:
            status = device.status()
            if name_lower in status.get("name", "").lower():
                return device

        return None
