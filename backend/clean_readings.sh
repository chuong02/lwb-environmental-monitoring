#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ -x .venv/bin/python ]; then
    PY=.venv/bin/python
elif [ -x venv/bin/python ]; then
    PY=venv/bin/python
else
    PY=python3
fi

"$PY" manage.py shell -c '
from datetime import timedelta
from django.utils import timezone
from telemetry.models import SensorReading

cutoff = timezone.now() - timedelta(minutes=30)
count, _ = SensorReading.objects.filter(
    created_at__lt=cutoff
).delete()

print(f"Deleted {count} old readings")
'
