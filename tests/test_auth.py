"""Tests for the auth module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from icloud_cli.auth import AuthManager
from icloud_cli.config import Config


class TestAuthManager:
    """Tests for AuthManager."""

    def test_get_status_not_logged_in(self, tmp_path):
        """Status shows not logged in when no credentials stored."""
        config = Config(
            apple_id="",
            session_dir=str(tmp_path / "session"),
            config_file=tmp_path / "config.toml",
        )
        auth = AuthManager(config)
        status = auth.get_status()

        assert status["apple_id"] == "(not set)"
        assert status["password_stored"] == "No"
        assert status["session_cached"] == "No"

    @patch("icloud_cli.auth.keyring")
    def test_get_status_logged_in(self, mock_keyring, tmp_path):
        """Status shows logged in when credentials are stored."""
        config = Config(
            apple_id="test@icloud.com",
            session_dir=str(tmp_path / "session"),
            config_file=tmp_path / "config.toml",
        )
        # Create a session file
        session_dir = tmp_path / "session"
        session_dir.mkdir(parents=True)
        (session_dir / "session_cookie").write_text("fake_cookie")

        mock_keyring.get_password.return_value = "stored_password"

        auth = AuthManager(config)
        status = auth.get_status()

        assert status["apple_id"] == "test@icloud.com"
        assert status["password_stored"] == "Yes"
        assert status["session_cached"] == "Yes"

    @patch("icloud_cli.auth.keyring")
    def test_logout_clears_session(self, mock_keyring, tmp_path):
        """Logout clears session files."""
        config = Config(
            apple_id="test@icloud.com",
            session_dir=str(tmp_path / "session"),
            config_file=tmp_path / "config.toml",
        )
        session_dir = tmp_path / "session"
        session_dir.mkdir(parents=True)
        (session_dir / "cookie1").write_text("data")
        (session_dir / "cookie2").write_text("data")

        mock_keyring.delete_password.return_value = None

        auth = AuthManager(config)
        auth.logout()

        # Session files should be cleared
        assert list(session_dir.iterdir()) == []

    @patch("icloud_cli.auth.keyring")
    def test_has_no_cached_session(self, mock_keyring, tmp_path):
        """Reports no session when session dir is empty."""
        config = Config(
            apple_id="test@icloud.com",
            session_dir=str(tmp_path / "session"),
            config_file=tmp_path / "config.toml",
        )
        (tmp_path / "session").mkdir(parents=True)

        mock_keyring.get_password.return_value = None

        auth = AuthManager(config)
        assert not auth._has_cached_session()

    @patch("icloud_cli.auth.keyring")
    def test_imap_credentials_not_set(self, mock_keyring, tmp_path):
        """Returns None when IMAP credentials are not configured."""
        config = Config(
            apple_id="test@icloud.com",
            session_dir=str(tmp_path / "session"),
            config_file=tmp_path / "config.toml",
        )
        mock_keyring.get_password.return_value = None

        auth = AuthManager(config)
        assert auth.get_imap_credentials() is None


class TestHandle2FA:
    """Tests for the interactive 2FA prompt flow."""

    def _make_auth(self, tmp_path, api):
        config = Config(
            apple_id="test@icloud.com",
            session_dir=str(tmp_path / "session"),
            config_file=tmp_path / "config.toml",
        )
        auth = AuthManager(config)
        auth._api = api
        return auth

    @patch("icloud_cli.auth.click")
    def test_security_key_challenge_does_not_prompt(self, mock_click, tmp_path):
        """When request_2fa_code() returns False, no code is requested."""
        api = MagicMock()
        api.request_2fa_code.return_value = False
        api.two_factor_delivery_method = "security_key"
        auth = self._make_auth(tmp_path, api)

        assert auth._handle_2fa() is False
        api.request_2fa_code.assert_called_once()
        # No code should be prompted for or validated when nothing was delivered.
        mock_click.prompt.assert_not_called()
        api.validate_2fa_code.assert_not_called()

    @patch("icloud_cli.auth.error")
    @patch("icloud_cli.auth.click")
    def test_missing_delivery_channel_has_accurate_error(
        self, mock_click, mock_error, tmp_path
    ):
        """A missing delivery route is not misreported as a security-key challenge."""
        api = MagicMock()
        api.request_2fa_code.return_value = False
        api.two_factor_delivery_method = "unknown"
        auth = self._make_auth(tmp_path, api)

        assert auth._handle_2fa() is False
        message = str(mock_error.call_args.args[0]).lower()
        assert "delivery channel" in message
        assert "hardware security key" not in message
        mock_click.prompt.assert_not_called()

    @patch("icloud_cli.auth.click")
    def test_trusted_device_success(self, mock_click, tmp_path):
        """A valid trusted-device code trusts the session and succeeds."""
        api = MagicMock()
        api.request_2fa_code.return_value = True
        api.two_factor_delivery_method = "trusted_device"
        api.two_factor_delivery_notice = None
        api.validate_2fa_code.return_value = True
        api.is_trusted_session = False
        auth = self._make_auth(tmp_path, api)
        mock_click.prompt.return_value = "123456"

        assert auth._handle_2fa() is True
        api.validate_2fa_code.assert_called_once_with("123456")
        api.trust_session.assert_called_once()

    @patch("icloud_cli.auth.info")
    @patch("icloud_cli.auth.click")
    def test_prompt_text_matches_delivery_channel(self, mock_click, mock_info, tmp_path):
        """The prompt describes the trusted-device channel without an approve step."""
        api = MagicMock()
        api.request_2fa_code.return_value = True
        api.two_factor_delivery_method = "trusted_device"
        api.two_factor_delivery_notice = None
        api.validate_2fa_code.return_value = True
        api.is_trusted_session = True
        auth = self._make_auth(tmp_path, api)
        mock_click.prompt.return_value = "123456"

        auth._handle_2fa()

        messages = " ".join(str(c.args[0]) for c in mock_info.call_args_list).lower()
        assert "approve" not in messages
        assert "trusted device" in messages

    @patch("icloud_cli.auth.click")
    def test_retries_then_succeeds(self, mock_click, tmp_path):
        """A mistyped code is retried instead of forcing a re-login."""
        api = MagicMock()
        api.request_2fa_code.return_value = True
        api.two_factor_delivery_method = "sms"
        api.two_factor_delivery_notice = None
        api.validate_2fa_code.side_effect = [False, True]
        api.is_trusted_session = True
        auth = self._make_auth(tmp_path, api)
        mock_click.prompt.return_value = "000000"

        assert auth._handle_2fa() is True
        assert api.validate_2fa_code.call_count == 2

    @patch("icloud_cli.auth.click")
    def test_invalid_code_exhausts_attempts(self, mock_click, tmp_path):
        """After three wrong codes the flow fails without trusting the session."""
        api = MagicMock()
        api.request_2fa_code.return_value = True
        api.two_factor_delivery_method = "trusted_device"
        api.two_factor_delivery_notice = None
        api.validate_2fa_code.return_value = False
        auth = self._make_auth(tmp_path, api)
        mock_click.prompt.return_value = "000000"

        assert auth._handle_2fa() is False
        assert api.validate_2fa_code.call_count == 3
        api.trust_session.assert_not_called()
