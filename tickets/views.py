import csv
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count
from .models import Ticket, TicketUpdate, Mall, Department, Shop, ShopContact, SubCategory, Designation
from .forms import (
    TicketCreateForm, TicketAssignForm, TicketUpdateForm,
    TicketResolveForm, TicketEditForm, TicketFilterForm
)
from . import email_service


# ── DASHBOARD ─────────────────────────────────────────────────────────────────
@login_required
def dashboard(request):
    user = request.user

    if user.is_external:
        tickets = Ticket.objects.filter(created_by=user)
    else:
        tickets = Ticket.objects.all()

    context = {
        'total':       tickets.count(),
        'open':        tickets.filter(ticket_status=Ticket.OPEN).count(),
        'in_progress': tickets.filter(ticket_status=Ticket.IN_PROGRESS).count(),
        'resolved':    tickets.filter(ticket_status=Ticket.RESOLVED).count(),
        'recent':      tickets[:10],
    }
    return render(request, 'tickets/dashboard.html', context)


# ── TICKET LIST ───────────────────────────────────────────────────────────────
@login_required
def ticket_list(request):
    user = request.user
    form = TicketFilterForm(request.GET)

    if user.is_external:
        qs = Ticket.objects.filter(created_by=user)
    else:
        qs = Ticket.objects.all()

    if form.is_valid():
        if form.cleaned_data.get('status'):
            qs = qs.filter(ticket_status=form.cleaned_data['status'])
        if form.cleaned_data.get('priority'):
            qs = qs.filter(priority=form.cleaned_data['priority'])
        if form.cleaned_data.get('dept'):
            qs = qs.filter(department=form.cleaned_data['dept'])
        if form.cleaned_data.get('search'):
            q = form.cleaned_data['search']
            qs = qs.filter(
                Q(ticket_id__icontains=q) |
                Q(complainant_name__icontains=q) |
                Q(complaint_description__icontains=q)
            )

    return render(request, 'tickets/ticket_list.html', {'tickets': qs, 'filter_form': form})


# ── CREATE TICKET ─────────────────────────────────────────────────────────────
@login_required
def ticket_create(request):
    if request.method == 'POST':
        form = TicketCreateForm(request.POST, user=request.user)
        if form.is_valid():
            ticket = form.save(commit=False)

            # ── Complainant from AJAX-driven hidden fields ──
            complainant_name    = request.POST.get('complainant_name', '').strip()
            complainant_company = request.POST.get('complainant_company', '').strip()
            complainant_address = request.POST.get('complainant_address', '').strip()

            if complainant_name:
                ticket.complainant_name    = complainant_name
                ticket.complainant_company = complainant_company
                ticket.complainant_address = complainant_address

            # Link selected shop
            shop_id = request.POST.get('shop')
            if shop_id:
                try:
                    from .models import Shop
                    ticket.shop = Shop.objects.get(id=shop_id)
                except Exception:
                    pass

            ticket.created_by = request.user
            ticket.save()

            # ── Log initial update ──────────────────────
            TicketUpdate.objects.create(
                ticket=ticket,
                updated_by=request.user,
                new_status=Ticket.OPEN,
                note="Ticket created.",
            )

            # ── Send emails ─────────────────────────────
            email_service.notify_ticket_created(ticket)

            messages.success(request, f"Ticket {ticket.ticket_id} created successfully.")
            return redirect('ticket_detail', pk=ticket.pk)
    else:
        form = TicketCreateForm(user=request.user)
    return render(request, 'tickets/ticket_form.html', {'form': form, 'title': 'Create New Ticket'})


