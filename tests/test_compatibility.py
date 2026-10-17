"""Regressions reproduced with current pyicloud and iCloud IMAP servers."""

from __future__ import annotations

import email
import imaplib
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pyicloud.exceptions import PyiCloudAPIResponseException
from pyicloud.services.findmyiphone import FindMyiPhoneServiceManager

from icloud_cli.auth import KEYRING_IMAP_SERVICE, AuthManager
from icloud_cli.config import Config
from icloud_cli.output import render
from icloud_cli.services.findmy import FindMyService
from icloud_cli.services.notes import NotesService
from icloud_cli.services.reminders import RemindersService


def test_findmy_accepts_real_service_manager(mock_api):
    device = MagicMock()
    device.status.return_value = {
        "name": "Example phone", "deviceDisplayName": "Phone", "batteryLevel": None,
    }
    device.location = {"latitude": 0, "longitude": 0}
    # Use the real manager's public devices property without network construction.
    manager = object.__new__(FindMyiPhoneServiceManager)
    manager._devices = {"example-id": device}
    mock_api.devices = manager
    service = FindMyService(mock_api)

    assert service.list_devices()[0]["location"] == "0.000000, 0.000000"
    assert service.locate_device("example PHONE")["battery"] == ""
    assert service.play_sound("Example phone") is True
    device.play_sound.assert_called_once()


def test_imap_username_roundtrip_keeps_keychain_account(mock_config):
    auth = AuthManager(mock_config)
    with patch("icloud_cli.auth.click.prompt", return_value=" example-app-password "), \
         patch("icloud_cli.auth.keyring.set_password") as save:
        assert auth.setup_imap_password(imap_username="mail@icloud.com") is True
    save.assert_called_once_with(
        KEYRING_IMAP_SERVICE, mock_config.apple_id, "example-app-password"
    )
    restored = Config.load(mock_config.config_file)
    assert restored.imap_username == "mail@icloud.com"
    with patch("icloud_cli.auth.keyring.get_password", return_value="app-password") as read:
        assert AuthManager(restored).get_imap_credentials() == ("mail@icloud.com", "app-password")
    read.assert_called_once_with(KEYRING_IMAP_SERVICE, mock_config.apple_id)


def test_imap_username_defaults_to_apple_id(mock_config):
    with patch("icloud_cli.auth.keyring.get_password", return_value="app-password"):
        assert AuthManager(mock_config).get_imap_credentials()[0] == mock_config.apple_id


def test_setup_imap_cli_forwards_username(runner, mock_config):
    from icloud_cli.main import cli

    with patch("icloud_cli.main.Config.load", return_value=mock_config), \
         patch("icloud_cli.main.AuthManager") as auth:
        result = runner.invoke(cli, ["notes", "setup-imap", "--username", "mail@icloud.com"])
    assert result.exit_code == 0
    auth.return_value.setup_imap_password.assert_called_once_with(imap_username="mail@icloud.com")


@pytest.fixture
def imap_notes():
    service = NotesService("mail@icloud.com", "example-app-password")
    conn = MagicMock()
    conn.select.return_value = ("OK", [b"1"])
    conn.search.return_value = ("OK", [b"1"])
    conn.fetch.return_value = (
        "OK", [(b"1", b"Subject: Example\r\nDate: Thu, 1 Jan 2026 10:00:00 +0000\r\n\r\nBody")]
    )
    conn.append.return_value = ("OK", [])
    service._connect = MagicMock(return_value=conn)
    return service, conn


def test_notes_list_fetches_real_headers(imap_notes):
    service, conn = imap_notes
    assert service.list_notes()[0]["subject"] == "Example"
    conn.fetch.assert_called_once_with(b"1", "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])")
    conn.select.assert_called_once_with("Notes", readonly=True)


@pytest.mark.parametrize("payload", [[None], [b""], []])
def test_notes_empty_search_and_list(imap_notes, payload):
    service, conn = imap_notes
    conn.search.return_value = ("OK", payload)
    assert service.search_notes("missing") == []
    assert service.list_notes() == []


