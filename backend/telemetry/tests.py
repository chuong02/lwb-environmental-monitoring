import importlib
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import clear_url_caches
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from telemetry.management.commands.mqtt_consumer import Command
from telemetry.models import Gateway, Node, PerfEvent, SensorReading
from telemetry.status import effective_last_seen, is_online


def msg(event_id, record_type, source, data, ts=None, run=7):
    ts = ts or timezone.now()
    return {"schema_version": 2, "event_id": event_id, "gateway_id": "gw", "run": run,
            "recv_ts_utc": ts.isoformat(), "record_type": record_type, "source": source,
            "seq": data.get("seq"), "data": data}


class ConsumerAndApiTests(TestCase):
    def setUp(self):
        self.cmd = Command()

    def test_reading_perf_and_overview(self):
        self.cmd.store_reading(msg(1, "SENSOR_DATA", 3, {"seq": 1, "unique": 1, "hdc_temp_x10": 281,
                                                          "hdc_hum_x10": 65535, "delay_ms": 90, "delay_valid": 1,
                                                          "hop_est": 2, "hop_est_valid": 1}))
        self.cmd.store_reading(msg(2, "SENSOR_DATA", 3, {"seq": 1, "unique": 0}))  # duplicate copy
        self.cmd.store_reading(msg(3, "LOCAL", 1, {"seq": 5, "hdc_temp_x10": 300}))
        self.cmd.store_perf(msg(4, "PERF_SUMMARY", 3, {"source": 3, "expected": 100, "received": 50,
                                                        "final": 0, "application_yield_x100": -1,
                                                        "delay_count": 0}))
        r = SensorReading.objects.get(node__node_id=3, event_id=1)
        self.assertEqual((r.hdc_temp_x10, r.hdc_hum_x10, r.delay_ms, r.hop_est), (281, None, 90, 2))
        self.assertNotIn("duplicate_seq", r.raw_payload)
        self.assertEqual(SensorReading.objects.count(), 3)  # duplicate copy is stored too, flagged
        self.assertEqual(Node.objects.get(node_id=1).role, "host")

        o = self.client.get("/api/overview/?online=1").json()
        self.assertEqual([n["node_id"] for n in o["nodes"]], [1, 3])
        p = self.client.get("/api/perf/").json()
        self.assertEqual(p["run"], 7)
        self.assertEqual(p["sources"][0]["progress_pct"], 50.0)
        self.assertIsNone(p["sources"][0]["application_yield_pct"])

    def test_host_with_only_recent_perf_event_is_online(self):
        now = timezone.now()
        self.cmd.store_perf(msg(1, "PERF_CONFIG", 1, {"role": "host"}, ts=now - timedelta(seconds=20)))
        node = Node.objects.get(node_id=1)
        self.assertEqual(SensorReading.objects.count(), 0)
        self.assertEqual(node.last_seen, now - timedelta(seconds=20))  # perf moves last_seen
        # Even a node whose last_seen was never set: PerfEvent alone is enough.
        Node.objects.filter(pk=node.pk).update(last_seen=None)
        host = self.client.get("/api/overview/").json()["nodes"][0]
        self.assertEqual(host["role"], "host")
        self.assertTrue(host["online"])

    def test_host_offline_after_45_seconds_without_perf(self):
        now = timezone.now()
        self.cmd.store_perf(msg(1, "PERF_CONFIG", 1, {"role": "host"}, ts=now - timedelta(seconds=40)))
        self.assertTrue(self.client.get("/api/overview/").json()["nodes"][0]["online"])
        PerfEvent.objects.update(recv_ts_utc=now - timedelta(seconds=60))
        Node.objects.update(last_seen=now - timedelta(seconds=60))
        self.assertFalse(self.client.get("/api/overview/").json()["nodes"][0]["online"])

    def _host_and_node2(self, node2_age):
        now = timezone.now()
        self.cmd.store_perf(msg(1, "PERF_CONFIG", 1, {"role": "host"}, ts=now - timedelta(seconds=300)))
        self.cmd.store_reading(msg(2, "SENSOR_DATA", 2, {"seq": 1, "unique": 1}, ts=now - timedelta(seconds=node2_age)))
        return now

    def _host_views(self):
        web = next(n for n in self.client.get("/api/overview/").json()["nodes"] if n["node_id"] == 1)
        with override_settings(ROOT_URLCONF="config.lwb_mobile_urls", LWB_MOBILE_LOCAL_ONLY=True):
            mob = self.client.get("/api/mobile/v1/nodes/").json()["results"]
        return web, next(n for n in mob if n["node_id"] == 1)

    def test_host_online_when_other_node_of_gateway_just_sent(self):
        self._host_and_node2(node2_age=2)
        web, mob = self._host_views()
        self.assertTrue(web["online"])
        self.assertEqual(mob["status"], "live")
        self.assertEqual(mob["role"], "host")

    def test_host_offline_when_no_node_sent_for_60_seconds(self):
        self._host_and_node2(node2_age=60)
        PerfEvent.objects.update(recv_ts_utc=timezone.now() - timedelta(seconds=60))
        Node.objects.update(last_seen=timezone.now() - timedelta(seconds=60))
        web, mob = self._host_views()
        self.assertFalse(web["online"])
        self.assertEqual(mob["status"], "offline")

    def test_old_backlog_does_not_mark_node_live(self):
        now = timezone.now()
        self.cmd.store_reading(msg(10, "LOCAL", 1, {"seq": 1}, ts=now))
        self.cmd.store_reading(msg(9, "LOCAL", 1, {"seq": 0}, ts=now - timedelta(hours=3)))
        self.assertEqual(Node.objects.get(node_id=1).last_seen, now)

    def test_duplicate_seq_is_stored_flagged_and_updates_last_seen(self):
        t1 = timezone.now() - timedelta(seconds=30)
        t2 = timezone.now()
        self.cmd.store_reading(msg(1, "SENSOR_DATA", 3, {"seq": 1, "unique": 1}, ts=t1))
        self.cmd.store_reading(msg(2, "SENSOR_DATA", 3, {"seq": 1, "unique": 0}, ts=t2))
        self.assertEqual(SensorReading.objects.count(), 2)
        first, second = SensorReading.objects.order_by("event_id")
        self.assertNotIn("duplicate_seq", first.raw_payload)
        self.assertIs(second.raw_payload["duplicate_seq"], True)
        node = Node.objects.get(node_id=3)
        self.assertEqual(node.last_seen, t2)
        self.assertEqual(node.gateway.last_seen, t2)

    def test_event_id_reuse_after_gateway_db_reset(self):
        now = timezone.now()
        self.cmd.store_reading(msg(1, "LOCAL", 1, {"seq": 1}, ts=now - timedelta(minutes=1)))
        self.cmd.store_reading(msg(1, "LOCAL", 1, {"seq": 2}, ts=now))
        self.assertEqual(SensorReading.objects.count(), 2)
        self.assertEqual(PerfEvent.objects.count(), 0)


