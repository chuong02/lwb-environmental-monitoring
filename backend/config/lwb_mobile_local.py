"""Separate read-only Mobile API on port 8001; reuses the existing database.

Run (laptop, reachable over Tailscale):
    python manage.py runserver 0.0.0.0:8001 --settings=config.lwb_mobile_local
Access is limited by LWB_MOBILE_ALLOWED_NETS (default: loopback + Tailscale 100.64.0.0/10).
Never expose this settings module through a public tunnel/reverse proxy.
"""
import os

from .settings import *  # noqa: F403,F401


def _csv_env(name, default):
    return [item.strip() for item in os.getenv(name, default).split(',') if item.strip()]


ROOT_URLCONF = 'config.lwb_mobile_urls'
DEBUG = False
# "*" is allowed: a phone reaches the laptop by its Tailscale IP, which changes the Host header.
ALLOWED_HOSTS = _csv_env('LWB_MOBILE_ALLOWED_HOSTS', '127.0.0.1,localhost,10.0.2.2,[::1]')
# CIDR ranges (besides loopback) whose REMOTE_ADDR may call the Mobile API.
LWB_MOBILE_ALLOWED_NETS = _csv_env('LWB_MOBILE_ALLOWED_NETS', '100.64.0.0/10')
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_PROXY_SSL_HEADER = None
USE_X_FORWARDED_HOST = False
LWB_MOBILE_LOCAL_ONLY = True
LWB_MOBILE_LIVE_SECONDS = 15
LWB_MOBILE_OFFLINE_SECONDS = 30
LWB_MOBILE_FUTURE_SECONDS = 10
# DATABASES, SECRET_KEY, INSTALLED_APPS and the MQTT worker remain unchanged.