# ── TICKET DETAIL ─────────────────────────────────────────────────────────────
# No @login_required — allows WhatsApp link recipients to view without login.
# Action buttons (assign/update/resolve) are hidden for unauthenticated users in template.
def ticket_detail(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)

    # Logged-in external users can only see their own tickets
    if request.user.is_authenticated and request.user.is_external:
        if ticket.created_by != request.user:
            messages.error(request, "You don't have permission to view this ticket.")
            return redirect('ticket_list')

    update_form  = TicketUpdateForm()
    assign_form  = TicketAssignForm(instance=ticket)
    resolve_form = TicketResolveForm(instance=ticket)

    from django.conf import settings as django_settings
    whatsapp_number = getattr(django_settings, 'WHATSAPP_NOTIFY_NUMBER', '')
    ticket_url = request.build_absolute_uri(request.path)

    # For public/guest view — flat list of fields to display
    ticket_fields = [
        ('Complainant Name',    ticket.complainant_name),
        ('Company Name',        ticket.complainant_company or '—'),
        ('Mall / Location',     ticket.mall.name),
        ('Ticket Type',         ticket.get_ticket_type_display()),
        ('Department',          ticket.department.name),
        ('Sub Category',        ticket.sub_category.name if ticket.sub_category else '—'),
        ('Due Date',            ticket.due_date or 'Not set'),
        ('Created At',          ticket.created_at.strftime('%d %b %Y, %H:%M')),
    ]

    from .models import Designation
    from django.db.models import Q
    designations = Designation.objects.filter(
        is_active=True
    ).filter(
        Q(department=ticket.department) | Q(department__isnull=True)
    ).order_by('level_order')

    return render(request, 'tickets/ticket_detail.html', {
        'ticket':          ticket,
        'updates':         ticket.updates.all(),
        'update_form':     update_form,
        'assign_form':     assign_form,
        'resolve_form':    resolve_form,
        'whatsapp_number': whatsapp_number,
        'ticket_url':      ticket_url,
        'ticket_fields':   ticket_fields,
        'designations':    designations,
    })


# ── EDIT TICKET ───────────────────────────────────────────────────────────────
@login_required
def ticket_edit(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)

    # Only creator can edit, and only if still Open
    if request.user.is_external:
        if ticket.created_by != request.user:
            messages.error(request, "Permission denied.")
            return redirect('ticket_list')
        if ticket.ticket_status != Ticket.OPEN:
            messages.error(request, "You can only edit tickets that are still Open.")
            return redirect('ticket_detail', pk=pk)

    if request.method == 'POST':
        form = TicketEditForm(request.POST, instance=ticket)
        if form.is_valid():
            form.save()
            TicketUpdate.objects.create(
                ticket=ticket,
                updated_by=request.user,
                note="Ticket description updated by complainant.",
            )
            messages.success(request, "Ticket updated.")
            return redirect('ticket_detail', pk=pk)
    else:
        form = TicketEditForm(instance=ticket)
    return render(request, 'tickets/ticket_form.html', {'form': form, 'title': 'Edit Ticket', 'ticket': ticket})


# ── DELETE TICKET ─────────────────────────────────────────────────────────────
@login_required
def ticket_delete(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)

    if request.user.is_external and ticket.created_by != request.user:
        messages.error(request, "Permission denied.")
        return redirect('ticket_list')

    if request.user.is_external and ticket.ticket_status != Ticket.OPEN:
        messages.error(request, "You can only delete tickets that are still Open.")
        return redirect('ticket_detail', pk=pk)

    if request.method == 'POST':
        ticket_id = ticket.ticket_id
        ticket.delete()
        messages.success(request, f"Ticket {ticket_id} deleted.")
        return redirect('ticket_list')

    return render(request, 'tickets/ticket_confirm_delete.html', {'ticket': ticket})


# ── ASSIGN TICKET (Manager/Admin) ─────────────────────────────────────────────
@login_required
def ticket_assign(request, pk):
    if not request.user.is_manager_or_admin:
        messages.error(request, "Only managers can assign tickets.")
        return redirect('ticket_detail', pk=pk)

    ticket = get_object_or_404(Ticket, pk=pk)

    if request.method == 'POST':
        form = TicketAssignForm(request.POST, instance=ticket)
        if form.is_valid():
            old_status = ticket.ticket_status
            updated = form.save(commit=False)
            if not updated.ticket_status or updated.ticket_status == Ticket.OPEN:
                updated.ticket_status = Ticket.IN_PROGRESS
            updated.save()

            TicketUpdate.objects.create(
                ticket=ticket,
                updated_by=request.user,
                old_status=old_status,
                new_status=updated.ticket_status,
                note=f"Assigned to {ticket.assigned_to.full_name}.",
            )

            # ── Send emails ─────────────────────────────
            email_service.notify_ticket_assigned(ticket)

            messages.success(request, f"Ticket assigned to {ticket.assigned_to.full_name} and emails sent.")
            return redirect('ticket_detail', pk=pk)

    return redirect('ticket_detail', pk=pk)


