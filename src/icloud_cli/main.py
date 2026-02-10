"""icloud-cli — Access iCloud services from Linux.

Main CLI entry point using Click with subcommand groups.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from icloud_cli import __version__
from icloud_cli.auth import AuthManager
from icloud_cli.config import Config
from icloud_cli.output import console, error, info, render, render_detail, success, warning


# ─── Global context ──────────────────────────────────────────────────────────

class AppContext:
    """Shared application context passed through Click."""

    def __init__(self):
        self.config: Config | None = None
        self.auth: AuthManager | None = None
        self._format: str = "table"

    @property
    def format(self) -> str:
        return self._format

    @format.setter
    def format(self, value: str):
        self._format = value


pass_context = click.make_pass_decorator(AppContext, ensure=True)


# ─── Root CLI group ──────────────────────────────────────────────────────────

@click.group()
@click.option(
    "--format", "-f",
    type=click.Choice(["table", "json", "plain"], case_sensitive=False),
    default=None,
    help="Output format (overrides config).",
)
@click.option(
    "--config", "-c",
    type=click.Path(exists=False),
    default=None,
    help="Path to config file.",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output.")
@click.version_option(version=__version__, prog_name="icloud-cli")
@pass_context
def cli(ctx: AppContext, format: str | None, config: str | None, verbose: bool):
    """☁️  icloud-cli — Access iCloud services from Linux.

    Manage your Calendar, Reminders, Notes, and Find My devices
    right from the terminal.
    """
    config_path = Path(config) if config else None
    ctx.config = Config.load(config_path)
    ctx.config.ensure_dirs()

    if verbose:
        ctx.config.verbose = True

    ctx.format = format or ctx.config.default_format
    ctx.auth = AuthManager(ctx.config)


# ─── Auth commands ───────────────────────────────────────────────────────────

@cli.command()
@pass_context
def login(ctx: AppContext):
    """Log in to your iCloud account."""
    if ctx.auth.login():
        info("Use 'icloud-cli notes setup-imap' to enable Notes access.")


@cli.command()
@pass_context
def logout(ctx: AppContext):
    """Log out and clear stored credentials."""
    ctx.auth.logout()


@cli.command()
@pass_context
def status(ctx: AppContext):
    """Show authentication status."""
    data = ctx.auth.get_status()
    render_detail(data, format=ctx.format, title="Auth Status")


# ─── Calendar commands ───────────────────────────────────────────────────────

@cli.group()
def calendar():
    """📅 Manage iCloud Calendar events."""
    pass


@calendar.command("list")
@click.option("--from", "from_date", default=None, help="Start date (YYYY-MM-DD or 'today').")
@click.option("--to", "to_date", default=None, help="End date (YYYY-MM-DD or 'today').")
@pass_context
def calendar_list(ctx: AppContext, from_date: str | None, to_date: str | None):
    """List calendar events."""
    from icloud_cli.services.calendar import CalendarService

    service = CalendarService(ctx.auth.api, ctx.config)
    events = service.list_events(from_date, to_date)
    render(events, format=ctx.format, title="Calendar Events",
           columns=["title", "start", "end", "calendar", "location"])


@calendar.command("show")
@click.argument("event_id")
@pass_context
def calendar_show(ctx: AppContext, event_id: str):
    """Show details of a specific event."""
    from icloud_cli.services.calendar import CalendarService

    service = CalendarService(ctx.auth.api, ctx.config)
    event = service.get_event(event_id)
    if event:
        render_detail(event, format=ctx.format, title="Event Details")
    else:
        error(f"Event '{event_id}' not found.")


@calendar.command("add")
@click.option("--title", "-t", required=True, help="Event title.")
@click.option("--start", "-s", required=True, help="Start datetime (YYYY-MM-DD HH:MM).")
@click.option("--end", "-e", required=True, help="End datetime (YYYY-MM-DD HH:MM).")
@click.option("--calendar", "-c", "calendar_name", default=None, help="Calendar name.")
@click.option("--location", "-l", default=None, help="Event location.")
@click.option("--notes", "-n", default=None, help="Event notes/description.")
@pass_context
def calendar_add(
    ctx: AppContext,
    title: str,
    start: str,
    end: str,
    calendar_name: str | None,
    location: str | None,
    notes: str | None,
):
    """Add a new calendar event."""
    from icloud_cli.services.calendar import CalendarService

    service = CalendarService(ctx.auth.api, ctx.config)
    result = service.add_event(
        title=title,
        start=start,
        end=end,
        calendar_name=calendar_name,
        location=location,
        description=notes,
    )
    if result:
        success(f"Event '{title}' created.")
    else:
        error("Failed to create event.")


@calendar.command("delete")
@click.argument("event_id")
@pass_context
def calendar_delete(ctx: AppContext, event_id: str):
    """Delete a calendar event."""
    from icloud_cli.services.calendar import CalendarService

    service = CalendarService(ctx.auth.api, ctx.config)
    if service.delete_event(event_id):
        success(f"Event '{event_id}' deleted.")
    else:
        error(f"Failed to delete event '{event_id}'.")


# ─── Reminders commands ─────────────────────────────────────────────────────

@cli.group()
def reminders():
    """✅ Manage iCloud Reminders."""
    pass


@reminders.command("list")
@click.option("--list", "list_name", default=None, help="Filter by reminder list name.")
@click.option("--completed", is_flag=True, help="Include completed reminders.")
@pass_context
def reminders_list(ctx: AppContext, list_name: str | None, completed: bool):
    """List reminders."""
    from icloud_cli.services.reminders import RemindersService

    service = RemindersService(ctx.auth.api, ctx.config)
    items = service.list_reminders(list_name=list_name, show_completed=completed)
    render(items, format=ctx.format, title="Reminders",
           columns=["title", "list", "due_date", "priority", "completed"])


@reminders.command("add")
@click.option("--title", "-t", required=True, help="Reminder title.")
@click.option("--due", "-d", default=None, help="Due date (YYYY-MM-DD or YYYY-MM-DD HH:MM).")
@click.option("--list", "-l", "list_name", default=None, help="Reminder list name.")
@click.option("--description", default=None, help="Reminder description.")
@pass_context
def reminders_add(
    ctx: AppContext, title: str, due: str | None, list_name: str | None, description: str | None
):
    """Add a new reminder."""
    from icloud_cli.services.reminders import RemindersService

    service = RemindersService(ctx.auth.api, ctx.config)
    if service.add_reminder(title=title, due_date=due, list_name=list_name, description=description):
        success(f"Reminder '{title}' created.")
    else:
        error("Failed to create reminder.")


@reminders.command("complete")
@click.argument("reminder_id")
@pass_context
def reminders_complete(ctx: AppContext, reminder_id: str):
    """Mark a reminder as completed."""
    from icloud_cli.services.reminders import RemindersService

    service = RemindersService(ctx.auth.api, ctx.config)
    if service.complete_reminder(reminder_id):
        success(f"Reminder '{reminder_id}' marked as completed.")
    else:
        error(f"Failed to complete reminder '{reminder_id}'.")


@reminders.command("delete")
@click.argument("reminder_id")
@pass_context
def reminders_delete(ctx: AppContext, reminder_id: str):
    """Delete a reminder."""
    from icloud_cli.services.reminders import RemindersService

    service = RemindersService(ctx.auth.api, ctx.config)
    if service.delete_reminder(reminder_id):
        success(f"Reminder '{reminder_id}' deleted.")
    else:
        error(f"Failed to delete reminder '{reminder_id}'.")


# ─── Notes commands ──────────────────────────────────────────────────────────

@cli.group()
def notes():
    """📝 Manage iCloud Notes."""
    pass


@notes.command("setup-imap")
@pass_context
def notes_setup_imap(ctx: AppContext):
    """Set up app-specific password for Notes access."""
    ctx.auth.setup_imap_password()


@notes.command("list")
@click.option("--folder", "-f", default=None, help="Filter by folder name.")
@pass_context
def notes_list(ctx: AppContext, folder: str | None):
    """List notes."""
    from icloud_cli.services.notes import NotesService

    credentials = ctx.auth.get_imap_credentials()
    if not credentials:
        error("Notes not configured. Run 'icloud-cli notes setup-imap' first.")
        return

    service = NotesService(*credentials)
    items = service.list_notes(folder=folder)
    render(items, format=ctx.format, title="Notes",
           columns=["id", "subject", "date", "folder"])


@notes.command("show")
@click.argument("note_id")
@pass_context
def notes_show(ctx: AppContext, note_id: str):
    """Show a note's content."""
    from icloud_cli.services.notes import NotesService

    credentials = ctx.auth.get_imap_credentials()
    if not credentials:
        error("Notes not configured. Run 'icloud-cli notes setup-imap' first.")
        return

    service = NotesService(*credentials)
    note = service.get_note(note_id)
    if note:
        render_detail(note, format=ctx.format, title="Note")
    else:
        error(f"Note '{note_id}' not found.")


