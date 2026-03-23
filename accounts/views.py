from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import ExternalRegisterForm, InternalUserCreateForm, LoginForm
from .models import User, UserRemovalLog
from django.utils import timezone


class CustomLoginView(LoginView):
    form_class = LoginForm
    template_name = 'accounts/login.html'

    def get_success_url(self):
        return '/dashboard/'


def register_external(request):
    if request.method == 'POST':
        form = ExternalRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Welcome, {user.full_name}! Your account has been created.")
            return redirect('/dashboard/')
    else:
        form = ExternalRegisterForm()
    return render(request, 'accounts/register.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('/accounts/login/')


@login_required
def create_internal_user(request):
    if not request.user.is_manager_or_admin:
        messages.error(request, "You don't have permission to create internal users.")
        return redirect('/dashboard/')

    if request.method == 'POST':
        form = InternalUserCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f"Internal user '{user.full_name}' created successfully.")
            return redirect('/users/')
    else:
        form = InternalUserCreateForm()
    return render(request, 'accounts/create_internal_user.html', {'form': form})


@login_required
def user_list(request):
    if not request.user.is_manager_or_admin:
        return redirect('/dashboard/')
    internal_users = User.objects.filter(role__in=[User.INTERNAL, User.MANAGER], is_active=True)
    external_users = User.objects.filter(role=User.EXTERNAL, is_active=True)
    removed_users  = UserRemovalLog.objects.select_related('user', 'removed_by').all()
    return render(request, 'accounts/user_list.html', {
        'internal_users': internal_users,
        'external_users': external_users,
        'removed_users':  removed_users,
    })


@login_required
def remove_user(request, user_id):
    if not request.user.is_manager_or_admin:
        messages.error(request, "Permission denied.")
        return redirect('user_list')

    user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, "Please provide a reason for removal.")
            return redirect('user_list')

        # Deactivate user
        user.is_active = False
        user.save()

        # Log the removal
        UserRemovalLog.objects.create(
            user=user,
            removed_by=request.user,
            reason=reason,
        )

        messages.success(request, f"{user.full_name} has been deactivated.")
    return redirect('user_list')


@login_required
def reactivate_user(request, user_id):
    if not request.user.is_manager_or_admin:
        messages.error(request, "Permission denied.")
        return redirect('user_list')

    user = get_object_or_404(User, id=user_id)
    user.is_active = True
    user.save()

    # Mark latest log as reactivated
    log = UserRemovalLog.objects.filter(user=user, reactivated=False).first()
    if log:
        log.reactivated    = True
        log.reactivated_at = timezone.now()
        log.save()

    messages.success(request, f"{user.full_name} has been reactivated.")
    return redirect('user_list')