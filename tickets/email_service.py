"""
tickets/email_service.py

All emails sent via background thread (non-blocking).
Uses raw smtplib — no Django email backend — to avoid gunicorn worker timeouts.
"""

from django.template.loader import render_to_string
from django.conf import settings
from django.contrib.auth import get_user_model
import logging
import threading
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)
User = get_user_model()


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _get_admin_emails():
    admin_emails = getattr(settings, 'MALLDESK_ADMIN_EMAILS', None)
    if admin_emails:
        return list(admin_emails)
    return list(User.objects.filter(role=User.ADMIN, is_active=True).values_list('email', flat=True))


def _get_cc_emails():
    return list(getattr(settings, 'MALLDESK_CC_EMAILS', []))


def _get_ticket_creator_email(ticket):
    if ticket.created_by and ticket.created_by.email:
        return ticket.created_by.email
    return None


def _build_cc(ticket):
    cc = list(_get_cc_emails())
    creator = _get_ticket_creator_email(ticket)
    if creator:
        cc.append(creator)
    return list(set(filter(None, cc)))


def _get_department_managers(department):
    return User.objects.filter(
        department=department,
        role__in=[User.MANAGER, User.ADMIN],
        is_active=True,
    )


# ── CORE SMTP SEND ────────────────────────────────────────────────────────────

def _smtp_send(subject, text_body, html_body, to_list, cc_list, bcc_list):
    """
    Raw smtplib send — completely bypasses Django email backend.
    Tries port 587 (STARTTLS) first, falls back to 465 (SSL).
    Called inside a daemon thread.
    """
    # Close any Django DB connections inherited from parent thread
    # This prevents 'connection already closed' errors in threads
    try:
        from django.db import connections
        connections.close_all()
    except Exception:
        pass

    host      = settings.EMAIL_HOST
    port      = getattr(settings, 'EMAIL_PORT', 587)
    user      = settings.EMAIL_HOST_USER
    password  = settings.EMAIL_HOST_PASSWORD
    from_addr = settings.DEFAULT_FROM_EMAIL

    all_recipients = list(set(filter(None, to_list + cc_list + bcc_list)))

    if not all_recipients:
        logger.warning(f"[EMAIL] No recipients — skipping: {subject}")
        return

    # Build MIME message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = from_addr
    msg['To']      = ', '.join(to_list)
    if cc_list:
        msg['Cc']  = ', '.join(cc_list)
    msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
    if html_body:
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    # SSL context — bypass hostname verification (DreamHost cert mismatch)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE

    last_error = None

    # Try 587 STARTTLS
    try:
        with smtplib.SMTP(host, 587, timeout=25) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ctx)
            smtp.ehlo()
            smtp.login(user, password)
            smtp.sendmail(from_addr, all_recipients, msg.as_bytes())
            logger.info(f"[EMAIL OK 587] TO:{to_list} | {subject}")
            return
    except Exception as e:
        last_error = e
        logger.warning(f"[EMAIL] Port 587 failed: {e}")

    # Fallback: 465 SSL
    try:
        with smtplib.SMTP_SSL(host, 465, context=ctx, timeout=25) as smtp:
            smtp.login(user, password)
            smtp.sendmail(from_addr, all_recipients, msg.as_bytes())
            logger.info(f"[EMAIL OK 465] TO:{to_list} | {subject}")
            return
    except Exception as e:
        logger.error(f"[EMAIL FAILED] {subject} | 587 err: {last_error} | 465 err: {e}")


def _send(subject, text_body, html_body, to_list, cc_list=None):
    """
    Public send function — fires email in background thread immediately.
    Returns instantly so the request is never blocked.
    """
    to_list  = [e for e in (to_list  or []) if e]
    cc_list  = [e for e in (cc_list  or []) if e]
    bcc_list = [e for e in _get_admin_emails() if e]

    # Deduplicate
    all_to  = set(to_list)
    cc_list  = [e for e in cc_list  if e not in all_to]
    bcc_list = [e for e in bcc_list if e not in all_to and e not in set(cc_list)]

    if not to_list:
        logger.warning(f"[EMAIL] Skipped — no TO: {subject}")
        return

    logger.info(f"[EMAIL QUEUED] TO:{to_list} CC:{cc_list} BCC:{bcc_list} | {subject}")

    thread = threading.Thread(
        target=_smtp_send,
        args=(subject, text_body, html_body, to_list, cc_list, bcc_list),
        daemon=True,
        name=f"email-{subject[:30]}",
    )
    thread.start()


