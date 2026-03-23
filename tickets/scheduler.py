"""
tickets/scheduler.py

Sends reminder emails for tickets that are Open or In Progress
beyond TICKET_REMINDER_HOURS without being resolved.
Runs as a daemon thread — starts automatically with Django.
"""

import threading
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def run_reminders():
    """Check for stale tickets and send reminder emails."""
    try:
        # Always close inherited DB connections at start of thread
        from django.db import connections
        connections.close_all()

        from django.utils import timezone
        from datetime import timedelta
        from tickets.models import Ticket, TicketUpdate
        from tickets.email_service import _send, _get_department_managers
        from django.template.loader import render_to_string

        hours   = getattr(settings, 'TICKET_REMINDER_HOURS', 2)
        max_rem = getattr(settings, 'TICKET_REMINDER_MAX', 5)
        now     = timezone.now()
        cutoff  = now - timedelta(hours=hours)

        # Tickets: Open or In Progress + assigned + older than cutoff
        stale = Ticket.objects.filter(
            ticket_status__in=[Ticket.OPEN, Ticket.IN_PROGRESS],
            assigned_to__isnull=False,
            created_at__lte=cutoff,
        ).select_related('mall', 'department', 'created_by', 'assigned_to')

        if not stale.exists():
            logger.info("[REMINDER] No stale tickets found.")
            return

        for ticket in stale:
            reminder_count = ticket.updates.filter(note__startswith='[REMINDER]').count()

            if reminder_count >= max_rem:
                logger.info(f"[REMINDER] {ticket.ticket_id} — max reminders reached, skipping.")
                continue

            hours_open = round((now - ticket.created_at).total_seconds() / 3600, 1)
            context = {
                'ticket':      ticket,
                'hours_open':  hours_open,
                'reminder_num': reminder_count + 1,
            }

            # To assigned user
            try:
                html = render_to_string('emails/ticket_reminder_assignee.html', context)
            except Exception:
                html = None
            subject = f"[MallDesk] Reminder #{reminder_count+1} — Ticket {ticket.ticket_id} Still {ticket.get_ticket_status_display()} ({hours_open}h)"
            text = (
                f"Dear {ticket.assigned_to.full_name},\n\n"
                f"Ticket {ticket.ticket_id} has been {ticket.get_ticket_status_display().lower()} "
                f"for {hours_open} hours without resolution.\n\n"
                f"Complainant: {ticket.complainant_name}\n"
                f"Mall       : {ticket.mall.name}\n"
                f"Priority   : {ticket.get_priority_display()}\n"
                f"Due Date   : {ticket.due_date or 'Not set'}\n\n"
                f"Please update or resolve this ticket.\n\n— MallDesk Automated Reminder"
            )
            _send(subject, text, html, [ticket.assigned_to.email])

            # To managers
            managers = _get_department_managers(ticket.department)
            if managers.exists():
                try:
                    html_mgr = render_to_string('emails/ticket_reminder_manager.html', context)
                except Exception:
                    html_mgr = None
                subject_mgr = f"[MallDesk] Reminder — Ticket {ticket.ticket_id} Unresolved for {hours_open}h"
                text_mgr = (
                    f"Ticket {ticket.ticket_id} assigned to {ticket.assigned_to.full_name} "
                    f"is still {ticket.get_ticket_status_display().lower()} after {hours_open} hours.\n\n"
                    f"Complainant: {ticket.complainant_name}\n"
                    f"Mall       : {ticket.mall.name}\n"
                    f"Priority   : {ticket.get_priority_display()}\n\n— MallDesk Automated Reminder"
                )
                _send(subject_mgr, text_mgr, html_mgr, list(managers.values_list('email', flat=True)))

            # Log reminder in ticket timeline
            TicketUpdate.objects.create(
                ticket=ticket,
                updated_by=None,
                note=f"[REMINDER] Automated reminder #{reminder_count+1} — ticket open for {hours_open} hours.",
            )
            logger.info(f"[REMINDER] Sent reminder #{reminder_count+1} for {ticket.ticket_id} ({hours_open}h open)")

    except Exception as e:
        logger.error(f"[REMINDER] Scheduler error: {e}", exc_info=True)
    finally:
        # Always close DB connections after thread work
        try:
            from django.db import connections
            connections.close_all()
        except Exception:
            pass


def _loop(interval_seconds):
    """Runs run_reminders() every interval_seconds forever."""
    import time
    logger.info(f"[REMINDER] Scheduler started — interval: {interval_seconds//60}min")
    while True:
        time.sleep(interval_seconds)
        logger.info("[REMINDER] Running check...")
        run_reminders()


def start_reminder_scheduler():
    interval = getattr(settings, 'TICKET_REMINDER_CHECK_INTERVAL', 30) * 60
    t = threading.Thread(target=_loop, args=(interval,), daemon=True, name='ReminderScheduler')
    t.start()
    logger.info(f"[REMINDER] Thread started — checks every {interval//60}min, threshold: {getattr(settings,'TICKET_REMINDER_HOURS',2)}h")