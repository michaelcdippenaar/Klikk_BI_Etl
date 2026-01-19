"""
Django settings module that loads environment-specific settings.
Uses DJANGO_ENV environment variable to determine which settings to load.
Defaults to 'development' if not set.
"""
import os
from decouple import config

# Get the environment (default to 'development')
env = config('DJANGO_ENV', default='development').lower()

if env == 'production':
    from .production import *
elif env == 'staging':
    from .staging import *
else:  # default to development
    from .development import *
