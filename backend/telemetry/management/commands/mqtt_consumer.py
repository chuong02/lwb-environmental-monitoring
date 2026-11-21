"""EMQX -> database worker.

Subscribes (base = MQTT_BASE_TOPIC, e.g. warehouse/site1/lwb):
  <base>/nodes/+/telemetry   SENSOR_DATA / LOCAL  -> SensorReading
  <base>/nodes/+/perf        PERF_*               -> PerfEvent
  <base>/gateway/+/status    gateway health       -> Gateway.status

Reliability: fixed client id + clean_session=False, so EMQX keeps the session
and queues QoS 1 messages while this worker is stopped (within the broker's
session expiry). Do not run two workers with the same MQTT_CLIENT_ID.

Retention: every minute, SensorReading older than
LWB_READING_RETENTION_MINUTES is deleted. Gateway/Node rows and PerfEvent
(test results) are kept.
"""
import json
import os
import ssl
import threading
import time
from datetime import timedelta

import paho.mqtt.client as mqtt
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from telemetry.models import Gateway, Node, PerfEvent, SensorReading


def _env(name, default=""):
    v = os.getenv(name)
    return default if v is None or v == "" else v


MQTT_HOST = _env("MQTT_HOST")
MQTT_PORT = int(_env("MQTT_PORT", "8883"))
MQTT_USERNAME = _env("MQTT_USERNAME")
MQTT_PASSWORD = _env("MQTT_PASSWORD")
MQTT_CA = _env("MQTT_CA")
MQTT_TLS = _env("MQTT_TLS", "true" if MQTT_PORT == 8883 else "false").lower() in ("1", "true", "yes")
MQTT_CLIENT_ID = _env("MQTT_CLIENT_ID", "lwb-django-consumer")


def _base_topic():
    base = _env("MQTT_BASE_TOPIC")
    if base:
        return base.strip("/")
    old = _env("MQTT_TOPIC", "warehouse/site1/lwb/nodes/+/telemetry")
    return old.split("/nodes/")[0].strip("/") if "/nodes/" in old else "warehouse/site1/lwb"


BASE = _base_topic()
TOPICS = [f"{BASE}/nodes/+/telemetry", f"{BASE}/nodes/+/perf", f"{BASE}/gateway/+/status"]

SENTINELS = {
    "hdc_temp_x10": -32768,
    "hdc_hum_x10": 65535,
    "light_raw": 65535,
    "bmp_temp_x10": -32768,
    "pressure_pa": -2147483648,
}
ROLE_BY_RECORD = {"LOCAL": "host", "SENSOR_DATA": "source"}


def _clean(data, key):
    v = data.get(key)
    if not isinstance(v, (int, float)) or v == SENTINELS.get(key):
        return None
    return int(v)


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


