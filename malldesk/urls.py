from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts import views as account_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),

    # Top-level shortcuts so /users/ and /accounts/users/ both work
    path('users/', account_views.user_list, name='user_list'),
    path('users/create/', account_views.create_internal_user, name='create_internal_user'),
    path('users/<int:user_id>/remove/',     account_views.remove_user,     name='remove_user'),
    path('users/<int:user_id>/reactivate/', account_views.reactivate_user, name='reactivate_user'),

    path('', include('tickets.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)