#!/usr/bin/env python3
"""Run Django tests against an in-memory SQLite DB, never the user's PostgreSQL."""
import argparse
import os
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--project', type=Path, required=True)
a = parser.parse_args()
project = a.project.expanduser().resolve()
if not (project / 'telemetry/mobile_v1/tests.py').exists():
    raise SystemExit('Run apply_backend.py first.')
sys.path.insert(0, str(project))
os.environ.pop('DJANGO_SETTINGS_MODULE', None)
try:
    import django
    from django.conf import settings
except ImportError:
    raise SystemExit('Activate the existing lwb-backend .venv first.')
settings.configure(
    SECRET_KEY='test-only-key-no-real-credentials',
    INSTALLED_APPS=['django.contrib.auth', 'django.contrib.contenttypes', 'rest_framework', 'telemetry'],
    DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
    MIGRATION_MODULES={'telemetry': None, 'auth': None, 'contenttypes': None},
    MIDDLEWARE=[], ROOT_URLCONF='config.lwb_mobile_urls',
    ALLOWED_HOSTS=['testserver'], USE_TZ=True, DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
    LWB_MOBILE_LOCAL_ONLY=True,
)
django.setup()
from django.test.utils import get_runner
print('TEST DATABASE: in-memory SQLite. Existing PostgreSQL is not opened.')
failures = get_runner(settings)(verbosity=2).run_tests(['telemetry.mobile_v1.tests'])
sys.exit(bool(failures))