class Command(BaseCommand):
    help = "Subscribe EMQX (telemetry, perf, gateway status) and store into the database"

    def handle(self, *args, **options):
        if not MQTT_HOST:
            raise RuntimeError("MQTT_HOST is not configured (.env)")

        threading.Thread(target=self.retention_loop, daemon=True).start()

        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=MQTT_CLIENT_ID,
            protocol=mqtt.MQTTv311,
            clean_session=False,
        )
        if MQTT_USERNAME:
            client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        if MQTT_TLS:
            if MQTT_CA and os.path.exists(MQTT_CA):
                client.tls_set(ca_certs=MQTT_CA)
            else:
                # Windows / macOS: use the operating system certificate store.
                client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        client.on_connect = self.on_connect
        client.on_message = self.on_message
        client.on_disconnect = self.on_disconnect

        self.stdout.write(f"Connecting to {MQTT_HOST}:{MQTT_PORT} tls={MQTT_TLS} client_id={MQTT_CLIENT_ID}")
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
        client.loop_forever(retry_first_connection=True)

    # ------------------------------------------------------------------ MQTT
    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            self.stdout.write(self.style.SUCCESS(
                f"MQTT connected (session_present={flags.session_present})"))
            for t in TOPICS:
                client.subscribe(t, qos=1)
                self.stdout.write(f"Subscribed: {t}")
        else:
            self.stderr.write(f"MQTT connection failed: {reason_code}")

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        self.stdout.write(f"MQTT disconnected: {reason_code}")

    def on_message(self, client, userdata, message):
        close_old_connections()
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            topic = message.topic
            if topic.endswith("/status") and "/gateway/" in topic:
                self.store_status(payload)
            elif topic.endswith("/perf"):
                self.store_perf(payload)
            else:
                self.store_reading(payload)
        except Exception as exc:  # keep the worker alive on a bad message
            self.stderr.write(f"Message error on {message.topic}: {exc}")

    # -------------------------------------------------------------- helpers
    def _gateway_node(self, payload):
        gateway_id = payload.get("gateway_id")
        source = _int(payload.get("source"))
        recv_ts = parse_datetime(payload.get("recv_ts_utc") or "")
        if gateway_id is None or payload.get("event_id") is None or source is None or recv_ts is None:
            raise ValueError("gateway_id/event_id/source/recv_ts_utc missing")
        gateway, _ = Gateway.objects.get_or_create(gateway_id=gateway_id)
        node, _ = Node.objects.get_or_create(gateway=gateway, node_id=source)
        return gateway, node, recv_ts

    @staticmethod
    def _touch(obj, recv_ts):
        # Only move last_seen forward (an old backlog must not mark a node live).
        if obj.last_seen is None or recv_ts > obj.last_seen:
            obj.last_seen = recv_ts
            obj.save(update_fields=["last_seen"])

    @transaction.atomic
    def store_reading(self, payload):
        record_type = payload.get("record_type")
        if record_type not in ("SENSOR_DATA", "LOCAL"):
            return
        data = payload.get("data") or {}
        # unique == 0: the host has already seen this (run, source, seq). Usually a
        # node that restarted inside the same RUN_ID. Keep it (flagged) so last_seen moves.
        duplicate_seq = record_type == "SENSOR_DATA" and data.get("unique") == 0
        raw_payload = dict(payload)
        if duplicate_seq:
            raw_payload["duplicate_seq"] = True
        gateway, node, recv_ts = self._gateway_node(payload)

        role = ROLE_BY_RECORD[record_type]
        if node.role != role and not (node.role == "relay" and role == "source"):
            node.role = role
            node.save(update_fields=["role"])

        hop = _int(data.get("hop_est")) if data.get("hop_est_valid") == 1 else None
        delay = _int(data.get("delay_ms")) if data.get("delay_valid") == 1 else None
        _, created = SensorReading.objects.get_or_create(
            gateway=gateway,
            event_id=int(payload["event_id"]),
            recv_ts_utc=recv_ts,
            defaults={
                "node": node,
                "seq": payload.get("seq"),
                "host_time": _int(data.get("time")),
                "hdc_temp_x10": _clean(data, "hdc_temp_x10"),
                "hdc_hum_x10": _clean(data, "hdc_hum_x10"),
                "light_raw": _clean(data, "light_raw"),
                "bmp_temp_x10": _clean(data, "bmp_temp_x10"),
                "pressure_pa": _clean(data, "pressure_pa"),
                "run": _int(payload.get("run")),
                "delay_ms": delay,
                "hop_est": hop,
                "raw_payload": raw_payload,
            },
        )
        self._touch(gateway, recv_ts)
        self._touch(node, recv_ts)
        if created:
            if duplicate_seq:
                self.stdout.write(f"reading node={node.node_id} seq={payload.get('seq')} "
                                  "DUPLICATE_SEQ (node khởi động lại cùng RUN_ID?)")
            else:
                self.stdout.write(f"reading node={node.node_id} seq={payload.get('seq')} delay_ms={delay} hop={hop}")

    @transaction.atomic
    def store_perf(self, payload):
        gateway, node, recv_ts = self._gateway_node(payload)
        record_type = payload.get("record_type") or "PERF"
        data = payload.get("data") or {}
        if record_type == "PERF_CONFIG" and data.get("role"):
            role = str(data["role"]).lower()
            if node.role != role:
                node.role = role
                node.save(update_fields=["role"])
        PerfEvent.objects.get_or_create(
            gateway=gateway,
            event_id=int(payload["event_id"]),
            recv_ts_utc=recv_ts,
            defaults={"node": node, "record_type": record_type,
                      "run": _int(payload.get("run")), "data": data},
        )
        self._touch(gateway, recv_ts)
        self._touch(node, recv_ts)
        self.stdout.write(f"perf {record_type} node={node.node_id} run={payload.get('run')}")

    def store_status(self, payload):
        gateway_id = payload.get("gateway_id")
        if not gateway_id:
            return
        gateway, _ = Gateway.objects.get_or_create(gateway_id=gateway_id)
        gateway.status = payload
        gateway.status_ts = timezone.now()
        gateway.save(update_fields=["status", "status_ts"])

    # ------------------------------------------------------------ retention
    def retention_loop(self):
        minutes = settings.LWB_READING_RETENTION_MINUTES
        perf_hours = settings.LWB_PERF_RETENTION_HOURS
        while True:
            time.sleep(60)
            try:
                close_old_connections()
                if minutes > 0:
                    cutoff = timezone.now() - timedelta(minutes=minutes)
                    n, _ = SensorReading.objects.filter(recv_ts_utc__lt=cutoff).delete()
                    if n:
                        self.stdout.write(f"retention: deleted {n} readings older than {minutes} min")
                if perf_hours > 0:
                    cutoff = timezone.now() - timedelta(hours=perf_hours)
                    PerfEvent.objects.filter(recv_ts_utc__lt=cutoff).delete()
            except Exception as exc:
                self.stderr.write(f"retention error: {exc}")
