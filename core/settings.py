"""
Django settings — MindMap Tasks (Jinja2 + HTMX).
Reads secrets and env-specific values from environment variables.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool = False) -> bool:
    """Parse truthy env values (1, true, yes, on); empty uses default."""
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in ('1', 'true', 'yes', 'on')


# ── Security ──────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-dev-only-replace-in-production-with-long-random-string-xyz',
)
# Optional Fernet key for task title encryption-at-rest.
# Must be a urlsafe base64-encoded 32-byte key when provided.
TASK_ENCRYPTION_KEY = os.environ.get('TASK_ENCRYPTION_KEY', '').strip()

# Default False: set DEBUG=True in .env for local debugging (never on public servers).
DEBUG = _env_bool('DEBUG', default=False)

_raw_hosts = os.environ.get('ALLOWED_HOSTS', '127.0.0.1,localhost,testserver')
ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(',') if h.strip()]

# HTTPS sites behind a reverse proxy (required for CSRF from Django 4+)
_raw_csrf = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _raw_csrf.split(',') if o.strip()]
if not CSRF_TRUSTED_ORIGINS:
    # Fallback for deployments where CSRF_TRUSTED_ORIGINS was not configured.
    derived_hosts = [h for h in ALLOWED_HOSTS if h not in {'localhost', '127.0.0.1', 'testserver'}]
    CSRF_TRUSTED_ORIGINS = [f'https://{h}' for h in derived_hosts if h and '*' not in h]

# ── Apps ──────────────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'users',
    'billing',
    'teams',
    'planner',
    'staff_dashboard',
]

# ── Middleware ────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',       # static files in prod
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'core.middleware.NoCacheHtmlMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

# ── Templates ─────────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.jinja2.Jinja2',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': False,
        'OPTIONS': {
            'environment': 'core.jinja_env.environment',
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.csrf',
                'users.context_processors.account_profile',
                'planner.context_processors.workspace_chrome',
            ],
        },
    },
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# ── Database ──────────────────────────────────────────────────────────────────
# Prefer POSTGRES_HOST (Docker / explicit config) — avoids URL-encoding issues in DATABASE_URL.
_postgres_host = os.environ.get('POSTGRES_HOST', '').strip()
_db_url = os.environ.get('DATABASE_URL', '').strip()

if _postgres_host:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('POSTGRES_DB', 'ntarque'),
            'USER': os.environ.get('POSTGRES_USER', 'ntarque'),
            'PASSWORD': os.environ.get('POSTGRES_PASSWORD', ''),
            'HOST': _postgres_host,
            'PORT': os.environ.get('POSTGRES_PORT', '5432'),
            'CONN_MAX_AGE': 600,
        }
    }
elif _db_url.startswith('postgres'):
    try:
        import dj_database_url  # noqa: PLC0415
        DATABASES = {'default': dj_database_url.config(default=_db_url, conn_max_age=600)}
    except ImportError as exc:
        raise RuntimeError('dj-database-url is required when DATABASE_URL is set') from exc
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ── Password validation ───────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ── Internationalisation ──────────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = os.environ.get('TIME_ZONE', 'UTC')
USE_I18N = True
USE_TZ = True

# ── Static files ──────────────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
_static_src = BASE_DIR / 'static'
STATICFILES_DIRS = [_static_src] if _static_src.is_dir() else []
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Auth redirects ────────────────────────────────────────────────────────────
LOGIN_URL = 'users:login'
LOGIN_REDIRECT_URL = 'planner:board_personal'
LOGOUT_REDIRECT_URL = 'users:login'

# ── Session ───────────────────────────────────────────────────────────────────
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # 2 weeks

# ── Production security (only when DEBUG=False) ───────────────────────────────
# USE_HTTPS=true when users hit the site over HTTPS (or TLS terminates at a proxy
# and you set X-Forwarded-Proto). For HTTP-only (e.g. raw droplet IP), keep False.
USE_HTTPS = _env_bool('USE_HTTPS', default=False)

if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SESSION_COOKIE_SECURE = USE_HTTPS
    CSRF_COOKIE_SECURE = USE_HTTPS
    if USE_HTTPS:
        SECURE_HSTS_SECONDS = 31536000
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True
        SECURE_HSTS_PRELOAD = True
        SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    else:
        SECURE_HSTS_SECONDS = 0
        SECURE_HSTS_INCLUDE_SUBDOMAINS = False
        SECURE_HSTS_PRELOAD = False
