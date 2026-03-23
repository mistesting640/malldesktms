from django.apps import AppConfig


class TicketsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tickets'

    def ready(self):
        import os
        # Skip in manage.py commands like migrate, collectstatic etc
        # but always start in gunicorn (production) and runserver (dev)
        run_main = os.environ.get('RUN_MAIN')
        server_software = os.environ.get('SERVER_SOFTWARE', '')

        is_gunicorn   = 'gunicorn' in server_software.lower()
        is_dev_server = run_main == 'true'
        is_railway    = os.environ.get('RAILWAY_ENVIRONMENT') is not None

        if is_gunicorn or is_dev_server or is_railway:
            try:
                from .scheduler import start_reminder_scheduler
                start_reminder_scheduler()
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Scheduler failed to start: {e}")