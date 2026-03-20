from django.urls import path
from . import views

urlpatterns = [
    path('login/',    views.CustomLoginView.as_view(), name='login'),
    path('logout/',   views.logout_view,               name='logout'),
    path('register/', views.register_external,         name='register'),
    # Also accessible at /accounts/users/ but named routes are at top-level urls.py
    path('users/',         views.user_list,            name='accounts_user_list'),
    path('users/create/',  views.create_internal_user, name='accounts_create_internal_user'),
]