"""
tickets/management/commands/send_ticket_reminders.py

Reminder logic:
  - Ticket is created and assigned
  - But status is STILL 'open' after TICKET_REMINDER_HOURS (default 2)
  - → Send reminder to manager + assigned user

Run manually:   python manage.py send_ticket_reminders
Run with test:  python manage.py send_ticket_reminders --hours 0.1 --dry-run
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.template.loader import render_to_string
from django.conf import settings
from datetime import timedelta
from tickets.models import Ticket, TicketUpdate
from tickets.email_service import _send, _get_department_managers
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send reminders for assigned tickets still in Open status after configured hours'

    def add_arguments(self, parser):
        parser.add_argument('--hours', type=float, default=None)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        hours     = options['hours'] or getattr(settings, 'TICKET_REMINDER_HOURS', 2)
        max_rem   = getattr(settings, 'TICKET_REMINDER_MAX', 5)
        dry_run   = options['dry_run']
        now       = timezone.now()
        cutoff    = now - timedelta(hours=hours)

        self.stdout.write(f"\n{'[DRY RUN] ' if dry_run else ''}Checking tickets assigned but still Open for {hours}+ hours...\n")

        # Only tickets that:
        # 1. Are still OPEN status
        # 2. Have been assigned to someone
        # 3. Were created more than {hours} ago
        # Remind on OPEN and IN_PROGRESS — until ticket is fully Resolved or Closed
        stale = Ticket.objects.filter(
            ticket_status__in=[Ticket.OPEN, Ticket.IN_PROGRESS],
            assigned_to__isnull=False,
            created_at__lte=cutoff,
        ).select_related('mall', 'department', 'created_by', 'assigned_to')

        if not stale.exists():
            self.stdout.write(self.style.SUCCESS('✓ No stale open tickets found.'))
            return

        sent = 0
        for ticket in stale:
            # Count reminders already sent for this ticket
            reminder_count = ticket.updates.filter(note__startswith='[REMINDER]').count()

            if reminder_count >= max_rem:
                self.stdout.write(f"  SKIP {ticket.ticket_id} — max reminders ({max_rem}) reached")
                continue

            hours_open = round((now - ticket.created_at).total_seconds() / 3600, 1)

            self.stdout.write(
                f"  → {ticket.ticket_id} | Assigned to: {ticket.assigned_to.full_name} | "
                f"Open for: {hours_open}h | Reminders sent: {reminder_count}"
            )

            if dry_run:
                continue

            context = {
                'ticket': ticket,
                'hours_open': hours_open,
                'reminder_num': reminder_count + 1,
            }

            # ── Remind assigned internal user ────────────
            subject = f"[MallDesk] ⚠ Reminder #{reminder_count+1} — Ticket {ticket.ticket_id} Still Open ({hours_open}h)"
            try:
                html = render_to_string('emails/ticket_reminder_assignee.html', context)
            except Exception:
                html = None
            text = (
                f"Dear {ticket.assigned_to.full_name},\n\n"
                f"Ticket {ticket.ticket_id} was assigned to you {hours_open} hours ago "
                f"but is still in OPEN status.\n\n"
                f"Complainant : {ticket.complainant_name}\n"
                f"Mall        : {ticket.mall.name}\n"
                f"Priority    : {ticket.get_priority_display()}\n"
                f"Due Date    : {ticket.due_date or 'Not set'}\n\n"
                f"Please update the ticket status.\n\n— MallDesk Automated Reminder"
            )
            _send(subject, text, html, [ticket.assigned_to.email])

            # ── Remind department managers ───────────────
            managers = _get_department_managers(ticket.department)
            if managers.exists():
                subject = f"[MallDesk] ⚠ Reminder — Ticket {ticket.ticket_id} Assigned but Still Open ({hours_open}h)"
                try:
                    html = render_to_string('emails/ticket_reminder_manager.html', context)
                except Exception:
                    html = None
                text = (
                    f"Ticket {ticket.ticket_id} was assigned {hours_open} hours ago "
                    f"but status has not been updated from OPEN.\n\n"
                    f"Complainant : {ticket.complainant_name}\n"
                    f"Assigned To : {ticket.assigned_to.full_name}\n"
                    f"Mall        : {ticket.mall.name}\n"
                    f"Priority    : {ticket.get_priority_display()}\n\n"
                    f"— MallDesk Automated Reminder"
                )
                _send(subject, text, html, list(managers.values_list('email', flat=True)))

            # ── Log reminder in ticket timeline ──────────
            TicketUpdate.objects.create(
                ticket=ticket,
                updated_by=None,
                note=f"[REMINDER] Automated reminder #{reminder_count+1} sent — ticket open for {hours_open} hours.",
            )

            sent += 1
            self.stdout.write(self.style.SUCCESS(f"     ✓ Reminder #{reminder_count+1} sent"))

        self.stdout.write(self.style.SUCCESS(f"\n✓ Done. {sent} reminder(s) sent."))