# ── 1. TICKET CREATED ─────────────────────────────────────────────────────────

def notify_ticket_created(ticket):
    context = {'ticket': ticket}
    cc = _build_cc(ticket)

    # To customer
    if ticket.created_by and ticket.created_by.email:
        subject = f"[MallDesk] Ticket {ticket.ticket_id} Received — {ticket.mall.name}"
        try:
            html = render_to_string('emails/ticket_created_customer.html', context)
        except Exception as e:
            html = None
            logger.error(f"Template error ticket_created_customer: {e}")
        text = (
            f"Dear {ticket.complainant_name},\n\n"
            f"Your ticket {ticket.ticket_id} has been received.\n"
            f"Type    : {ticket.get_ticket_type_display()}\n"
            f"Priority: {ticket.get_priority_display()}\n"
            f"Dept    : {ticket.department.name}\n"
            f"Due Date: {ticket.due_date or 'TBD'}\n\n"
            f"We will keep you updated.\n\n— MallDesk Support"
        )
        cc_no_creator = [e for e in cc if e != ticket.created_by.email]
        _send(subject, text, html, [ticket.created_by.email], cc_list=cc_no_creator)

    # To managers
    managers = _get_department_managers(ticket.department)
    if managers.exists():
        subject = f"[MallDesk] New {ticket.get_priority_display()} Ticket — {ticket.ticket_id}"
        try:
            html = render_to_string('emails/ticket_created_manager.html', context)
        except Exception as e:
            html = None
            logger.error(f"Template error ticket_created_manager: {e}")
        text = (
            f"New ticket submitted.\n\n"
            f"ID         : {ticket.ticket_id}\n"
            f"Complainant: {ticket.complainant_name} ({ticket.complainant_company})\n"
            f"Mall       : {ticket.mall.name}\n"
            f"Department : {ticket.department.name}\n"
            f"Priority   : {ticket.get_priority_display()}\n"
            f"Due Date   : {ticket.due_date or 'Not set'}\n\n"
            f"Description:\n{ticket.complaint_description}\n\n— MallDesk System"
        )
        _send(subject, text, html, list(managers.values_list('email', flat=True)), cc_list=cc)


# ── 2. TICKET ASSIGNED ────────────────────────────────────────────────────────

def notify_ticket_assigned(ticket):
    if not ticket.assigned_to:
        return
    context = {'ticket': ticket}
    cc = _build_cc(ticket)

    # To assignee
    subject = f"[MallDesk] Ticket {ticket.ticket_id} Assigned to You"
    try:
        html = render_to_string('emails/ticket_assigned_internal.html', context)
    except Exception as e:
        html = None
        logger.error(f"Template error ticket_assigned_internal: {e}")
    text = (
        f"Dear {ticket.assigned_to.full_name},\n\n"
        f"Ticket {ticket.ticket_id} has been assigned to you.\n\n"
        f"Complainant: {ticket.complainant_name}\n"
        f"Mall       : {ticket.mall.name}\n"
        f"Priority   : {ticket.get_priority_display()}\n"
        f"Due Date   : {ticket.due_date or 'ASAP'}\n\n"
        f"Issue:\n{ticket.complaint_description}\n\n— MallDesk System"
    )
    _send(subject, text, html, [ticket.assigned_to.email], cc_list=cc)

    # To customer
    if ticket.created_by and ticket.created_by.email:
        subject = f"[MallDesk] Your Ticket {ticket.ticket_id} is Now In Progress"
        try:
            html = render_to_string('emails/ticket_assigned_customer.html', context)
        except Exception as e:
            html = None
            logger.error(f"Template error ticket_assigned_customer: {e}")
        text = (
            f"Dear {ticket.complainant_name},\n\n"
            f"Ticket {ticket.ticket_id} is now In Progress.\n"
            f"Assigned to: {ticket.assigned_to.full_name} ({ticket.department.name})\n\n"
            f"We will notify you once resolved.\n\n— MallDesk Support"
        )
        cc_no_creator = [e for e in cc if e != ticket.created_by.email]
        _send(subject, text, html, [ticket.created_by.email], cc_list=cc_no_creator)


