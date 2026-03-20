from django.urls import path
from . import views

urlpatterns = [
    path('',             views.dashboard,       name='dashboard'),
    path('dashboard/',   views.dashboard,       name='dashboard'),
    path('tickets/',     views.ticket_list,     name='ticket_list'),
    path('tickets/new/', views.ticket_create,   name='ticket_create'),
    path('tickets/<int:pk>/',        views.ticket_detail, name='ticket_detail'),
    path('tickets/<int:pk>/edit/',   views.ticket_edit,   name='ticket_edit'),
    path('tickets/<int:pk>/delete/', views.ticket_delete, name='ticket_delete'),
    path('tickets/<int:pk>/assign/', views.ticket_assign, name='ticket_assign'),
    path('tickets/<int:pk>/update/', views.ticket_add_update, name='ticket_add_update'),
    path('tickets/<int:pk>/resolve/', views.ticket_resolve, name='ticket_resolve'),
]
