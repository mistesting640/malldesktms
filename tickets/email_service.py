"""
malldesk/tickets/email_service.py

Email flow for every notification:
  TO  → main recipient (customer or manager)
  CC  → MALLDESK_CC_EMAILS (manual) + ticket creator email (automatic)
  BCC → MALLDESK_ADMIN_EMAILS (always hidden)

So when a ticket action happens:
  - Customer (ticket creator) always gets CC'd on every email
  - Manual CC list from settings always included
  - Admin always BCC'd silently
"""

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


def _get_admin_emails():
    """BCC'd on every single email — invisible to recipients."""
    admin_emails = getattr(settings, 'MALLDESK_ADMIN_EMAILS', None)
    if admin_emails:
        return list(admin_emails)
    return list(User.objects.filter(role=User.ADMIN, is_active=True).values_list('email', flat=True))


def _get_cc_emails():
    """Fixed CC list from settings.py MALLDESK_CC_EMAILS."""
    return list(getattr(settings, 'MALLDESK_CC_EMAILS', []))


def _get_ticket_creator_email(ticket):
    """Automatically fetch the external user who raised the ticket."""
    if ticket.created_by and ticket.created_by.email:
        return ticket.created_by.email
    return None


def _build_cc(ticket, extra_cc=None):
    """
    Builds the final CC list for any email:
      1. Manual CC from settings (MALLDESK_CC_EMAILS)
      2. Ticket creator email (auto — the external user who raised the ticket)
      3. Any additional cc passed in
    """
    cc = list(_get_cc_emails())                     # manual CC from settings
    creator = _get_ticket_creator_email(ticket)
    if creator:
        cc.append(creator)                          # auto: external user who raised ticket
    if extra_cc:
        cc.extend(extra_cc)
    return list(set(filter(None, cc)))              # deduplicate & remove empty


def _send_now(subject, text_body, html_body, to_list, cc_list, bcc_list):
    """
    Actual SMTP send — runs in background thread.
    Uses raw smtplib directly to avoid gunicorn worker timeout.
    Tries port 587 (STARTTLS) first, falls back to 465 (SSL).
    """
    import smtplib, ssl
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    host     = settings.EMAIL_HOST
    user     = settings.EMAIL_HOST_USER
    password = settings.EMAIL_HOST_PASSWORD
    from_email = settings.DEFAULT_FROM_EMAIL

    all_recipients = list(set(to_list + cc_list + bcc_list))

    # Build MIME message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = from_email
    msg['To']      = ', '.join(to_list)
    if cc_list:
        msg['Cc']  = ', '.join(cc_list)
    # BCC not added to headers — just included in recipients list

    msg.attach(MIMEText(text_body, 'plain'))
    if html_body:
        msg.attach(MIMEText(html_body, 'html'))

    # SSL context — ignore hostname mismatch (DreamHost cert issue)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE

    sent = False

    # Try 587 STARTTLS first (works on Render)
    try:
        with smtplib.SMTP(host, 587, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ctx)
            smtp.login(user, password)
            smtp.sendmail(from_email, all_recipients, msg.as_bytes())
            sent = True
            logger.info(f"Email sent (587) | TO:{to_list} | {subject}")
    except Exception as e1:
        logger.warning(f"Port 587 failed ({e1}), trying 465...")

    # Fallback to 465 SSL
    if not sent:
        try:
            with smtplib.SMTP_SSL(host, 465, context=ctx, timeout=20) as smtp:
                smtp.login(user, password)
                smtp.sendmail(from_email, all_recipients, msg.as_bytes())
                sent = True
                logger.info(f"Email sent (465) | TO:{to_list} | {subject}")
        except Exception as e2:
            logger.error(f"Email failed both ports | {subject} | 587:{e1} | 465:{e2}")


def _send(subject, text_body, html_body, to_list, cc_list=None):
    """
    Sends email in a background thread so the user gets
    instant response — no waiting for SMTP to complete.

    TO  → main recipients
    CC  → visible to all (ticket creator + manual CC)
    BCC → admin always (invisible)
    """
    import threading

    to_list  = [e for e in (to_list  or []) if e]
    cc_list  = [e for e in (cc_list  or []) if e]
    bcc_list = [e for e in _get_admin_emails() if e]

    # Deduplicate across TO / CC / BCC
    all_addressed = set(to_list + cc_list)
    bcc_list = [e for e in bcc_list if e not in all_addressed]
    cc_list  = [e for e in cc_list  if e not in set(to_list)]

    if not to_list:
        logger.warning(f"Email skipped — no recipients for: {subject}")
        return

    logger.info(f"Queuing email in background | TO:{to_list} | Subject:{subject}")

    # Fire and forget — daemon thread dies if server restarts
    thread = threading.Thread(
        target=_send_now,
        args=(subject, text_body, html_body, to_list, cc_list, bcc_list),
        daemon=True,
    )
    thread.start()