@notes.command("add")
@click.option("--title", "-t", required=True, help="Note title.")
@click.option("--body", "-b", required=True, help="Note body text.")
@click.option("--folder", "-f", default=None, help="Target folder.")
@pass_context
def notes_add(ctx: AppContext, title: str, body: str, folder: str | None):
    """Create a new note."""
    from icloud_cli.services.notes import NotesService

    credentials = ctx.auth.get_imap_credentials()
    if not credentials:
        error("Notes not configured. Run 'icloud-cli notes setup-imap' first.")
        return

    service = NotesService(*credentials)
    if service.add_note(title=title, body=body, folder=folder):
        success(f"Note '{title}' created.")
    else:
        error("Failed to create note.")


@notes.command("search")
@click.argument("query")
@pass_context
def notes_search(ctx: AppContext, query: str):
    """Search notes by keyword."""
    from icloud_cli.services.notes import NotesService

    credentials = ctx.auth.get_imap_credentials()
    if not credentials:
        error("Notes not configured. Run 'icloud-cli notes setup-imap' first.")
        return

    service = NotesService(*credentials)
    items = service.search_notes(query)
    render(items, format=ctx.format, title=f"Search: '{query}'",
           columns=["id", "subject", "date", "folder"])


# ─── Find My commands ────────────────────────────────────────────────────────

