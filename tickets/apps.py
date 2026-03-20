"""
tickets/apps.py

Starts a background thread when Django starts.
The thread runs send_ticket_reminders every TICKET_REMINDER_CHECK_INTERVAL minutes.
No external scheduler needed — works on any device / OS.
"""

from django.apps import AppConfig


class TicketsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tickets'

    def ready(self):
        # Only start in the main process, not Django reloader child process
        import os
        if os.environ.get('RUN_MAIN') != 'true':
            return
        try:
            from .scheduler import start_reminder_scheduler
            start_reminder_scheduler()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to start reminder scheduler: {e}")