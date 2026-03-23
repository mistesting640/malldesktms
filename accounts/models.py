from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', User.ADMIN)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    # Role choices
    EXTERNAL = 'external'   # Customer / shop owner outside the company
    INTERNAL = 'internal'   # Employee assigned to handle tickets
    MANAGER  = 'manager'    # Can assign tickets, track tasks
    ADMIN    = 'admin'      # Full access, creates internal users

    ROLE_CHOICES = [
        (EXTERNAL, 'External User'),
        (INTERNAL, 'Internal User'),
        (MANAGER,  'Manager'),
        (ADMIN,    'Admin'),
    ]

    email           = models.EmailField(unique=True)
    full_name       = models.CharField(max_length=150)
    mobile          = models.CharField(max_length=20, blank=True)
    role            = models.CharField(max_length=20, choices=ROLE_CHOICES, default=EXTERNAL)

    # External user fields
    business_name   = models.CharField(max_length=200, blank=True, help_text="Shop/Business name for external users")
    project         = models.ForeignKey(
        'tickets.Mall', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='external_users'
    )

    # Internal user fields
    department      = models.ForeignKey(
        'tickets.Department', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='members'
    )
    designation     = models.ForeignKey(
        'tickets.Designation', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='users'
    )

    is_active       = models.BooleanField(default=True)
    is_staff        = models.BooleanField(default=False)
    date_joined     = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['full_name']

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-date_joined']

    def __str__(self):
        return f"{self.full_name} ({self.get_role_display()})"

    @property
    def is_external(self):
        return self.role == self.EXTERNAL

    @property
    def is_internal(self):
        return self.role in [self.INTERNAL, self.MANAGER, self.ADMIN]

    @property
    def is_manager_or_admin(self):
        return self.role in [self.MANAGER, self.ADMIN]


class UserRemovalLog(models.Model):
    """Tracks when and why a user was deactivated."""
    user        = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='removal_logs'
    )
    removed_by  = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='removals_done'
    )
    reason      = models.TextField()
    removed_at  = models.DateTimeField(auto_now_add=True)
    reactivated = models.BooleanField(default=False)
    reactivated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-removed_at']

    def __str__(self):
        return f"{self.user.full_name} removed on {self.removed_at:%d %b %Y}"