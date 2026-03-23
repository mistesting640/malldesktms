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

    # AJAX endpoints for cascading dropdowns
    path('ajax/shops/',           views.ajax_get_shops,           name='ajax_get_shops'),
    path('ajax/contact-types/',   views.ajax_get_contact_types,   name='ajax_get_contact_types'),
    path('ajax/contacts/',        views.ajax_get_contacts,        name='ajax_get_contacts'),
    path('ajax/subcategories/',   views.ajax_get_subcategories,   name='ajax_get_subcategories'),
    path('ajax/designations/',    views.ajax_get_designations,    name='ajax_get_designations'),
    path('ajax/users-by-desig/',  views.ajax_get_users_by_designation, name='ajax_get_users_by_designation'),

    # Escalation
    path('tickets/<int:pk>/escalate/', views.ticket_escalate, name='ticket_escalate'),

    # CSV Exports
    path('export/tickets/', views.export_tickets_csv, name='export_tickets_csv'),
    path('export/users/',   views.export_users_csv,   name='export_users_csv'),
]