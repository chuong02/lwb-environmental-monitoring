"""Pure helpers shared by the API and tests. No third-party dependencies."""
from datetime import datetime

STATUSES = ('live', 'stale', 'offline', 'never', 'clock_error')


def node_status(last_seen: datetime | None, now: datetime, live_s=15, offline_s=30, future_s=10):
    if last_seen is None:
        return 'never'
    age = (now - last_seen).total_seconds()
    if age < -future_s:
        return 'clock_error'
    if age <= live_s:
        return 'live'
    if age <= offline_s:
        return 'stale'
    return 'offline'


def bounded_int(value, default, maximum, name):
    if value is None:
        return default
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be an integer.') from None
    if n < 1:
        raise ValueError(f'{name} must be greater than zero.')
    return min(n, maximum)


def policy(live_s=15, offline_s=30, future_s=10):
    if not 0 < live_s < offline_s or future_s < 0:
        raise ValueError('Require 0 < live_seconds < offline_seconds and future_seconds >= 0.')
    return dict(live_seconds=live_s, offline_seconds=offline_s, future_seconds=future_s)


def number(value, scale=1, sentinel=None):
    if value is None or (sentinel is not None and value == sentinel):
        return None
    return value / scale if scale != 1 else value


def reading_data(reading):
    """The same engineering units as the existing telemetry API; null stays null."""
    pressure = reading.pressure_pa
    if pressure is not None and pressure <= -2000000000:
        pressure = None
    return {
        'event_id': reading.event_id,
        'gateway_id': reading.gateway.gateway_id,
        'node_id': reading.node.node_id,
        'seq': reading.seq,
        'recv_ts_utc': reading.recv_ts_utc.isoformat(),
        'temperature_c': number(reading.hdc_temp_x10, 10, -32768),
        'humidity_percent': number(reading.hdc_hum_x10, 10, 65535),
        'light_raw': number(reading.light_raw, sentinel=65535),
        'bmp_temperature_c': number(reading.bmp_temp_x10, 10, -32768),
        'pressure_pa': pressure,
    }