@cli.group()
def findmy():
    """📍 Find My devices."""
    pass


@findmy.command("list")
@pass_context
def findmy_list(ctx: AppContext):
    """List all devices."""
    from icloud_cli.services.findmy import FindMyService

    service = FindMyService(ctx.auth.api)
    devices = service.list_devices()
    render(devices, format=ctx.format, title="Find My Devices",
           columns=["name", "model", "battery", "status", "location"])


@findmy.command("locate")
@click.argument("device_name")
@pass_context
def findmy_locate(ctx: AppContext, device_name: str):
    """Get detailed location of a device."""
    from icloud_cli.services.findmy import FindMyService

    service = FindMyService(ctx.auth.api)
    location = service.locate_device(device_name)
    if location:
        render_detail(location, format=ctx.format, title=f"Location: {device_name}")
    else:
        error(f"Device '{device_name}' not found or location unavailable.")


@findmy.command("play-sound")
@click.argument("device_name")
@pass_context
def findmy_play_sound(ctx: AppContext, device_name: str):
    """Play a sound on a device."""
    from icloud_cli.services.findmy import FindMyService

    service = FindMyService(ctx.auth.api)
    if service.play_sound(device_name):
        success(f"Playing sound on '{device_name}'...")
    else:
        error(f"Device '{device_name}' not found.")


@findmy.command("lost-mode")
@click.argument("device_name")
@click.option("--phone", "-p", required=True, help="Contact phone number.")
@click.option("--message", "-m", default="This device has been lost.", help="Lock screen message.")
@pass_context
def findmy_lost_mode(ctx: AppContext, device_name: str, phone: str, message: str):
    """Activate Lost Mode on a device."""
    from icloud_cli.services.findmy import FindMyService

    service = FindMyService(ctx.auth.api)
    if service.lost_mode(device_name, phone=phone, message=message):
        success(f"Lost Mode activated on '{device_name}'.")
    else:
        error(f"Failed to activate Lost Mode on '{device_name}'.")


# ─── Sync / Daemon commands ─────────────────────────────────────────────────

@cli.command()
@pass_context
def sync(ctx: AppContext):
    """Run a one-shot sync of all services to local cache."""
    from icloud_cli.daemon import sync_all

    sync_all(ctx.auth, ctx.config)


@cli.group()
def daemon():
    """🔄 Background sync daemon."""
    pass


@daemon.command("start")
@pass_context
def daemon_start(ctx: AppContext):
    """Start the background sync daemon."""
    from icloud_cli.daemon import start_daemon

    start_daemon(ctx.auth, ctx.config)


@daemon.command("stop")
@pass_context
def daemon_stop(ctx: AppContext):
    """Stop the background sync daemon."""
    from icloud_cli.daemon import stop_daemon

    stop_daemon(ctx.config)


@daemon.command("status")
@pass_context
def daemon_status(ctx: AppContext):
    """Show daemon status."""
    from icloud_cli.daemon import get_daemon_status

    data = get_daemon_status(ctx.config)
    render_detail(data, format=ctx.format, title="Daemon Status")


# ─── Entry point ─────────────────────────────────────────────────────────────

def main():
    """Entry point wrapper."""
    cli()


if __name__ == "__main__":
    main()
