"""
Django production settings.
"""
from .base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='192.168.1.236', cast=lambda v: [s.strip() for s in v.split(',')])

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='klikk_bi_etl'),
        'USER': config('DB_USER', default='klikk_user'),
        'PASSWORD': config('DB_PASSWORD', default='StrongPasswordHere'),
        'HOST': config('DB_HOST', default='127.0.0.1'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 600,  # Reuse connections for 10 minutes (connection pooling)
        'OPTIONS': {
            'connect_timeout': 10,
        }
    }
}

# Security settings for production
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=False, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=False, cast=bool)

# CSRF trusted origins for production
# Add port if using one (e.g., http://192.168.1.236:8000)
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='http://192.168.1.236,https://192.168.1.236,http://192.168.1.236:8000,https://192.168.1.236:8000',
    cast=lambda v: [s.strip() for s in v.split(',')]
)

# Static files served by gunicorn/nginx in production
STATIC_ROOT = BASE_DIR / 'staticfiles'
