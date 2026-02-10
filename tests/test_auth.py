"""Tests for the auth module."""

from __future__ import annotations

from unittest.mock import patch

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
