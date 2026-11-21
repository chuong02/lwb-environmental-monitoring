#!/usr/bin/env python3
"""SQLite outbox -> MQTT (EMQX) publisher for the LWB gateway.

Changes vs. the first version
- Publishes a whole batch, then waits for all PUBACKs (much faster than
  waiting up to 10 s per message on a cloud broker).
- Newest rows first, so the dashboard shows live data immediately; the older
  backlog after an outage is still drained, just behind live data.
- Publishes performance records (PERF_*) too, on .../nodes/<id>/perf.
- Rows older than PUBLISH_MAX_AGE_HOURS are marked expired (published=2) and
  stay in SQLite only; set 0 to publish everything.
- Publishes a retained gateway status message (UART ok/bad counters, backlog)
  and a last-will "offline" message.

published column: 0 pending, 1 sent, 2 expired (not sent), 3 corrupted UART line.
"""
import json
import logging
import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import paho.mqtt.client as mqtt


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def env(name, default=None):
    value = os.getenv(name)
    return default if value is None or value == "" else value


DB_PATH = Path(env("DB_PATH", "/var/lib/lwb-gateway/lwb.db"))

MQTT_HOST = env("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(env("MQTT_PORT", "1883"))
MQTT_USERNAME = env("MQTT_USERNAME", "")
MQTT_PASSWORD = env("MQTT_PASSWORD", "")
MQTT_TLS = env("MQTT_TLS", "false").lower() in ("1", "true", "yes", "on")
MQTT_CA = env("MQTT_CA", "/etc/ssl/certs/ca-certificates.crt")
MQTT_BASE_TOPIC = env("MQTT_BASE_TOPIC", "company/site1/lwb").strip("/")
MQTT_CLIENT_ID = env("MQTT_CLIENT_ID", "border-router-lwb")
GATEWAY_ID = env("GATEWAY_ID", "border-router")
BATCH_SIZE = int(env("MQTT_BATCH_SIZE", "50"))
IDLE_SEC = float(env("MQTT_IDLE_SEC", "0.5"))
MAX_AGE_HOURS = float(env("PUBLISH_MAX_AGE_HOURS", "24"))
STATUS_SEC = float(env("GATEWAY_STATUS_SEC", "15"))

TELEMETRY_TYPES = ("SENSOR_DATA", "LOCAL")
PERF_TYPES = ("PERF_CONFIG", "PERF_SUMMARY", "PERF_SOURCE_SUMMARY", "PERF_REPORT",
              "PERF_START", "PERF_ABORT", "PERF_HOP_SUMMARY", "REJOIN_REQUEST")
PUBLISH_TYPES = TELEMETRY_TYPES + PERF_TYPES

STATUS_TOPIC = f"{MQTT_BASE_TOPIC}/gateway/{GATEWAY_ID}/status"

connected = threading.Event()


def open_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def sanitize_topic_token(value):
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value))
    return value.strip("_") or "unknown"


def build_topic(record_type, source):
    node = sanitize_topic_token(source if source is not None else "unknown")
    if record_type in TELEMETRY_TYPES:
        return f"{MQTT_BASE_TOPIC}/nodes/{node}/telemetry"
    return f"{MQTT_BASE_TOPIC}/nodes/{node}/perf"


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        logging.info("MQTT connected")
        client.publish(STATUS_TOPIC, json.dumps({"gateway_id": GATEWAY_ID, "online": True,
                                                 "ts_utc": utc_now_iso()}), qos=1, retain=True)
        connected.set()
    else:
        logging.error("MQTT connect rejected: %s", reason_code)
        connected.clear()


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    logging.warning("MQTT disconnected: %s", reason_code)
    connected.clear()


def make_client():
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=MQTT_CLIENT_ID,
        protocol=mqtt.MQTTv311,
        clean_session=False,
    )
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    if MQTT_TLS:
        client.tls_set(ca_certs=MQTT_CA)
    client.will_set(STATUS_TOPIC, json.dumps({"gateway_id": GATEWAY_ID, "online": False}),
                    qos=1, retain=True)
    client.max_inflight_messages_set(max(20, BATCH_SIZE))
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    return client


def iso_hours_ago(hours=0, minutes=0):
    t = datetime.now(timezone.utc) - timedelta(hours=hours, minutes=minutes)
    return t.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def expire_old_rows(conn):
    if MAX_AGE_HOURS <= 0:
        return 0
    cur = conn.execute(
        "UPDATE events SET published = 2 WHERE published = 0 AND recv_ts_utc < ?",
        (iso_hours_ago(hours=MAX_AGE_HOURS),))
    conn.commit()
    return cur.rowcount


