from django.apps import AppConfig
import logging
import os

logger = logging.getLogger(__name__)


class TicketsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tickets'

    def ready(self):
        print("=" * 60)
        print("[MALLDESK] TicketsConfig.ready() called")
        print(f"[MALLDESK] RUN_MAIN={os.environ.get('RUN_MAIN')}")
        print(f"[MALLDESK] SERVER_SOFTWARE={os.environ.get('SERVER_SOFTWARE')}")
        print(f"[MALLDESK] RAILWAY_ENVIRONMENT={os.environ.get('RAILWAY_ENVIRONMENT')}")
        print("=" * 60)

        # Always try to start — let the scheduler handle any errors
        try:
            from .scheduler import start_reminder_scheduler
            start_reminder_scheduler()
            print("[MALLDESK] Reminder scheduler started OK")
        except Exception as e:
            print(f"[MALLDESK] Scheduler FAILED: {e}")