def test_notes_search_escapes_quoted_strings(imap_notes):
    service, conn = imap_notes
    assert service.search_notes('a"b\\c')[0]["subject"] == "Example"
    conn.search.assert_called_once_with(None, "OR", "SUBJECT", '"a\\"b\\\\c"',
                                       "TEXT", '"a\\"b\\\\c"')


def test_notes_mime_body_matches_transfer_encoding(imap_notes):
    service, conn = imap_notes
    assert service.add_note("A & B", "<b>plain</b>\nnext") is True
    msg = email.message_from_bytes(conn.append.call_args.args[3])
    body = msg.get_payload(decode=True).decode("utf-8")
    assert "&lt;b&gt;plain&lt;/b&gt;<br>next" in body
    assert "<title>A &amp; B</title>" in body


def test_notes_failed_select_does_not_mask_result(imap_notes):
    service, conn = imap_notes
    conn.select.return_value = ("NO", [])
    conn.close.side_effect = imaplib.IMAP4.error("not selected")
    assert service.list_notes("missing") == []
    conn.logout.assert_called_once()


def test_notes_show_does_not_mark_message_seen(imap_notes):
    service, conn = imap_notes
    assert service.get_note("1")["body"] == "Body"
    conn.fetch.assert_called_once_with(b"1", "(BODY.PEEK[])")


def test_empty_json_is_still_json(capsys):
    render([], format="json")
    assert json.loads(capsys.readouterr().out) == []


def test_2fa_retry_requests_new_challenge(mock_config):
    api = MagicMock()
    api.request_2fa_code.return_value = True
    api.two_factor_delivery_method = "trusted_device"
    api.two_factor_delivery_notice = None
    api.is_trusted_session = True
    api.validate_2fa_code.side_effect = [False, True]
    auth = AuthManager(mock_config)
    auth._api = api
    with patch("icloud_cli.auth.click.prompt", return_value="123456"):
        assert auth._handle_2fa() is True
    calls = [call[0] for call in api.method_calls]
    assert calls == [
        "request_2fa_code", "validate_2fa_code", "request_2fa_code", "validate_2fa_code",
    ]


def test_2fa_failed_redelivery_does_not_validate_again(mock_config):
    api = MagicMock()
    api.request_2fa_code.side_effect = [True, False]
    api.two_factor_delivery_method = "trusted_device"
    api.two_factor_delivery_notice = None
    api.validate_2fa_code.return_value = False
    auth = AuthManager(mock_config)
    auth._api = api
    with patch("icloud_cli.auth.click.prompt", return_value="123456") as prompt:
        assert auth._handle_2fa() is False
    prompt.assert_called_once()
    api.validate_2fa_code.assert_called_once()


def _zone_api(mock_api):
    reminder = SimpleNamespace(
        id="reminder-1", list_id="list-1", title="Example", desc="", due_date=None,
        priority=0, completed=False, deleted=False,
    )
    mock_api.reminders.lists.return_value = [SimpleNamespace(id="list-1", title="Personal")]
    mock_api.reminders.iter_changes.return_value = [SimpleNamespace(
        reminder_id=reminder.id, reminder=reminder, type="updated",
    )]
    return mock_api.reminders


def test_cursor_failure_uses_zone_snapshot_without_saving_bad_cursor(mock_api, mock_config):
    api = _zone_api(mock_api)
    api.sync_cursor.side_effect = PyiCloudAPIResponseException("Bad Request", 400)
    service = RemindersService(mock_api, mock_config)
    assert service.list_reminders()[0]["title"] == "Example"
    api.iter_changes.assert_called_once_with(since=None)
    api.reminders.assert_not_called()
    assert not service._state_file.exists()


def test_per_list_query_failure_falls_back_to_zone_snapshot(mock_api, mock_config):
    api = _zone_api(mock_api)
    api.sync_cursor.return_value = "cursor-before-read"
    api.reminders.side_effect = PyiCloudAPIResponseException("Bad Request", 400)
    service = RemindersService(mock_api, mock_config)
    assert service.list_reminders()[0]["list"] == "Personal"
    api.iter_changes.assert_called_once_with(since=None)
    assert service._load_sync_state()[0] == "cursor-before-read"