# ── UPDATE STATUS / ADD NOTE ──────────────────────────────────────────────────
@login_required
def ticket_add_update(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)

    if request.method == 'POST':
        form = TicketUpdateForm(request.POST)
        new_status = request.POST.get('new_status', '')

        if form.is_valid():
            old_status = ticket.ticket_status

            update = form.save(commit=False)
            update.ticket = ticket
            update.updated_by = request.user
            update.old_status = old_status

            if new_status and new_status != old_status:
                update.new_status = new_status
                ticket.ticket_status = new_status
                ticket.save(update_fields=['ticket_status'])

            update.save()

            # ── Send emails ─────────────────────────────
            email_service.notify_ticket_updated(ticket, update)

            messages.success(request, "Update added and notifications sent.")

    return redirect('ticket_detail', pk=pk)


# ── RESOLVE TICKET ────────────────────────────────────────────────────────────
@login_required
def ticket_resolve(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)

    if request.method == 'POST':
        form = TicketResolveForm(request.POST, instance=ticket)
        if form.is_valid():
            old_status = ticket.ticket_status
            resolved = form.save(commit=False)
            resolved.ticket_status = Ticket.RESOLVED
            resolved.resolved_on = timezone.now()
            resolved.save()

            TicketUpdate.objects.create(
                ticket=ticket,
                updated_by=request.user,
                old_status=old_status,
                new_status=Ticket.RESOLVED,
                note=f"Ticket resolved. Resolution: {ticket.resolution}",
            )

            # ── Send emails ─────────────────────────────
            email_service.notify_ticket_resolved(ticket)

            messages.success(request, f"Ticket {ticket.ticket_id} marked as Resolved. Notification emails sent.")

    return redirect('ticket_detail', pk=pk)


# ── AJAX: Get shops for a mall ────────────────────────────────────────────────
def ajax_get_shops(request):
    mall_id = request.GET.get('mall_id')
    if not mall_id:
        return JsonResponse({'shops': []})
    shops = Shop.objects.filter(mall_id=mall_id, is_active=True).values(
        'id', 'shop_number', 'shop_name', 'floor'
    )
    return JsonResponse({'shops': list(shops)})


# ── AJAX: Get contact types for a shop ───────────────────────────────────────
def ajax_get_contact_types(request):
    shop_id = request.GET.get('shop_id')
    if not shop_id:
        return JsonResponse({'types': []})
    types = ShopContact.objects.filter(
        shop_id=shop_id, is_active=True
    ).values_list('contact_type', flat=True).distinct()
    type_choices = [
        {'value': t, 'label': dict(ShopContact.TYPE_CHOICES).get(t, t)}
        for t in types
    ]
    return JsonResponse({'types': type_choices})


# ── AJAX: Get contacts for a shop + type ─────────────────────────────────────
def ajax_get_contacts(request):
    shop_id      = request.GET.get('shop_id')
    contact_type = request.GET.get('contact_type')
    if not shop_id or not contact_type:
        return JsonResponse({'contacts': []})
    contacts = ShopContact.objects.filter(
        shop_id=shop_id, contact_type=contact_type, is_active=True
    ).values('id', 'name', 'mobile', 'email')
    return JsonResponse({'contacts': list(contacts)})


# ── AJAX: Get sub-categories for a department ─────────────────────────────────
def ajax_get_subcategories(request):
    dept_id = request.GET.get('dept_id')
    if not dept_id:
        return JsonResponse({'subcategories': []})
    subs = SubCategory.objects.filter(
        department_id=dept_id, is_active=True
    ).values('id', 'name')
    return JsonResponse({'subcategories': list(subs)})