class PublicModeTests(TestCase):
    """LWB_PUBLIC=1 (Tailscale Funnel): no /admin/, dashboard API still works."""

    @staticmethod
    def _reload_urls():
        import config.urls
        importlib.reload(config.urls)  # urlpatterns depend on settings.LWB_PUBLIC at import
        clear_url_caches()

    def tearDown(self):
        self._reload_urls()  # back to the normal URLconf for the other tests

    def test_admin_registered_when_not_public(self):
        self._reload_urls()
        self.assertEqual(self.client.get("/admin/").status_code, 302)  # redirect to login

    def test_public_mode_hides_admin_but_serves_api(self):
        with override_settings(LWB_PUBLIC=True):
            self._reload_urls()
            self.assertEqual(self.client.get("/admin/").status_code, 404)
            self.assertEqual(self.client.get("/admin/login/").status_code, 404)
            self.assertEqual(self.client.get("/api/overview/").status_code, 200)
            self.assertEqual(self.client.get("/api/perf/").status_code, 200)
            self.assertEqual(self.client.get("/api/nodes/").status_code, 200)
            info = self.client.get("/api/info/").json()
            self.assertNotIn("admin", info["endpoints"])

    def _import_settings(self, **env):
        """Import config.settings in a fresh interpreter (.env never overrides set variables)."""
        child = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "LWB_"))}
        child.update(env)
        code = ("import json, config.settings as s; print(json.dumps({'debug': s.DEBUG, "
                "'hosts': s.ALLOWED_HOSTS, 'csrf': s.CSRF_TRUSTED_ORIGINS, "
                "'proxy': s.SECURE_PROXY_SSL_HEADER}))")
        return subprocess.run([sys.executable, "-c", code], cwd=str(settings.BASE_DIR), env=child,
                              capture_output=True, text=True)

    def test_public_settings_require_real_secret_key(self):
        for key in ("", "django-insecure-replace-this"):
            r = self._import_settings(LWB_PUBLIC="1", DJANGO_SECRET_KEY=key)
            self.assertNotEqual(r.returncode, 0, key)
            self.assertIn("DJANGO_SECRET_KEY", r.stderr)

    def test_public_settings_values(self):
        r = self._import_settings(LWB_PUBLIC="1", DJANGO_SECRET_KEY="x" * 50, DJANGO_DEBUG="true",
                                  DJANGO_ALLOWED_HOSTS="127.0.0.1,localhost,.ts.net",
                                  LWB_PUBLIC_ORIGINS="https://pc.example.ts.net")
        self.assertEqual(r.returncode, 0, r.stderr)
        v = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertIs(v["debug"], False)  # forced off even though DJANGO_DEBUG=true
        self.assertEqual(v["hosts"], ["127.0.0.1", "localhost", ".ts.net"])
        self.assertEqual(v["csrf"], ["https://pc.example.ts.net"])
        self.assertEqual(v["proxy"], ["HTTP_X_FORWARDED_PROTO", "https"])


