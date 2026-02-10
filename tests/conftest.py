"""Shared pytest fixtures for icloud-cli tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from icloud_cli.config import Config


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_config(tmp_path):
    """Create a temporary config for testing."""
    config = Config(
        apple_id="test@icloud.com",
        session_dir=str(tmp_path / "session"),
        cache_dir=str(tmp_path / "cache"),
        config_file=tmp_path / "config.toml",
    )
    config.ensure_dirs()
    return config


@pytest.fixture
def mock_api():
    """Create a mocked PyiCloudService."""
    api = MagicMock()
    api.requires_2fa = False
    api.requires_2sa = False
    api.is_trusted_session = True
    return api


@pytest.fixture
def mock_auth(mock_api, mock_config):
    """Create a mocked AuthManager."""
    with patch("icloud_cli.auth.AuthManager") as mock_auth_cls:
        auth = mock_auth_cls.return_value
        auth.api = mock_api
        auth.config = mock_config
        auth.get_imap_credentials.return_value = ("test@icloud.com", "test-password")
        auth.get_status.return_value = {
            "apple_id": "test@icloud.com",
            "password_stored": "Yes",
            "imap_password_stored": "Yes",
            "session_cached": "Yes",
            "session_dir": mock_config.session_dir,
        }
        yield auth
