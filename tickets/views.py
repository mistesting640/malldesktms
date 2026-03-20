from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count
from .models import Ticket, TicketUpdate, Mall, Department
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
            ticket = form.save()

            # ── Log initial update ──────────────────────
            TicketUpdate.objects.create(
                ticket=ticket,
                updated_by=request.user,
                new_status=Ticket.OPEN,
                note="Ticket created.",
            )

            # ── Send emails ─────────────────────────────
            email_service.notify_ticket_created(ticket)

            messages.success(request, f"Ticket {ticket.ticket_id} created successfully. You will receive a confirmation email.")
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

    return render(request, 'tickets/ticket_detail.html', {
        'ticket':          ticket,
        'updates':         ticket.updates.all(),
        'update_form':     update_form,
        'assign_form':     assign_form,
        'resolve_form':    resolve_form,
        'whatsapp_number': whatsapp_number,
        'ticket_url':      ticket_url,
        'ticket_fields':   ticket_fields,
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