def _get_department_managers(department):
    return User.objects.filter(
        department=department,
        role__in=[User.MANAGER, User.ADMIN],
        is_active=True,
    )


# ── 1. TICKET CREATED ─────────────────────────────────────────────────────────
def notify_ticket_created(ticket):
    """
    Customer  → TO (their own confirmation)
    Managers  → TO (alert)
    CC on both → ticket creator + manual CC list
    BCC on both → admin
    """
    context = {'ticket': ticket}
    cc = _build_cc(ticket)  # includes creator + manual CC

    # Email to customer
    if ticket.created_by and ticket.created_by.email:
        subject = f"[MallDesk] Ticket {ticket.ticket_id} Received — {ticket.mall.name}"
        html = render_to_string('emails/ticket_created_customer.html', context)
        text = (
            f"Dear {ticket.complainant_name},\n\n"
            f"Your ticket {ticket.ticket_id} has been received.\n"
            f"Type     : {ticket.get_ticket_type_display()}\n"
            f"Priority : {ticket.get_priority_display()}\n"
            f"Dept     : {ticket.department.name}\n"
            f"Due Date : {ticket.due_date or 'TBD'}\n\n"
            f"We will keep you updated.\n\n— MallDesk Support Team"
        )
        # Creator is TO here, so remove from CC to avoid duplicate
        cc_for_customer = [e for e in cc if e != ticket.created_by.email]
        _send(subject, text, html, [ticket.created_by.email], cc_list=cc_for_customer)

    # Email to managers
    managers = _get_department_managers(ticket.department)
    if managers.exists():
        subject = f"[MallDesk] New {ticket.get_priority_display()} Ticket — {ticket.ticket_id}"
        html = render_to_string('emails/ticket_created_manager.html', context)
        text = (
            f"New ticket submitted.\n\n"
            f"Ticket ID  : {ticket.ticket_id}\n"
            f"Complainant: {ticket.complainant_name} ({ticket.complainant_company})\n"
            f"Mall       : {ticket.mall.name}\n"
            f"Department : {ticket.department.name}\n"
            f"Priority   : {ticket.get_priority_display()}\n"
            f"Due Date   : {ticket.due_date or 'Not set'}\n\n"
            f"Description:\n{ticket.complaint_description}\n\n— MallDesk System"
        )
        manager_emails = list(managers.values_list('email', flat=True))
        _send(subject, text, html, manager_emails, cc_list=cc)


# ── 2. TICKET ASSIGNED ────────────────────────────────────────────────────────
def notify_ticket_assigned(ticket):
    """
    Assignee  → TO
    Customer  → TO
    CC on both → ticket creator + manual CC
    BCC → admin
    """
    if not ticket.assigned_to:
        return
    context = {'ticket': ticket}
    cc = _build_cc(ticket)

    # Email to assigned internal user
    subject = f"[MallDesk] Ticket {ticket.ticket_id} Assigned to You"
    html = render_to_string('emails/ticket_assigned_internal.html', context)
    text = (
        f"Dear {ticket.assigned_to.full_name},\n\n"
        f"Ticket {ticket.ticket_id} has been assigned to you.\n\n"
        f"Complainant: {ticket.complainant_name}\n"
        f"Address    : {ticket.complainant_address}\n"
        f"Mall       : {ticket.mall.name}\n"
        f"Priority   : {ticket.get_priority_display()}\n"
        f"Due Date   : {ticket.due_date or 'ASAP'}\n\n"
        f"Issue:\n{ticket.complaint_description}\n\n— MallDesk System"
    )
    _send(subject, text, html, [ticket.assigned_to.email], cc_list=cc)

    # Email to customer
    if ticket.created_by and ticket.created_by.email:
        subject = f"[MallDesk] Your Ticket {ticket.ticket_id} is Now In Progress"
        html = render_to_string('emails/ticket_assigned_customer.html', context)
        text = (
            f"Dear {ticket.complainant_name},\n\n"
            f"Ticket {ticket.ticket_id} is now In Progress.\n"
            f"Assigned to: {ticket.assigned_to.full_name} ({ticket.department.name})\n\n"
            f"We will notify you once resolved.\n\n— MallDesk Support Team"
        )
        cc_for_customer = [e for e in cc if e != ticket.created_by.email]
        _send(subject, text, html, [ticket.created_by.email], cc_list=cc_for_customer)