def load_batch(conn):
    marks = ",".join("?" * len(PUBLISH_TYPES))
    return conn.execute(
        f"""
        SELECT id, recv_ts_utc, record_type, run, source, seq, payload_json
        FROM events
        WHERE published = 0 AND record_type IN ({marks}) AND source IS NOT NULL
        ORDER BY id DESC
        LIMIT ?
        """,
        (*PUBLISH_TYPES, BATCH_SIZE),
    ).fetchall()


def mark_published(conn, ids):
    ts = utc_now_iso()
    conn.executemany(
        "UPDATE events SET published = 1, published_ts_utc = ? WHERE id = ?",
        [(ts, i) for i in ids])
    conn.commit()


def gateway_status(conn):
    row = conn.execute(
        """
        SELECT
          SUM(CASE WHEN record_type = 'UART_BAD' THEN 1 ELSE 0 END) AS bad,
          SUM(CASE WHEN record_type <> 'UART_BAD' THEN 1 ELSE 0 END) AS good
        FROM events WHERE recv_ts_utc >= ?
        """, (iso_hours_ago(minutes=5),)).fetchone()
    marks = ",".join("?" * len(PUBLISH_TYPES))
    backlog = conn.execute(
        f"SELECT COUNT(*) FROM events WHERE published = 0 AND record_type IN ({marks})",
        PUBLISH_TYPES).fetchone()[0]
    bad, good = row["bad"] or 0, row["good"] or 0
    return {
        "gateway_id": GATEWAY_ID,
        "online": True,
        "ts_utc": utc_now_iso(),
        "uart_lines_5min": good + bad,
        "uart_bad_5min": bad,
        "uart_bad_pct_5min": round(100.0 * bad / (good + bad), 2) if good + bad else None,
        "backlog": backlog,
    }


def publish_batch(client, conn, rows):
    pending = []
    for row in rows:
        try:
            data = json.loads(row["payload_json"])
        except json.JSONDecodeError:
            data = {"_raw_payload_json": row["payload_json"]}
        payload = {
            "schema_version": 2,
            "event_id": row["id"],
            "gateway_id": GATEWAY_ID,
            "recv_ts_utc": row["recv_ts_utc"],
            "record_type": row["record_type"],
            "run": row["run"],
            "source": row["source"],
            "seq": row["seq"],
            "data": data,
        }
        info = client.publish(build_topic(row["record_type"], row["source"]),
                              json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                              qos=1, retain=False)
        pending.append((row["id"], info))

    done = []
    deadline = time.monotonic() + 15
    for event_id, info in pending:
        try:
            info.wait_for_publish(timeout=max(0.1, deadline - time.monotonic()))
        except (RuntimeError, ValueError):
            break
        if info.is_published():
            done.append(event_id)
    if done:
        mark_published(conn, done)
        logging.info("Published %d/%d (newest event_id=%s)", len(done), len(pending), pending[0][0])
    return len(done) == len(pending)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}")

    conn = open_db()
    client = make_client()

    logging.info("Starting MQTT publisher broker=%s:%s tls=%s base_topic=%s",
                 MQTT_HOST, MQTT_PORT, MQTT_TLS, MQTT_BASE_TOPIC)

    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_start()
    last_status = last_expire = -1e9

    try:
        while True:
            if not connected.wait(timeout=5):
                logging.warning("Waiting for MQTT broker...")
                continue

            now = time.monotonic()
            if now - last_expire > 300:
                n = expire_old_rows(conn)
                if n:
                    logging.info("Expired %d rows older than %.0f h (kept in SQLite)", n, MAX_AGE_HOURS)
                last_expire = now
            if now - last_status > STATUS_SEC:
                client.publish(STATUS_TOPIC, json.dumps(gateway_status(conn)), qos=1, retain=True)
                last_status = now

            rows = load_batch(conn)
            if not rows:
                time.sleep(IDLE_SEC)
                continue
            if not publish_batch(client, conn, rows):
                logging.warning("Some PUBACKs missing; those rows will be retried")
                time.sleep(1)

    except KeyboardInterrupt:
        logging.info("Publisher stopping")
    finally:
        client.loop_stop()
        client.disconnect()
        conn.close()


if __name__ == "__main__":
    main()