@override_settings(LWB_ONLINE_SECONDS=30)
class HostLivenessTests(TestCase):
    """A HOST is alive whenever its gateway is heard; every other node is judged by itself.

    Rows are written with the ORM so each source of the HOST's effective last_seen
    (own last_seen / any node of the gateway / any PerfEvent of the gateway) is isolated.
    """

    def setUp(self):
        self.now = timezone.now()
        self.gw = Gateway.objects.create(gateway_id="gw")

    def node(self, node_id, role, ago, gateway=None):
        """Node last heard `ago` seconds ago (None = never)."""
        seen = None if ago is None else self.now - timedelta(seconds=ago)
        return Node.objects.create(gateway=gateway or self.gw, node_id=node_id, role=role, last_seen=seen)

    def row(self, node_id, gateway_id="gw"):
        rows = self.client.get("/api/overview/").json()["nodes"]
        return next(n for n in rows if (n["gateway_id"], n["node_id"]) == (gateway_id, node_id))

    def test_perf_event_of_any_node_on_the_gateway_keeps_the_host_alive(self):
        host = self.node(1, "host", 600)
        other = self.node(3, "source", 600)  # its stored last_seen is old too ...
        PerfEvent.objects.create(gateway=self.gw, node=other, event_id=1, record_type="PERF_SUMMARY",
                                 recv_ts_utc=self.now - timedelta(seconds=5))  # ... but a summary just arrived
        self.assertEqual(effective_last_seen(host), self.now - timedelta(seconds=5))
        self.assertTrue(self.row(1)["online"])
        self.assertLess(self.row(1)["age_s"], 10)

    def test_nodes_of_another_gateway_do_not_keep_the_host_alive(self):
        other_gw = Gateway.objects.create(gateway_id="gw-b")
        self.node(1, "host", 600)
        busy = self.node(2, "source", 1, gateway=other_gw)
        PerfEvent.objects.create(gateway=other_gw, node=busy, event_id=1, record_type="PERF_SUMMARY",
                                 recv_ts_utc=self.now)
        self.assertFalse(self.row(1)["online"])
        self.assertTrue(self.row(2, "gw-b")["online"])

    def test_node_1_without_a_role_is_taken_to_be_the_host(self):
        self.node(1, "", 600)
        self.node(2, "source", 2)
        self.node(7, "", 600)
        self.assertEqual((self.row(1)["role"], self.row(1)["online"]), ("host", True))
        self.assertEqual((self.row(7)["role"], self.row(7)["online"]), ("source", False))  # only node 1 is guessed

    def test_ordinary_nodes_follow_only_themselves_and_the_host_keeps_its_45_second_window(self):
        host = self.node(1, "host", 600)
        n2 = self.node(2, "source", 40)  # the newest packet of the gateway, 40 s ago
        n3 = self.node(3, "source", 600)
        self.assertEqual([self.row(i)["online"] for i in (1, 2, 3)], [True, False, False])
        self.assertEqual(effective_last_seen(host), n2.last_seen)  # HOST: whole gateway
        self.assertEqual(effective_last_seen(n3), n3.last_seen)  # n3: a neighbour's packet is not its own

    def test_single_node_helpers(self):
        host = self.node(1, "host", 600)
        self.node(2, "source", 3)
        self.assertEqual(effective_last_seen(host), self.now - timedelta(seconds=3))
        self.assertTrue(is_online(host))
        silent = self.node(1, "host", None, gateway=Gateway.objects.create(gateway_id="gw-empty"))
        self.assertIsNone(effective_last_seen(silent))  # nothing ever heard on that gateway
        self.assertFalse(is_online(silent))