# ── AJAX: Get users by designation for assign dropdown ───────────────────────
def ajax_get_users_by_designation(request):
    designation_id = request.GET.get('designation_id')
    dept_id        = request.GET.get('dept_id')
    if not designation_id:
        return JsonResponse({'users': []})
    qs = get_user_model().objects.filter(
        designation_id=designation_id,
        is_active=True,
        role__in=['internal', 'manager'],
    )
    if dept_id:
        qs = qs.filter(department_id=dept_id)
    users = qs.values('id', 'full_name', 'email')
    return JsonResponse({'users': list(users)})


# ── AJAX: Get designations for a department ───────────────────────────────────
def ajax_get_designations(request):
    dept_id = request.GET.get('dept_id')
    from django.db.models import Q
    qs = Designation.objects.filter(is_active=True)
    if dept_id:
        qs = qs.filter(Q(department_id=dept_id) | Q(department__isnull=True))
    designations = qs.values('id', 'name', 'level_order')
    return JsonResponse({'designations': list(designations)})


# ── ESCALATION: Auto-escalate a ticket ───────────────────────────────────────
@login_required
def ticket_escalate(request, pk):
    """
    Called automatically by scheduler OR manually by manager.
    Reassigns ticket to next higher designation user in the same department.
    """
    ticket = get_object_or_404(Ticket, pk=pk)

    if not request.user.is_manager_or_admin:
        messages.error(request, "Only managers can escalate tickets.")
        return redirect('ticket_detail', pk=pk)

    result = _do_escalate(ticket, escalated_by=request.user, manual=True)
    if result['success']:
        messages.success(request, result['message'])
    else:
        messages.error(request, result['message'])

    return redirect('ticket_detail', pk=pk)


def _do_escalate(ticket, escalated_by=None, manual=False):
    """
    Core escalation logic — finds next higher designation user and reassigns.
    Returns dict with success, message.
    """
    from django.utils import timezone
    from django.contrib.auth import get_user_model
    User = get_user_model()

    if not ticket.assigned_to:
        return {'success': False, 'message': 'Ticket is not assigned to anyone.'}

    current_designation = getattr(ticket.assigned_to, 'designation', None)
    if not current_designation:
        return {'success': False, 'message': f'{ticket.assigned_to.full_name} has no designation set — cannot escalate.'}

    # Get next higher designation
    next_designation = current_designation.get_next_level(department=ticket.department)
    if not next_designation:
        return {'success': False, 'message': f'No higher designation found above {current_designation.name}.'}

    # Find available user with that designation in the same department
    next_user = User.objects.filter(
        designation=next_designation,
        department=ticket.department,
        is_active=True,
        role__in=['internal', 'manager'],
    ).first()

    # Fallback: same designation any department
    if not next_user:
        next_user = User.objects.filter(
            designation=next_designation,
            is_active=True,
            role__in=['internal', 'manager'],
        ).first()

    if not next_user:
        return {'success': False, 'message': f'No active user found with designation: {next_designation.name}'}

    old_assignee = ticket.assigned_to

    # Update ticket
    ticket.escalated_from   = old_assignee
    ticket.escalated        = True
    ticket.escalated_at     = timezone.now()
    ticket.escalation_count = (ticket.escalation_count or 0) + 1
    ticket.assigned_to      = next_user
    ticket.ticket_status    = Ticket.IN_PROGRESS
    ticket.save()

    # Log in timeline
    note = (
        f"{'[AUTO-ESCALATION]' if not manual else '[MANUAL ESCALATION]'} "
        f"Escalated from {old_assignee.full_name} ({current_designation.name}) "
        f"to {next_user.full_name} ({next_designation.name}) — "
        f"Ticket unresolved."
    )
    TicketUpdate.objects.create(
        ticket=ticket,
        updated_by=escalated_by,
        old_status=Ticket.IN_PROGRESS,
        new_status=Ticket.IN_PROGRESS,
        note=note,
    )

    # Send email notifications
    try:
        from tickets import email_service
        email_service.notify_ticket_assigned(ticket)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Escalation email failed: {e}")

    msg = f"Ticket escalated from {old_assignee.full_name} to {next_user.full_name} ({next_designation.name})"
    return {'success': True, 'message': msg, 'new_assignee': next_user}


