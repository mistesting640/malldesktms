"""
tickets/scheduler.py

Background thread that periodically checks for open tickets
that have been assigned but not updated, and sends reminder emails.

Settings:
    TICKET_REMINDER_HOURS            = 2    # hours after which to send reminder
    TICKET_REMINDER_CHECK_INTERVAL   = 30   # how often (minutes) to check (default 30 min)
    TICKET_REMINDER_MAX              = 5    # max reminders per ticket

How it works:
    1. Django starts → TicketsConfig.ready() → start_reminder_scheduler()
    2. A daemon thread starts, running every TICKET_REMINDER_CHECK_INTERVAL minutes
    3. Each run: finds tickets that are OPEN + ASSIGNED + created > REMINDER_HOURS ago
    4. Sends reminder email to assigned user + manager
    5. Logs [REMINDER] in ticket timeline to track count and prevent spam
"""

import threading
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def run_reminders():
    """Core reminder logic — called by scheduler thread."""
    try:
        from django.utils import timezone
        from datetime import timedelta
        from tickets.models import Ticket, TicketUpdate
        from tickets.email_service import _send, _get_department_managers
        from django.template.loader import render_to_string

        hours   = getattr(settings, 'TICKET_REMINDER_HOURS', 2)
        max_rem = getattr(settings, 'TICKET_REMINDER_MAX', 5)
        now     = timezone.now()
        cutoff  = now - timedelta(hours=hours)

        # Tickets that are:
        # - Still OPEN status
        # - Already assigned to someone
        # - Were created more than {hours} ago (so they've had time)
        # Remind on OPEN and IN_PROGRESS — until ticket is fully Resolved or Closed
        stale_tickets = Ticket.objects.filter(
            ticket_status__in=[Ticket.OPEN, Ticket.IN_PROGRESS],
            assigned_to__isnull=False,
            created_at__lte=cutoff,
        ).select_related('mall', 'department', 'created_by', 'assigned_to')

        if not stale_tickets.exists():
            logger.info("Reminder check: No stale open tickets found.")
            return

        for ticket in stale_tickets:
            # How many reminders already sent for this ticket
            reminder_count = ticket.updates.filter(note__startswith='[REMINDER]').count()

            # Stop after max reminders to avoid inbox spam
            if reminder_count >= max_rem:
                continue

            hours_open = round((now - ticket.created_at).total_seconds() / 3600, 1)
            context = {
                'ticket':      ticket,
                'hours_open':  hours_open,
                'reminder_num': reminder_count + 1,
            }

            # ── Email to assigned internal user ──────────
            try:
                html = render_to_string('emails/ticket_reminder_assignee.html', context)
            except Exception:
                html = None

            subject = (
                f"[MallDesk] ⚠ Reminder #{reminder_count+1} — "
                f"Ticket {ticket.ticket_id} Still Open ({hours_open}h)"
            )
            text = (
                f"Dear {ticket.assigned_to.full_name},\n\n"
                f"Ticket {ticket.ticket_id} was assigned to you {hours_open} hours ago "
                f"but is still OPEN.\n\n"
                f"Complainant : {ticket.complainant_name}\n"
                f"Mall        : {ticket.mall.name}\n"
                f"Priority    : {ticket.get_priority_display()}\n"
                f"Due Date    : {ticket.due_date or 'Not set'}\n\n"
                f"Please update the ticket status.\n\n— MallDesk Automated Reminder"
            )
            _send(subject, text, html, [ticket.assigned_to.email])

            # ── Email to department managers ─────────────
            managers = _get_department_managers(ticket.department)
            if managers.exists():
                try:
                    html_mgr = render_to_string('emails/ticket_reminder_manager.html', context)
                except Exception:
                    html_mgr = None
                subject_mgr = (
                    f"[MallDesk] ⚠ Reminder — Ticket {ticket.ticket_id} "
                    f"Assigned but Still Open ({hours_open}h)"
                )
                text_mgr = (
                    f"Ticket {ticket.ticket_id} was assigned {hours_open} hours ago "
                    f"but status is still OPEN.\n\n"
                    f"Complainant : {ticket.complainant_name}\n"
                    f"Assigned To : {ticket.assigned_to.full_name}\n"
                    f"Mall        : {ticket.mall.name}\n"
                    f"Priority    : {ticket.get_priority_display()}\n\n"
                    f"— MallDesk Automated Reminder"
                )
                _send(subject_mgr, text_mgr, html_mgr,
                      list(managers.values_list('email', flat=True)))

            # ── Log in ticket timeline ───────────────────
            TicketUpdate.objects.create(
                ticket=ticket,
                updated_by=None,
                note=(
                    f"[REMINDER] Automated reminder #{reminder_count+1} sent — "
                    f"ticket has been open for {hours_open} hours."
                ),
            )

            logger.info(
                f"Reminder #{reminder_count+1} sent for {ticket.ticket_id} "
                f"(open {hours_open}h, assigned to {ticket.assigned_to.full_name})"
            )

    except Exception as e:
        logger.error(f"Reminder scheduler error: {e}", exc_info=True)


def _scheduler_loop(interval_seconds):
    """Runs run_reminders() every interval_seconds in a loop."""
    import time
    logger.info(f"Reminder scheduler started — checking every {interval_seconds//60} minutes.")
    while True:
        time.sleep(interval_seconds)
        logger.info("Running reminder check...")
        run_reminders()


def start_reminder_scheduler():
    """
    Starts the background reminder thread.
    Called once from TicketsConfig.ready() when Django starts.
    """
    interval_minutes = getattr(settings, 'TICKET_REMINDER_CHECK_INTERVAL', 30)
    interval_seconds = interval_minutes * 60

    thread = threading.Thread(
        target=_scheduler_loop,
        args=(interval_seconds,),
        daemon=True,   # daemon=True means thread dies when Django stops
        name='TicketReminderScheduler',
    )
    thread.start()
    logger.info(
        f"TicketReminderScheduler thread started. "
        f"Will check every {interval_minutes} min. "
        f"Reminder threshold: {getattr(settings, 'TICKET_REMINDER_HOURS', 2)}h."
    )