"""Authentication management for icloud-cli.

Handles Apple ID login, 2FA verification, session caching,
and credential storage via OS keyring.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
import keyring
from pyicloud import PyiCloudService
from pyicloud.exceptions import (
    PyiCloudFailedLoginException,
)

from icloud_cli.config import Config
from icloud_cli.output import error, info, success, warning

KEYRING_SERVICE = "icloud-cli-tools"
KEYRING_IMAP_SERVICE = "icloud-cli-tools-imap"


class AuthManager:
    """Manages iCloud authentication, sessions, and credentials."""

    def __init__(self, config: Config):
        self.config = config
        self._api: PyiCloudService | None = None

    @property
    def api(self) -> PyiCloudService:
        """Get authenticated PyiCloudService instance."""
        if self._api is None:
            self._api = self._get_session()
        return self._api

    def login(self) -> bool:
        """Interactive login flow with 2FA support.

        Returns True if login was successful.
        """
        # Get Apple ID — always allow changing
        apple_id = self.config.apple_id
        if apple_id:
            apple_id = click.prompt("Apple ID (email)", default=apple_id)
        else:
            apple_id = click.prompt("Apple ID (email)")
        self.config.apple_id = apple_id
        self.config.save()

        # Get password from keyring or prompt
        password = keyring.get_password(KEYRING_SERVICE, apple_id)
        if not password:
            password = click.prompt("Password", hide_input=True)
            if click.confirm("Save password to system keyring?", default=True):
                keyring.set_password(KEYRING_SERVICE, apple_id, password)
                success("Password saved to keyring.")

        # Authenticate
        try:
            session_dir = Path(self.config.session_dir)
            session_dir.mkdir(parents=True, exist_ok=True)

            self._api = PyiCloudService(
                apple_id=apple_id,
                password=password,
                cookie_directory=str(session_dir),
            )
        except PyiCloudFailedLoginException as e:
            error(f"Login failed: {e}")
            return False
        except Exception as e:
            error(f"Connection error: {e}")
            return False

        # Handle 2FA
        if self._api.requires_2fa:
            return self._handle_2fa()

        if self._api.requires_2sa:
            return self._handle_2sa()

        success(f"Logged in as {apple_id}")
        return True

    def _handle_2fa(self) -> bool:
        """Handle two-factor authentication (HSA2 trusted device or SMS code)."""
        info("Two-factor authentication required.")

        try:
            delivered = self._api.request_2fa_code()
        except Exception as e:
            error(f"Failed to trigger 2FA delivery: {e}")
            return False

        if not delivered:
            # request_2fa_code() returns False only when Apple wants a hardware
            # security key (or offers no code-delivery channel at all), which
            # this CLI cannot drive. Don't prompt for a code that never arrives.
            error(
                "This 2FA challenge requires a hardware security key, "
                "which icloud-cli does not support."
            )
            return False

        # Describe the channel we'll actually validate against. validate_2fa_code()
        # keys off two_factor_delivery_method, so the prompt must match it — telling
        # the user to enter the SMS code when we're verifying the trusted-device
        # code (or vice versa) is what made the old prompt misleading.
        method = self._api.two_factor_delivery_method
        notice = self._api.two_factor_delivery_notice

        if method == "sms":
            info("Apple sent a 6-digit verification code by SMS.")
            info("Enter the code from the text message.")
        else:
            info("Apple sent a 6-digit verification code to your trusted devices.")
            info("Enter the code shown in the trusted-device notification.")

        if notice:
            warning(notice)

        max_attempts = 3
        for attempt in range(max_attempts):
            code = click.prompt("Enter 2FA code")
            try:
                if self._api.validate_2fa_code(code):
                    break
            except Exception as e:
                error(f"2FA verification failed: {e}")
                return False

            remaining = max_attempts - attempt - 1
            if remaining <= 0:
                error("Invalid 2FA code.")
                return False
            warning(f"Invalid 2FA code. {remaining} attempt(s) remaining.")

        if not self._api.is_trusted_session:
            info("Trusting this session...")
            self._api.trust_session()

        success("2FA verification successful!")
        return True

    def _handle_2sa(self) -> bool:
        """Handle two-step authentication (SMS/phone-based)."""
        info("Two-step authentication required.")

        devices = self._api.trusted_devices
        if not devices:
            error("No trusted devices found.")
            return False

        # Show available devices
        for i, device in enumerate(devices):
            phone = device.get("phoneNumber", "Unknown")
            info(f"  {i + 1}. {phone}")

        device_idx = click.prompt("Choose device number", type=int, default=1) - 1
        if device_idx < 0 or device_idx >= len(devices):
            error("Invalid device number.")
            return False

        device = devices[device_idx]
        if not self._api.send_verification_code(device):
            error("Failed to send verification code.")
            return False

        code = click.prompt("Enter verification code")
        if not self._api.validate_verification_code(device, code):
            error("Invalid verification code.")
            return False

        success("2SA verification successful!")
        return True

    def logout(self) -> None:
        """Clear all stored credentials and sessions."""
        # Remove keyring credentials
        apple_id = self.config.apple_id
        if apple_id:
            try:
                keyring.delete_password(KEYRING_SERVICE, apple_id)
                info("Removed password from keyring.")
            except keyring.errors.PasswordDeleteError:
                pass

            try:
                keyring.delete_password(KEYRING_IMAP_SERVICE, apple_id)
                info("Removed IMAP password from keyring.")
            except keyring.errors.PasswordDeleteError:
                pass

        # Clear session cookies
        session_dir = Path(self.config.session_dir)
        if session_dir.exists():
            for f in session_dir.iterdir():
                f.unlink()
            info("Cleared session cookies.")

        self._api = None
        success("Logged out successfully.")

    def get_status(self) -> dict:
        """Return current authentication status."""
        apple_id = self.config.apple_id
        has_password = bool(
            apple_id and keyring.get_password(KEYRING_SERVICE, apple_id)
        )
        has_imap_password = bool(
            apple_id and keyring.get_password(KEYRING_IMAP_SERVICE, apple_id)
        )
        has_session = self._has_cached_session()

        return {
            "apple_id": apple_id or "(not set)",
            "password_stored": "Yes" if has_password else "No",
            "imap_password_stored": "Yes" if has_imap_password else "No",
            "session_cached": "Yes" if has_session else "No",
            "session_dir": self.config.session_dir,
        }

    def setup_imap_password(self) -> bool:
        """Guide user through setting up an app-specific password for Notes (IMAP).

        Returns True if password was stored successfully.
        """
        apple_id = self.config.apple_id
        if not apple_id:
            error("Please login first with 'icloud-cli login'.")
            return False

        info("Notes access requires an app-specific password.")
        info("Generate one at: https://appleid.apple.com/account/manage")
        info("  → Sign In & Security → App-Specific Passwords → Generate")
        print()

        password = click.prompt("Enter app-specific password", hide_input=True)
        keyring.set_password(KEYRING_IMAP_SERVICE, apple_id, password)
        self.config.imap_password_in_keyring = True
        self.config.save()

        success("IMAP password saved to keyring.")
        return True

    def get_imap_credentials(self) -> tuple[str, str] | None:
        """Get IMAP credentials (apple_id, app-specific password).

        Returns None if not configured.
        """
        apple_id = self.config.apple_id
        if not apple_id:
            return None

        password = keyring.get_password(KEYRING_IMAP_SERVICE, apple_id)
        if not password:
            return None

        return (apple_id, password)

    def _get_session(self) -> PyiCloudService:
        """Get or restore a cached PyiCloudService session."""
        apple_id = self.config.apple_id
        if not apple_id:
            error("Not logged in. Run 'icloud-cli login' first.")
            sys.exit(1)

        password = keyring.get_password(KEYRING_SERVICE, apple_id)
        if not password:
            # No saved password — prompt interactively
            warning("No stored password found.")
            password = click.prompt("Password", hide_input=True)
            if click.confirm("Save password to system keyring?", default=True):
                keyring.set_password(KEYRING_SERVICE, apple_id, password)
                success("Password saved to keyring.")

        try:
            session_dir = Path(self.config.session_dir)
            session_dir.mkdir(parents=True, exist_ok=True)

            api = PyiCloudService(
                apple_id=apple_id,
                password=password,
                cookie_directory=str(session_dir),
            )

            if api.requires_2fa or api.requires_2sa:
                warning("Session expired. Please re-authenticate.")
                error("Run 'icloud-cli login' to refresh your session.")
                sys.exit(1)

            return api
        except PyiCloudFailedLoginException:
            error("Authentication failed. Run 'icloud-cli login' to re-authenticate.")
            sys.exit(1)
        except Exception as e:
            error(f"Failed to connect to iCloud: {e}")
            sys.exit(1)

    def _has_cached_session(self) -> bool:
        """Check if a cached session exists."""
        session_dir = Path(self.config.session_dir)
        if not session_dir.exists():
            return False
        return any(session_dir.iterdir())
