"""
Django staging settings.
"""
from .base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1,192.168.1.236', cast=lambda v: [s.strip() for s in v.split(',')])

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


# Update JWT signing key


# Static files configuration for staging
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files (if you have user uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Use WhiteNoise to serve static files when DEBUG=False
# Install with: pip install whitenoise
# Add 'whitenoise.middleware.WhiteNoiseMiddleware' to MIDDLEWARE (already in base.py)
# WhiteNoise should be added after SecurityMiddleware and before other middleware
# For now, we'll serve static files via URL patterns (see urls.py)

# Security settings for staging
SECURE_SSL_REDIRECT = False  # Set to True if using HTTPS
SESSION_COOKIE_SECURE = False  # Set to True if using HTTPS
CSRF_COOKIE_SECURE = False  # Set to True if using HTTPS

# CSRF trusted origins for staging
# Add port if using one (e.g., http://192.168.1.236:8000)
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='http://localhost,http://127.0.0.1,http://192.168.1.236,http://localhost:8000,http://127.0.0.1:8000,http://192.168.1.236:8000',
    cast=lambda v: [s.strip() for s in v.split(',')]
)


