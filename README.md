# MallDesk — Ticket Management System

A full Django-based ticket/complaint management system for mall operations.
Built with two user types, department routing, manager assignment,
and **automatic email notifications at every stage**.

---

## Features

### Users
| Role | Description |
|------|-------------|
| **External** | Customer/shop owner — self-registers, submits & tracks own tickets |
| **Internal** | Employee — handles assigned tickets, adds updates |
| **Manager** | Assigns tickets to internal users, tracks all tasks |
| **Admin** | Full access, creates internal users |

### Email Notifications (all 8 triggers)
1. **Ticket Created** → Confirmation to customer + alert to department manager
2. **Ticket Assigned** → Notification to assigned internal user + customer informed
3. **Status Updated** → Customer gets update + manager notified of status change
4. **Ticket Resolved** → Resolution summary to customer + resolution time to manager

---

## Setup

### 1. Install
```bash
pip install -r requirements.txt
```

### 2. Migrations
```bash
python manage.py makemigrations accounts
python manage.py makemigrations tickets
python manage.py migrate
```

### 3. Create Admin
```bash
python manage.py createsuperuser
```

### 4. Seed Data (via /admin/)
- Add Malls → Departments → Sub Categories
- Create Internal Users from `/accounts/users/create/`

### 5. Configure Email in `malldesk/settings.py`

**Development (console output — default):**
```python
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```

**Production with Gmail:**
```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your@gmail.com'
EMAIL_HOST_PASSWORD = 'your-gmail-app-password'
DEFAULT_FROM_EMAIL = 'MallDesk <your@gmail.com>'
```
> Gmail requires an App Password (not login password).
> Google Account → Security → 2-Step Verification → App Passwords

**Production with SendGrid:**
```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.sendgrid.net'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'apikey'
EMAIL_HOST_PASSWORD = 'your-sendgrid-api-key'
```

### 6. Run
```bash
python manage.py runserver
```

---

## URL Reference

| URL | Description | Access |
|-----|-------------|--------|
| `/` | Dashboard | All logged-in |
| `/accounts/login/` | Login | Public |
| `/accounts/register/` | External registration | Public |
| `/accounts/users/` | User list | Manager/Admin |
| `/accounts/users/create/` | Create internal user | Manager/Admin |
| `/tickets/` | All tickets | All |
| `/tickets/new/` | Create ticket | All |
| `/tickets/<id>/` | Ticket detail | All (filtered) |
| `/tickets/<id>/assign/` | Assign ticket | Manager/Admin |
| `/tickets/<id>/update/` | Add update/note | Internal |
| `/tickets/<id>/resolve/` | Resolve ticket | Internal |
| `/admin/` | Django admin | Superuser |

---

## Permissions

| Action | External | Internal | Manager | Admin |
|--------|----------|----------|---------|-------|
| Create ticket | ✅ | ✅ | ✅ | ✅ |
| View own tickets | ✅ | — | — | — |
| View all tickets | ❌ | ✅ | ✅ | ✅ |
| Edit/Delete (Open only) | ✅ | ❌ | ❌ | ❌ |
| Assign ticket | ❌ | ❌ | ✅ | ✅ |
| Add updates | ❌ | ✅ | ✅ | ✅ |
| Resolve ticket | ❌ | ✅ | ✅ | ✅ |
| Create internal users | ❌ | ❌ | ✅ | ✅ |

---

## Production Checklist
- [ ] `DEBUG = False`
- [ ] `SECRET_KEY` from environment variable
- [ ] PostgreSQL configured
- [ ] Real SMTP email configured
- [ ] `python manage.py collectstatic`
- [ ] `ALLOWED_HOSTS` set to your domain
- [ ] gunicorn + nginx

## Tech Stack
- Django 4.2, SQLite/PostgreSQL, Django email (SMTP/SendGrid), HTML/CSS/JS
# malldesktms