# ── 3. TICKET UPDATED ─────────────────────────────────────────────────────────
def notify_ticket_updated(ticket, update):
    """
    Customer  → TO
    Managers  → TO (on status change)
    CC on both → ticket creator + manual CC
    BCC → admin
    """
    context = {'ticket': ticket, 'update': update}
    cc = _build_cc(ticket)

    # ── Always email customer on any update or note ─────
    if ticket.created_by and ticket.created_by.email:
        subject = f"[MallDesk] Update on Ticket {ticket.ticket_id}"
        html = render_to_string('emails/ticket_updated_customer.html', context)
        text = f"Dear {ticket.complainant_name},\n\nUpdate on ticket {ticket.ticket_id}.\n\n"
        if update.old_status and update.new_status:
            text += f"Status: {update.old_status.replace('_',' ').title()} → {update.new_status.replace('_',' ').title()}\n\n"
        text += f"Note: {update.note}\n\n— MallDesk Support Team"
        cc_for_customer = [e for e in cc if e != ticket.created_by.email]
        _send(subject, text, html, [ticket.created_by.email], cc_list=cc_for_customer)

    # ── Always email managers on any update ──────────────
    managers = _get_department_managers(ticket.department)
    if managers.exists():
        # Safe status label — may be empty if no status change
        new_status_label = update.new_status.replace('_', ' ').title() if update.new_status else 'Note Added'
        subject = f"[MallDesk] Update on Ticket {ticket.ticket_id} — {new_status_label}"
        html = render_to_string('emails/ticket_updated_manager.html', context)
        text = (
            f"Ticket {ticket.ticket_id} updated.\n"
            f"By     : {update.updated_by.full_name if update.updated_by else 'System'}\n"
            f"Status : {update.old_status or '—'} → {update.new_status or '(no change)'}\n"
            f"Note   : {update.note}\n— MallDesk System"
        )
        manager_emails = list(managers.values_list('email', flat=True))
        _send(subject, text, html, manager_emails, cc_list=cc)


# ── 4. TICKET RESOLVED ────────────────────────────────────────────────────────
def notify_ticket_resolved(ticket):
    """
    Customer  → TO
    Managers  → TO
    CC on both → ticket creator + manual CC
    BCC → admin
    """
    context = {'ticket': ticket}
    cc = _build_cc(ticket)

    # Email to customer
    if ticket.created_by and ticket.created_by.email:
        subject = f"[MallDesk] Ticket {ticket.ticket_id} Resolved ✓"
        html = render_to_string('emails/ticket_resolved_customer.html', context)
        text = (
            f"Dear {ticket.complainant_name},\n\n"
            f"Ticket {ticket.ticket_id} has been resolved.\n\n"
            f"Resolution : {ticket.resolution}\n"
            f"Resolved by: {ticket.assigned_to.full_name if ticket.assigned_to else 'Our team'}\n"
            f"Time taken : {ticket.resolution_time} hours\n\n"
            f"If the issue persists, raise a new ticket.\n\n— MallDesk Support Team"
        )
        cc_for_customer = [e for e in cc if e != ticket.created_by.email]
        _send(subject, text, html, [ticket.created_by.email], cc_list=cc_for_customer)

    # Email to managers
    managers = _get_department_managers(ticket.department)
    if managers.exists():
        subject = f"[MallDesk] Ticket {ticket.ticket_id} Resolved in {ticket.resolution_time}h"
        html = render_to_string('emails/ticket_resolved_manager.html', context)
        text = (
            f"Ticket {ticket.ticket_id} resolved.\n"
            f"Complainant: {ticket.complainant_name}\n"
            f"Resolved by: {ticket.assigned_to.full_name if ticket.assigned_to else 'N/A'}\n"
            f"Time taken : {ticket.resolution_time} hours\n"
            f"Resolution : {ticket.resolution}"
        )
        manager_emails = list(managers.values_list('email', flat=True))
        _send(subject, text, html, manager_emails, cc_list=cc)