# ── EXPORT: Tickets CSV ────────────────────────────────────────────────────────
@login_required
def export_tickets_csv(request):
    user = request.user
    if user.is_external:
        qs = Ticket.objects.filter(created_by=user)
    else:
        qs = Ticket.objects.all()

    # Apply same filters as ticket_list
    status   = request.GET.get('status')
    priority = request.GET.get('priority')
    search   = request.GET.get('search')
    dept     = request.GET.get('dept')

    if status:   qs = qs.filter(ticket_status=status)
    if priority: qs = qs.filter(priority=priority)
    if dept:     qs = qs.filter(department_id=dept)
    if search:
        qs = qs.filter(
            Q(ticket_id__icontains=search) |
            Q(complainant_name__icontains=search) |
            Q(complaint_description__icontains=search)
        )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="tickets.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Ticket ID', 'Complainant Name', 'Company', 'Address',
        'Mall', 'Department', 'Sub Category', 'Ticket Type',
        'Priority', 'Status', 'Assigned To', 'Due Date',
        'Created At', 'Resolved On', 'Resolution Time (hrs)',
        'Complaint Description', 'Resolution',
        'Escalated', 'Escalation Count',
    ])

    for t in qs.select_related('mall', 'department', 'sub_category', 'assigned_to'):
        writer.writerow([
            t.ticket_id,
            t.complainant_name,
            t.complainant_company,
            t.complainant_address,
            t.mall.name,
            t.department.name,
            t.sub_category.name if t.sub_category else '',
            t.get_ticket_type_display(),
            t.get_priority_display(),
            t.get_ticket_status_display(),
            t.assigned_to.full_name if t.assigned_to else '',
            t.due_date or '',
            t.created_at.strftime('%d-%m-%Y %H:%M'),
            t.resolved_on.strftime('%d-%m-%Y %H:%M') if t.resolved_on else '',
            t.resolution_time or '',
            t.complaint_description,
            t.resolution,
            'Yes' if t.escalated else 'No',
            t.escalation_count,
        ])

    return response


# ── EXPORT: Users CSV ──────────────────────────────────────────────────────────
@login_required
def export_users_csv(request):
    if not request.user.is_manager_or_admin:
        return redirect('dashboard')

    user_type = request.GET.get('type', 'internal')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{user_type}_users.csv"'
    writer = csv.writer(response)

    from django.contrib.auth import get_user_model
    User = get_user_model()

    if user_type == 'external':
        writer.writerow(['Full Name', 'Email', 'Mobile', 'Business Name', 'Mall', 'Tickets Raised', 'Joined'])
        qs = User.objects.filter(role=User.EXTERNAL)
        for u in qs:
            writer.writerow([
                u.full_name,
                u.email,
                u.mobile,
                u.business_name,
                u.project.name if u.project else '',
                u.created_tickets.count(),
                u.date_joined.strftime('%d-%m-%Y'),
            ])
    elif user_type == 'removed':
        from accounts.models import UserRemovalLog
        writer.writerow(['User Name', 'Email', 'Removed By', 'Reason', 'Removed On', 'Reactivated', 'Reactivated On'])
        for log in UserRemovalLog.objects.select_related('user', 'removed_by').all():
            writer.writerow([
                log.user.full_name,
                log.user.email,
                log.removed_by.full_name if log.removed_by else '',
                log.reason,
                log.removed_at.strftime('%d-%m-%Y %H:%M'),
                'Yes' if log.reactivated else 'No',
                log.reactivated_at.strftime('%d-%m-%Y %H:%M') if log.reactivated_at else '',
            ])
    else:
        writer.writerow(['Full Name', 'Email', 'Mobile', 'Role', 'Department', 'Designation', 'Active', 'Joined'])
        qs = User.objects.filter(role__in=[User.INTERNAL, User.MANAGER, User.ADMIN])
        for u in qs:
            writer.writerow([
                u.full_name,
                u.email,
                u.mobile,
                u.get_role_display(),
                u.department.name if u.department else '',
                u.designation.name if u.designation else '',
                'Yes' if u.is_active else 'No',
                u.date_joined.strftime('%d-%m-%Y'),
            ])

    return response