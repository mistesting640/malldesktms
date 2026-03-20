from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import ExternalRegisterForm, InternalUserCreateForm, LoginForm
from .models import User


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
    internal_users = User.objects.filter(role__in=[User.INTERNAL, User.MANAGER])
    external_users = User.objects.filter(role=User.EXTERNAL)
    return render(request, 'accounts/user_list.html', {
        'internal_users': internal_users,
        'external_users': external_users,
    })
