from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-change-this-in-production-use-env-variable'

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
    'tickets',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'malldesk.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'malldesk.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# ─── EMAIL ────────────────────────────────────────────────────────────────────
EMAIL_BACKEND       = 'malldesk.custom_email_backend.SSLBypassEmailBackend'
EMAIL_HOST          = 'smtp.dreamhost.com'
EMAIL_PORT          = 465
EMAIL_USE_TLS       = False
EMAIL_USE_SSL       = False  # handled inside custom backend
EMAIL_HOST_USER     = 'mis.accounts@vsquareservices.com'
EMAIL_HOST_PASSWORD = 'Legend@7570#Square'
DEFAULT_FROM_EMAIL  = 'MallDesk <mis.accounts@vsquareservices.com>'

# ─── WHO GETS EMAILS ──────────────────────────────────────────────────────────
# BCC on every email — invisible to customer/manager
MALLDESK_ADMIN_EMAILS = [
    'mis@vsquareservices.com',
]
# CC on every email — visible to recipients
MALLDESK_CC_EMAILS = [
    # 'another@vsquareservices.com',
]

# ─── WHATSAPP ─────────────────────────────────────────────────────────────────
# Number with country code, no + or spaces. India example: 919876543210
WHATSAPP_NOTIFY_NUMBER = '917503020176'   # ← change to your number

# ─── TICKET REMINDERS ─────────────────────────────────────────────────────────
# Send reminder if ticket is Open/In Progress for this many hours without update
TICKET_REMINDER_HOURS          = 2    # remind after 2 hours
TICKET_REMINDER_CHECK_INTERVAL = 30   # background check every 30 minutes
TICKET_REMINDER_MAX            = 5    # max reminders per ticket (stops spam)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'tickets': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
 