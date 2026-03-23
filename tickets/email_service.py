"""
tickets/email_service.py
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


def _smtp_send(subject, text_body, html_body, to_list, cc_list, bcc_list):
    """Actual SMTP send in background thread."""
    print(f"\n[EMAIL THREAD START] Subject: {subject}")
    print(f"[EMAIL THREAD] TO:{to_list} CC:{cc_list} BCC:{bcc_list}")

    # Close DB connections inherited from parent thread
    try:
        from django.db import connections
        connections.close_all()
    except Exception as ex:
        print(f"[EMAIL THREAD] DB close warning: {ex}")

    host      = settings.EMAIL_HOST
    user      = settings.EMAIL_HOST_USER
    password  = settings.EMAIL_HOST_PASSWORD
    from_addr = settings.DEFAULT_FROM_EMAIL

    print(f"[EMAIL THREAD] HOST:{host} USER:{user}")

    all_recipients = list(set(filter(None, to_list + cc_list + bcc_list)))

    if not all_recipients:
        print("[EMAIL THREAD] No recipients — aborting")
        return

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = from_addr
    msg['To']      = ', '.join(to_list)
    if cc_list:
        msg['Cc']  = ', '.join(cc_list)
    msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
    if html_body:
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE

    # Try 587 STARTTLS
    try:
        print(f"[EMAIL THREAD] Trying port 587...")
        with smtplib.SMTP(host, 587, timeout=25) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ctx)
            smtp.ehlo()
            smtp.login(user, password)
            smtp.sendmail(from_addr, all_recipients, msg.as_bytes())
            print(f"[EMAIL THREAD] SUCCESS port 587 — sent to {all_recipients}")
            return
    except Exception as e:
        print(f"[EMAIL THREAD] Port 587 FAILED: {e}")

    # Try 465 SSL
    try:
        print(f"[EMAIL THREAD] Trying port 465...")
        with smtplib.SMTP_SSL(host, 465, context=ctx, timeout=25) as smtp:
            smtp.login(user, password)
            smtp.sendmail(from_addr, all_recipients, msg.as_bytes())
            print(f"[EMAIL THREAD] SUCCESS port 465 — sent to {all_recipients}")
            return
    except Exception as e:
        print(f"[EMAIL THREAD] Port 465 FAILED: {e}")
        print(f"[EMAIL THREAD] BOTH PORTS FAILED — email NOT sent")

    try:
        from django.db import connections
        connections.close_all()
    except Exception:
        pass


def _send(subject, text_body, html_body, to_list, cc_list=None):
    to_list  = [e for e in (to_list  or []) if e]
    cc_list  = [e for e in (cc_list  or []) if e]
    bcc_list = [e for e in _get_admin_emails() if e]

    all_to   = set(to_list)
    cc_list  = [e for e in cc_list  if e not in all_to]
    bcc_list = [e for e in bcc_list if e not in all_to and e not in set(cc_list)]

    if not to_list:
        print(f"[EMAIL] Skipped — no TO: {subject}")
        return

    print(f"[EMAIL] Queuing background thread for: {subject}")
    thread = threading.Thread(
        target=_smtp_send,
        args=(subject, text_body, html_body, to_list, cc_list, bcc_list),
        daemon=True,
        name=f"email-{subject[:20]}",
    )
    thread.start()
    print(f"[EMAIL] Thread started: {thread.name}")


def notify_ticket_created(ticket):
    print(f"[EMAIL] notify_ticket_created called for {ticket.ticket_id}")
    context = {'ticket': ticket}
    cc = _build_cc(ticket)

    if ticket.created_by and ticket.created_by.email:
        subject = f"[MallDesk] Ticket {ticket.ticket_id} Received — {ticket.mall.name}"
        try:
            html = render_to_string('emails/ticket_created_customer.html', context)
        except Exception as e:
            html = None
            print(f"[EMAIL] Template error: {e}")
        text = (
            f"Dear {ticket.complainant_name},\n\n"
            f"Your ticket {ticket.ticket_id} has been received.\n"
            f"Priority: {ticket.get_priority_display()}\n"
            f"Dept    : {ticket.department.name}\n"
            f"Due Date: {ticket.due_date or 'TBD'}\n\n"
            f"We will keep you updated.\n\n— MallDesk Support"
        )
        cc_no_creator = [e for e in cc if e != ticket.created_by.email]
        _send(subject, text, html, [ticket.created_by.email], cc_list=cc_no_creator)

    managers = _get_department_managers(ticket.department)
    if managers.exists():
        subject = f"[MallDesk] New {ticket.get_priority_display()} Ticket — {ticket.ticket_id}"
        try:
            html = render_to_string('emails/ticket_created_manager.html', context)
        except Exception as e:
            html = None
            print(f"[EMAIL] Template error: {e}")
        text = (
            f"New ticket submitted.\n\n"
            f"ID         : {ticket.ticket_id}\n"
            f"Complainant: {ticket.complainant_name}\n"
            f"Mall       : {ticket.mall.name}\n"
            f"Priority   : {ticket.get_priority_display()}\n\n"
            f"Description:\n{ticket.complaint_description}\n\n— MallDesk System"
        )
        _send(subject, text, html, list(managers.values_list('email', flat=True)), cc_list=cc)


def notify_ticket_assigned(ticket):
    if not ticket.assigned_to:
        return
    print(f"[EMAIL] notify_ticket_assigned called for {ticket.ticket_id}")
    context = {'ticket': ticket}
    cc = _build_cc(ticket)

    subject = f"[MallDesk] Ticket {ticket.ticket_id} Assigned to You"
    try:
        html = render_to_string('emails/ticket_assigned_internal.html', context)
    except Exception as e:
        html = None
        print(f"[EMAIL] Template error: {e}")
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

    if ticket.created_by and ticket.created_by.email:
        subject = f"[MallDesk] Your Ticket {ticket.ticket_id} is Now In Progress"
        try:
            html = render_to_string('emails/ticket_assigned_customer.html', context)
        except Exception as e:
            html = None
            print(f"[EMAIL] Template error: {e}")
        text = (
            f"Dear {ticket.complainant_name},\n\n"
            f"Ticket {ticket.ticket_id} is now In Progress.\n"
            f"Assigned to: {ticket.assigned_to.full_name}\n\n"
            f"We will notify you once resolved.\n\n— MallDesk Support"
        )
        cc_no_creator = [e for e in cc if e != ticket.created_by.email]
        _send(subject, text, html, [ticket.created_by.email], cc_list=cc_no_creator)


def notify_ticket_updated(ticket, update):
    print(f"[EMAIL] notify_ticket_updated called for {ticket.ticket_id}")
    context = {'ticket': ticket, 'update': update}
    cc = _build_cc(ticket)
    new_status_label = update.new_status.replace('_', ' ').title() if update.new_status else 'Note Added'

    if ticket.created_by and ticket.created_by.email:
        subject = f"[MallDesk] Update on Ticket {ticket.ticket_id} — {new_status_label}"
        try:
            html = render_to_string('emails/ticket_updated_customer.html', context)
        except Exception as e:
            html = None
            print(f"[EMAIL] Template error: {e}")
        text = f"Dear {ticket.complainant_name},\n\nUpdate on ticket {ticket.ticket_id}.\n\n"
        if update.old_status and update.new_status:
            text += f"Status: {update.old_status.replace('_',' ').title()} → {new_status_label}\n\n"
        text += f"Note: {update.note}\n\n— MallDesk Support"
        cc_no_creator = [e for e in cc if e != ticket.created_by.email]
        _send(subject, text, html, [ticket.created_by.email], cc_list=cc_no_creator)

    managers = _get_department_managers(ticket.department)
    if managers.exists():
        subject = f"[MallDesk] Ticket {ticket.ticket_id} Updated — {new_status_label}"
        try:
            html = render_to_string('emails/ticket_updated_manager.html', context)
        except Exception as e:
            html = None
            print(f"[EMAIL] Template error: {e}")
        text = (
            f"Ticket {ticket.ticket_id} updated.\n"
            f"By    : {update.updated_by.full_name if update.updated_by else 'System'}\n"
            f"Status: {update.old_status or '—'} → {update.new_status or '(no change)'}\n"
            f"Note  : {update.note}\n— MallDesk System"
        )
        _send(subject, text, html, list(managers.values_list('email', flat=True)), cc_list=cc)


def notify_ticket_resolved(ticket):
    print(f"[EMAIL] notify_ticket_resolved called for {ticket.ticket_id}")
    context = {'ticket': ticket}
    cc = _build_cc(ticket)

    if ticket.created_by and ticket.created_by.email:
        subject = f"[MallDesk] Ticket {ticket.ticket_id} Resolved"
        try:
            html = render_to_string('emails/ticket_resolved_customer.html', context)
        except Exception as e:
            html = None
            print(f"[EMAIL] Template error: {e}")
        text = (
            f"Dear {ticket.complainant_name},\n\n"
            f"Ticket {ticket.ticket_id} has been resolved.\n\n"
            f"Resolution : {ticket.resolution}\n"
            f"Resolved by: {ticket.assigned_to.full_name if ticket.assigned_to else 'Our team'}\n\n— MallDesk Support"
        )
        cc_no_creator = [e for e in cc if e != ticket.created_by.email]
        _send(subject, text, html, [ticket.created_by.email], cc_list=cc_no_creator)

    managers = _get_department_managers(ticket.department)
    if managers.exists():
        subject = f"[MallDesk] Ticket {ticket.ticket_id} Resolved"
        try:
            html = render_to_string('emails/ticket_resolved_manager.html', context)
        except Exception as e:
            html = None
            print(f"[EMAIL] Template error: {e}")
        text = (
            f"Ticket {ticket.ticket_id} resolved.\n"
            f"Complainant: {ticket.complainant_name}\n"
            f"Resolved by: {ticket.assigned_to.full_name if ticket.assigned_to else 'N/A'}\n"
            f"Resolution : {ticket.resolution}"
        )
        _send(subject, text, html, list(managers.values_list('email', flat=True)), cc_list=cc)