"""Tests for the notes service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from icloud_cli.services.notes import NotesService, _decode_header, _format_date


class TestDecodeHeader:
    """Tests for email header decoding."""

    def test_decode_plain_string(self):
        assert _decode_header("My Note") == "My Note"

    def test_decode_none(self):
        assert _decode_header(None) == "Untitled"

    def test_decode_empty(self):
        assert _decode_header("") == "Untitled"


class TestFormatDate:
    """Tests for date formatting."""

    def test_format_valid_date(self):
        result = _format_date("Mon, 15 Jun 2025 14:30:00 +0000")
        assert "2025-06-15" in result

    def test_format_empty(self):
        assert _format_date("") == ""

    def test_format_invalid(self):
        # Should return the original string on parse failure
        result = _format_date("not a date")
        assert result == "not a date"


class TestNotesService:
    """Tests for NotesService with mocked IMAP."""

    @patch("icloud_cli.services.notes.imaplib.IMAP4_SSL")
    def test_list_notes_empty(self, mock_imap_class):
        mock_conn = MagicMock()
        mock_imap_class.return_value = mock_conn
        mock_conn.login.return_value = ("OK", [])
        mock_conn.select.return_value = ("OK", [b"0"])
        mock_conn.search.return_value = ("OK", [b""])

        service = NotesService("test@icloud.com", "password")
        result = service.list_notes()

        assert result == []
        mock_conn.logout.assert_called_once()

    @patch("icloud_cli.services.notes.imaplib.IMAP4_SSL")
    def test_search_notes(self, mock_imap_class):
        mock_conn = MagicMock()
        mock_imap_class.return_value = mock_conn
        mock_conn.login.return_value = ("OK", [])
        mock_conn.select.return_value = ("OK", [b"1"])
        mock_conn.search.return_value = ("OK", [b"1"])
        hdr_bytes = (
            b"Subject: Test Note\r\n"
            b"Date: Mon, 15 Jun 2025 14:30:00 +0000\r\n\r\n"
        )
        mock_conn.fetch.return_value = (
            "OK",
            [(b"1 (BODY[HEADER.FIELDS (SUBJECT DATE)] {50}", hdr_bytes), b")"],
        )

        service = NotesService("test@icloud.com", "password")
        result = service.search_notes("Test")

        assert len(result) == 1
        assert result[0]["subject"] == "Test Note"
