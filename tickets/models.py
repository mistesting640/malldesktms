from django.db import models
from django.conf import settings
from django.utils import timezone


class Mall(models.Model):
    name       = models.CharField(max_length=200)
    location   = models.CharField(max_length=300)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Department(models.Model):
    mall       = models.ForeignKey(Mall, on_delete=models.CASCADE, related_name='departments', null=True, blank=True,
                                   help_text="Leave blank to apply to all malls")
    name       = models.CharField(max_length=150)
    is_active  = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        mall_str = f" — {self.mall.name}" if self.mall else " — All Malls"
        return f"{self.name}{mall_str}"


class SubCategory(models.Model):
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='sub_categories')
    name       = models.CharField(max_length=150)
    is_active  = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Sub Category'
        verbose_name_plural = 'Sub Categories'

    def __str__(self):
        return f"{self.name} ({self.department.name})"


class Ticket(models.Model):
    # ── Type & Category ─────────────────────────────────
    COMPLAINT  = 'complaint'
    REQUEST    = 'request'
    FEEDBACK   = 'feedback'
    MAINTENANCE = 'maintenance'
    TYPE_CHOICES = [
        (COMPLAINT,   'Complaint'),
        (REQUEST,     'Request'),
        (FEEDBACK,    'Feedback'),
        (MAINTENANCE, 'Maintenance'),
    ]

    # ── Status ──────────────────────────────────────────
    OPEN       = 'open'
    IN_PROGRESS = 'in_progress'
    RESOLVED   = 'resolved'
    CLOSED     = 'closed'
    STATUS_CHOICES = [
        (OPEN,        'Open'),
        (IN_PROGRESS, 'In Progress'),
        (RESOLVED,    'Resolved'),
        (CLOSED,      'Closed'),
    ]

    # ── Priority ────────────────────────────────────────
    LOW      = 'low'
    MEDIUM   = 'medium'
    HIGH     = 'high'
    CRITICAL = 'critical'
    PRIORITY_CHOICES = [
        (LOW,      'Low'),
        (MEDIUM,   'Medium'),
        (HIGH,     'High'),
        (CRITICAL, 'Critical'),
    ]

    # ── Core Fields ─────────────────────────────────────
    ticket_id           = models.CharField(max_length=20, unique=True, editable=False)

    # Complainant info
    complainant_name    = models.CharField(max_length=200)
    complainant_company = models.CharField(max_length=200, blank=True)
    complainant_address = models.TextField(blank=True)

    # Classification
    mall                = models.ForeignKey(Mall, on_delete=models.PROTECT, related_name='tickets')
    ticket_type         = models.CharField(max_length=20, choices=TYPE_CHOICES, default=COMPLAINT)
    ticket_status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default=OPEN)
    department          = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='tickets')
    sub_category        = models.ForeignKey(SubCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets')
    priority            = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default=MEDIUM)

    # Content
    complaint_description = models.TextField()
    resolution          = models.TextField(blank=True)

    # Assignment
    created_by          = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                            related_name='created_tickets')
    assigned_to         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                            related_name='assigned_tickets')

    # Dates
    created_at          = models.DateTimeField(auto_now_add=True)
    due_date            = models.DateField(null=True, blank=True)
    resolved_on         = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.ticket_id} — {self.complainant_name}"

    def save(self, *args, **kwargs):
        if not self.ticket_id:
            # Auto-generate: TK-0001, TK-0002 …
            last = Ticket.objects.order_by('-id').first()
            next_id = (last.id + 1) if last else 1
            self.ticket_id = f"TK-{next_id:04d}"
        super().save(*args, **kwargs)

    @property
    def resolution_time(self):
        """Returns resolution time in hours if resolved"""
        if self.resolved_on and self.created_at:
            delta = self.resolved_on - self.created_at
            return round(delta.total_seconds() / 3600, 1)
        return None

    @property
    def is_overdue(self):
        if self.due_date and self.ticket_status not in [self.RESOLVED, self.CLOSED]:
            return timezone.now().date() > self.due_date
        return False

    @property
    def status_badge_class(self):
        mapping = {
            self.OPEN: 'badge-open',
            self.IN_PROGRESS: 'badge-progress',
            self.RESOLVED: 'badge-resolved',
            self.CLOSED: 'badge-closed',
        }
        return mapping.get(self.ticket_status, '')

    @property
    def priority_badge_class(self):
        mapping = {
            self.LOW: 'badge-low',
            self.MEDIUM: 'badge-medium',
            self.HIGH: 'badge-high',
            self.CRITICAL: 'badge-high',
        }
        return mapping.get(self.priority, '')


class TicketUpdate(models.Model):
    """Tracks every change/comment/status update on a ticket"""
    ticket     = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='updates')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    old_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20, blank=True)
    note       = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Update on {self.ticket.ticket_id} by {self.updated_by}"
