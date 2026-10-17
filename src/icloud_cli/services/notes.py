"""Notes service for icloud-cli.

Accesses iCloud Notes via IMAP protocol. Notes are stored as email messages
in the 'Notes' IMAP folder on imap.mail.me.com.

Requires an app-specific password generated at https://appleid.apple.com.
"""

from __future__ import annotations

import email
import email.header
import imaplib
from contextlib import suppress
from datetime import datetime
from email.mime.text import MIMEText
from html import escape
from typing import Any

import html2text

IMAP_HOST = "imap.mail.me.com"
IMAP_PORT = 993
NOTES_FOLDER = "Notes"


class NotesService:
    """Manages iCloud Notes via IMAP."""

    def __init__(self, apple_id: str, imap_password: str):
        self.apple_id = apple_id
        self.imap_password = imap_password
        self._h2t = html2text.HTML2Text()
        self._h2t.ignore_links = False
        self._h2t.body_width = 0  # Don't wrap lines

    def _connect(self) -> imaplib.IMAP4_SSL:
        """Establish IMAP connection and login."""
        try:
            conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
            conn.login(self.apple_id, self.imap_password)
            return conn
        except imaplib.IMAP4.error as e:
            from icloud_cli.output import error
            error(f"IMAP login failed: {e}")
            error("Make sure you're using an app-specific password.")
            raise

    def list_notes(self, folder: str | None = None) -> list[dict[str, Any]]:
        """List all notes, optionally filtered by folder.

        Args:
            folder: IMAP folder name to filter (default: 'Notes').

        Returns:
            List of note metadata dictionaries.
        """
        conn = self._connect()
        try:
            target_folder = folder or NOTES_FOLDER
            status, _ = conn.select(target_folder, readonly=True)
            if status != "OK":
                from icloud_cli.output import warning
                warning(f"Folder '{target_folder}' not found.")
                return []

            # Search for all messages in Notes folder
            status, data = conn.search(None, "ALL")
            if status != "OK":
                return []

            message_ids = (data[0] or b"").split() if data else []
            result = []

            for msg_id in message_ids:
                status, hdr_data = conn.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])")
                if status != "OK" or not hdr_data or not isinstance(hdr_data[0], tuple):
                    continue
                hdr = email.message_from_bytes(hdr_data[0][1])
                subject = _decode_header(hdr.get("Subject", "Untitled"))
                date_str = hdr.get("Date", "")

                result.append({
                    "id": msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id),
                    "subject": subject,
                    "date": _format_date(date_str),
                    "folder": target_folder,
                })

            return result

        finally:
            with suppress(imaplib.IMAP4.error):
                conn.close()
            conn.logout()

    def get_note(self, note_id: str) -> dict[str, Any] | None:
        """Get a note's full content.

        Args:
            note_id: IMAP message ID.

        Returns:
            Note dictionary with content, or None.
        """
        conn = self._connect()
        try:
            conn.select(NOTES_FOLDER, readonly=True)

            status, msg_data = conn.fetch(note_id.encode(), "(BODY.PEEK[])")
            if status != "OK" or not msg_data[0]:
                return None

            raw_email = msg_data[0]
            if isinstance(raw_email, tuple):
                msg = email.message_from_bytes(raw_email[1])
            else:
                return None

            subject = _decode_header(msg.get("Subject", "Untitled"))
            date_str = msg.get("Date", "")

            # Extract body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if content_type == "text/html":
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = self._h2t.handle(payload.decode("utf-8", errors="replace"))
                        break
                    elif content_type == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = payload.decode("utf-8", errors="replace")
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    content_type = msg.get_content_type()
                    decoded = payload.decode("utf-8", errors="replace")
                    body = (
                        self._h2t.handle(decoded)
                        if content_type == "text/html"
                        else decoded
                    )

            return {
                "id": note_id,
                "subject": subject,
                "date": _format_date(date_str),
                "body": body.strip(),
            }

        finally:
            with suppress(imaplib.IMAP4.error):
                conn.close()
            conn.logout()

    def add_note(
        self, title: str, body: str, folder: str | None = None
    ) -> bool:
        """Create a new note via IMAP APPEND.

        Args:
            title: Note title (becomes Subject).
            body: Note body text.
            folder: Target folder (default: 'Notes').

        Returns:
            True if note was created.
        """
        conn = self._connect()
        try:
            target_folder = folder or NOTES_FOLDER

            # Construct MIME once so transfer encoding matches the HTML body.
            html_body = (
                f"<html><head><title>{escape(title)}</title></head>"
                f"<body><div>{escape(body).replace(chr(10), '<br>')}</div></body></html>"
            )
            msg = MIMEText(html_body, "html", "utf-8")
            msg["Subject"] = title
            msg["From"] = self.apple_id
            msg["X-Uniform-Type-Identifier"] = "com.apple.mail-note"
            msg["Date"] = email.utils.formatdate(localtime=True)

            # Append to Notes folder
            status, _ = conn.append(
                target_folder,
                None,
                imaplib.Time2Internaldate(datetime.now().timestamp()),
                msg.as_bytes(),
            )

            return status == "OK"

        except Exception as e:
            from icloud_cli.output import error
            error(f"Failed to create note: {e}")
            return False
        finally:
            conn.logout()

    def search_notes(self, query: str) -> list[dict[str, Any]]:
        """Search notes by keyword.

        Args:
            query: Search keyword.

        Returns:
            List of matching note metadata.
        """
        conn = self._connect()
        try:
            conn.select(NOTES_FOLDER, readonly=True)

            # Escape IMAP quoted-string syntax in user input.
            query = query.replace("\\", "\\\\").replace('"', '\\"')
            # Search in subject and body
            status, data = conn.search(None, "OR", "SUBJECT", f'"{query}"', "TEXT", f'"{query}"')
            if status != "OK":
                return []

            message_ids = (data[0] or b"").split() if data else []
            result = []

            for msg_id in message_ids:
                status, hdr_data = conn.fetch(
                    msg_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])"
                )
                if status == "OK" and hdr_data[0] and isinstance(hdr_data[0], tuple):
                    hdr = email.message_from_bytes(hdr_data[0][1])
                    subject = _decode_header(hdr.get("Subject", "Untitled"))
                    date_str = hdr.get("Date", "")

                    result.append({
                        "id": msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id),
                        "subject": subject,
                        "date": _format_date(date_str),
                        "folder": NOTES_FOLDER,
                    })

            return result

        finally:
            with suppress(imaplib.IMAP4.error):
                conn.close()
            conn.logout()


def _decode_header(header: str | None) -> str:
    """Decode an email header value."""
    if not header:
        return "Untitled"

    decoded_parts = email.header.decode_header(header)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return " ".join(result)


def _format_date(date_str: str) -> str:
    """Format an email date header for display."""
    if not date_str:
        return ""
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return date_str