# ── 3. TICKET UPDATED ─────────────────────────────────────────────────────────

def notify_ticket_updated(ticket, update):
    context = {'ticket': ticket, 'update': update}
    cc = _build_cc(ticket)

    new_status_label = update.new_status.replace('_', ' ').title() if update.new_status else 'Note Added'

    # To customer
    if ticket.created_by and ticket.created_by.email:
        subject = f"[MallDesk] Update on Ticket {ticket.ticket_id} — {new_status_label}"
        try:
            html = render_to_string('emails/ticket_updated_customer.html', context)
        except Exception as e:
            html = None
            logger.error(f"Template error ticket_updated_customer: {e}")
        text = f"Dear {ticket.complainant_name},\n\nUpdate on ticket {ticket.ticket_id}.\n\n"
        if update.old_status and update.new_status:
            text += f"Status: {update.old_status.replace('_',' ').title()} → {new_status_label}\n\n"
        text += f"Note: {update.note}\n\n— MallDesk Support"
        cc_no_creator = [e for e in cc if e != ticket.created_by.email]
        _send(subject, text, html, [ticket.created_by.email], cc_list=cc_no_creator)

    # To managers
    managers = _get_department_managers(ticket.department)
    if managers.exists():
        subject = f"[MallDesk] Ticket {ticket.ticket_id} Updated — {new_status_label}"
        try:
            html = render_to_string('emails/ticket_updated_manager.html', context)
        except Exception as e:
            html = None
            logger.error(f"Template error ticket_updated_manager: {e}")
        text = (
            f"Ticket {ticket.ticket_id} updated.\n"
            f"By    : {update.updated_by.full_name if update.updated_by else 'System'}\n"
            f"Status: {update.old_status or '—'} → {update.new_status or '(no change)'}\n"
            f"Note  : {update.note}\n— MallDesk System"
        )
        _send(subject, text, html, list(managers.values_list('email', flat=True)), cc_list=cc)


# ── 4. TICKET RESOLVED ────────────────────────────────────────────────────────

def notify_ticket_resolved(ticket):
    context = {'ticket': ticket}
    cc = _build_cc(ticket)

    # To customer
    if ticket.created_by and ticket.created_by.email:
        subject = f"[MallDesk] Ticket {ticket.ticket_id} Resolved"
        try:
            html = render_to_string('emails/ticket_resolved_customer.html', context)
        except Exception as e:
            html = None
            logger.error(f"Template error ticket_resolved_customer: {e}")
        text = (
            f"Dear {ticket.complainant_name},\n\n"
            f"Ticket {ticket.ticket_id} has been resolved.\n\n"
            f"Resolution : {ticket.resolution}\n"
            f"Resolved by: {ticket.assigned_to.full_name if ticket.assigned_to else 'Our team'}\n"
            f"Time taken : {ticket.resolution_time} hours\n\n— MallDesk Support"
        )
        cc_no_creator = [e for e in cc if e != ticket.created_by.email]
        _send(subject, text, html, [ticket.created_by.email], cc_list=cc_no_creator)

    # To managers
    managers = _get_department_managers(ticket.department)
    if managers.exists():
        subject = f"[MallDesk] Ticket {ticket.ticket_id} Resolved in {ticket.resolution_time}h"
        try:
            html = render_to_string('emails/ticket_resolved_manager.html', context)
        except Exception as e:
            html = None
            logger.error(f"Template error ticket_resolved_manager: {e}")
        text = (
            f"Ticket {ticket.ticket_id} resolved.\n"
            f"Complainant: {ticket.complainant_name}\n"
            f"Resolved by: {ticket.assigned_to.full_name if ticket.assigned_to else 'N/A'}\n"
            f"Time taken : {ticket.resolution_time} hours\n"
            f"Resolution : {ticket.resolution}"
        )
        _send(subject, text, html, list(managers.values_list('email', flat=True)), cc_list=cc)