@override_settings(LWB_ONLINE_SECONDS=30)
class WebAndMobileAgreeTests(TestCase):
    """/api/overview/ (dashboard) and /api/mobile/v1/ (Android app) must tell the same story."""

    def mobile(self, path):
        # In production the Mobile API runs under its own settings/URLconf; mount it for the call.
        with override_settings(ROOT_URLCONF="config.lwb_mobile_urls", LWB_MOBILE_LOCAL_ONLY=True):
            return self.client.get("/api/mobile/v1/" + path).json()

    def test_same_last_seen_and_verdict_for_every_node(self):
        now = timezone.now()
        gw = Gateway.objects.create(gateway_id="gw")
        Node.objects.create(gateway=gw, node_id=1, role="host", last_seen=now - timedelta(seconds=600))
        busy = Node.objects.create(gateway=gw, node_id=2, role="source")
        Node.objects.create(gateway=gw, node_id=3, role="source", last_seen=now - timedelta(seconds=600))
        for age in (2, 20, 40, 60):  # seconds since the gateway's newest packet
            with self.subTest(age=age):
                Node.objects.filter(pk=busy.pk).update(last_seen=now - timedelta(seconds=age))
                web = {n["node_id"]: n for n in self.client.get("/api/overview/").json()["nodes"]}
                app = {n["node_id"]: n for n in self.mobile("nodes/")["results"]}
                self.assertEqual(web.keys(), app.keys())
                for node_id in web:
                    self.assertEqual(parse_datetime(web[node_id]["last_seen"]),
                                     parse_datetime(app[node_id]["last_seen"]), node_id)
                    # online on the web = live or stale in the app (a HOST has no stale band).
                    self.assertEqual(web[node_id]["online"], app[node_id]["status"] in ("live", "stale"),
                                     (node_id, app[node_id]["status"]))
                # The app's SQL paths (summary counts, ?status= filter) must agree with its per-row status.
                counts = self.mobile("nodes/status-summary/")["summary"]
                for state in ("live", "stale", "offline"):
                    expected = {i for i, n in app.items() if n["status"] == state}
                    self.assertEqual(counts[state], len(expected), state)
                    listed = {n["node_id"] for n in self.mobile(f"nodes/?status={state}")["results"]}
                    self.assertEqual(listed, expected, state)

    def test_mobile_role_in_list_and_detail(self):
        now = timezone.now()
        gw = Gateway.objects.create(gateway_id="gw")
        for node_id, role in ((1, "host"), (2, "source"), (3, "")):
            Node.objects.create(gateway=gw, node_id=node_id, role=role, last_seen=now)
        listed = {n["node_id"]: n["role"] for n in self.mobile("nodes/")["results"]}
        self.assertEqual(listed, {1: "host", 2: "source", 3: ""})  # unknown role is "" (never missing)
        for node_id, role in listed.items():
            self.assertEqual(self.mobile(f"nodes/{node_id}/latest/?gateway=gw")["node"]["role"], role)
