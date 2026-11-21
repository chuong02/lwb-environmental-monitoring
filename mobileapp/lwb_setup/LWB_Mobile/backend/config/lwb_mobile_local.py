"""Separate localhost-only Mobile API on port 8001; reuse existing PostgreSQL.

Run: python manage.py runserver 127.0.0.1:8001 --settings=config.lwb_mobile_local
Never expose this settings module through a public tunnel/reverse proxy.
"""
from .settings import *  # noqa: F403,F401

ROOT_URLCONF = 'config.lwb_mobile_urls'
DEBUG = False
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '10.0.2.2', '[::1]']
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_PROXY_SSL_HEADER = None
USE_X_FORWARDED_HOST = False
LWB_MOBILE_LOCAL_ONLY = True
LWB_MOBILE_LIVE_SECONDS = 15
LWB_MOBILE_OFFLINE_SECONDS = 30
LWB_MOBILE_FUTURE_SECONDS = 10
# DATABASES, SECRET_KEY, INSTALLED_APPS and the MQTT worker remain unchanged.
