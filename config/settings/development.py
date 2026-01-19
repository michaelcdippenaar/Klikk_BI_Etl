"""
Django development settings.
"""
from .base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1,192.168.1.136', cast=lambda v: [s.strip() for s in v.split(',')])

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'klikk_bi_etl',
        'USER': 'klikk_user',
        'PASSWORD': 'StrongPasswordHere',
        'HOST': '192.168.1.236',
        'PORT': '5432',
        'CONN_MAX_AGE': 600,  # Reuse connections for 10 minutes (connection pooling)
        'OPTIONS': {
            'connect_timeout': 10,
        }
    }
}