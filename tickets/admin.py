from django.contrib import admin
from .models import Mall, Department, SubCategory, Ticket, TicketUpdate, Shop, ShopContact, Designation


@admin.register(Mall)
class MallAdmin(admin.ModelAdmin):
    list_display  = ('name', 'location', 'is_active')
    list_filter   = ('is_active',)
    search_fields = ('name', 'location')


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'mall', 'is_active')
    list_filter  = ('is_active', 'mall')


@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'department', 'is_active')
    list_filter  = ('department',)


class TicketUpdateInline(admin.TabularInline):
    model   = TicketUpdate
    extra   = 0
    readonly_fields = ('updated_by', 'old_status', 'new_status', 'note', 'created_at')
    can_delete = False


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display  = ('ticket_id', 'complainant_name', 'mall', 'department', 'priority', 'ticket_status', 'assigned_to', 'due_date', 'created_at')
    list_filter   = ('ticket_status', 'priority', 'ticket_type', 'mall', 'department')
    search_fields = ('ticket_id', 'complainant_name', 'complainant_company', 'complaint_description')
    readonly_fields = ('ticket_id', 'created_at', 'resolved_on', 'resolution_time')
    inlines       = [TicketUpdateInline]
    date_hierarchy = 'created_at'
    ordering      = ('-created_at',)

    fieldsets = (
        ('Ticket Info', {
            'fields': ('ticket_id', 'ticket_type', 'ticket_status', 'priority', 'due_date')
        }),
        ('Complainant', {
            'fields': ('complainant_name', 'complainant_company', 'complainant_address', 'created_by')
        }),
        ('Classification', {
            'fields': ('mall', 'department', 'sub_category')
        }),
        ('Content', {
            'fields': ('complaint_description', 'resolution')
        }),
        ('Assignment & Dates', {
            'fields': ('assigned_to', 'created_at', 'resolved_on', 'resolution_time')
        }),
    )


@admin.register(TicketUpdate)
class TicketUpdateAdmin(admin.ModelAdmin):
    list_display  = ('ticket', 'updated_by', 'old_status', 'new_status', 'created_at')
    list_filter   = ('new_status',)
    readonly_fields = ('created_at',)


class ShopContactInline(admin.TabularInline):
    model   = ShopContact
    extra   = 1
    fields  = ('contact_type', 'name', 'mobile', 'email', 'is_active')


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display  = ('shop_number', 'shop_name', 'mall', 'floor', 'is_active')
    list_filter   = ('mall', 'is_active', 'floor')
    search_fields = ('shop_number', 'shop_name')
    inlines       = [ShopContactInline]


@admin.register(ShopContact)
class ShopContactAdmin(admin.ModelAdmin):
    list_display  = ('name', 'contact_type', 'shop', 'mobile', 'email', 'is_active')
    list_filter   = ('contact_type', 'shop__mall', 'is_active')
    search_fields = ('name', 'mobile', 'email', 'shop__shop_number')


@admin.register(Designation)
class DesignationAdmin(admin.ModelAdmin):
    list_display  = ('name', 'department', 'level_order', 'is_active')
    list_filter   = ('department', 'is_active')
    ordering      = ('level_order',)
    help_text     = "Set level_order: 1=lowest (Technician), higher=senior. Escalation goes up the levels."