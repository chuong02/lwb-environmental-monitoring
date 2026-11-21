from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from telemetry.models import Gateway, Node, PerfEvent, SensorReading
from .core import node_status

BASE = '/api/mobile/v1/'


class MobileApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.now = timezone.now()
        self.g1 = Gateway.objects.create(gateway_id='gateway-A')
        self.g2 = Gateway.objects.create(gateway_id='gateway-B')
        self.n1 = Node.objects.create(gateway=self.g1, node_id=1, role='source', last_seen=self.now)
        self.n2 = Node.objects.create(gateway=self.g2, node_id=1, role='source', last_seen=self.now - timedelta(seconds=40))

    def reading(self, node=None, seconds=0, event=1, **kw):
        node = node or self.n1
        return SensorReading.objects.create(gateway=node.gateway, node=node, event_id=event,
            recv_ts_utc=self.now + timedelta(seconds=seconds), **kw)

    def test_host_without_readings_but_recent_perf_is_live(self):
        host = Node.objects.create(gateway=self.g1, node_id=9, role='host', last_seen=None)
        PerfEvent.objects.create(gateway=self.g1, node=host, event_id=1, record_type='PERF_SUMMARY',
                                 recv_ts_utc=self.now - timedelta(seconds=20))
        data = self.client.get(BASE + 'nodes/9/latest/?gateway=gateway-A').data
        self.assertEqual(data['node']['status'], 'live')
        self.assertIsNone(data['reading'])
        listing = self.client.get(BASE + 'nodes/?status=live&q=9').data
        self.assertIn(9, [n['node_id'] for n in listing['results']])

    def test_dynamic_nodes_pagination_query_count(self):
        Node.objects.bulk_create([Node(gateway=self.g1, node_id=i, last_seen=self.now) for i in range(2, 252)])
        with self.assertNumQueries(2):
            result = self.client.get(BASE + 'nodes/?page=2&page_size=25')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['count'], 252)
        self.assertEqual(len(result.data['results']), 25)
        self.assertEqual(result.data['page'], 2)
        self.assertEqual(result.data['summary']['total'], 252)

    def test_same_node_id_different_gateways(self):
        self.reading(self.n1, hdc_temp_x10=251)
        self.reading(self.n2, hdc_temp_x10=302)
        a = self.client.get(BASE + 'nodes/1/latest/?gateway=gateway-A')
        b = self.client.get(BASE + 'nodes/1/latest/?gateway=gateway-B')
        self.assertEqual(a.data['reading']['temperature_c'], 25.1)
        self.assertEqual(b.data['reading']['temperature_c'], 30.2)

    def test_gateway_required(self):
        self.assertEqual(self.client.get(BASE + 'nodes/1/latest/').status_code, 400)

    def test_no_data_distinct_from_unknown_node(self):
        r = self.client.get(BASE + 'nodes/1/latest/?gateway=gateway-A')
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.data['reading'])
        self.assertEqual(self.client.get(BASE + 'nodes/999/latest/?gateway=gateway-A').status_code, 404)

    def test_history_order_and_limit(self):
        for e, seconds in [(1, 0), (2, -30), (3, -15)]: self.reading(seconds=seconds, event=e)
        r = self.client.get(BASE + 'nodes/1/history/?gateway=gateway-A&limit=2')
        self.assertEqual([row['event_id'] for row in r.data['results']], [3, 1])

    def test_invalid_limit_and_page(self):
        for query in ['page=0', 'page=x', 'page_size=-2', 'status=bad']:
            self.assertEqual(self.client.get(BASE + 'nodes/?' + query).status_code, 400)
        self.assertEqual(self.client.get(BASE + 'nodes/1/history/?gateway=gateway-A&limit=0').status_code, 400)

    def test_null_and_sentinels(self):
        self.reading(hdc_temp_x10=-32768, hdc_hum_x10=65535, light_raw=65535,
                     bmp_temp_x10=-32768, pressure_pa=-2147483648)
        r = self.client.get(BASE + 'nodes/1/latest/?gateway=gateway-A').data['reading']
        for key in ['temperature_c', 'humidity_percent', 'light_raw', 'bmp_temperature_c', 'pressure_pa']:
            self.assertIsNone(r[key])

    def test_filters_and_summary_scope(self):
        r = self.client.get(BASE + 'nodes/?gateway=gateway-B&status=offline')
        self.assertEqual(r.data['count'], 1)
        self.assertEqual(r.data['results'][0]['gateway_id'], 'gateway-B')
        self.assertEqual(r.data['summary']['offline'], 1)

    def test_no_data_and_clock_states(self):
        Node.objects.create(gateway=self.g1, node_id=4)
        Node.objects.create(gateway=self.g1, node_id=5, last_seen=self.now + timedelta(minutes=1))
        r = self.client.get(BASE + 'nodes/status-summary/').data['summary']
        self.assertEqual(r['never'], 1)
        self.assertEqual(r['clock_error'], 1)
        self.assertEqual(sum(r[s] for s in ['live','stale','offline','never','clock_error']), r['total'])

    def test_read_only(self):
        self.assertEqual(self.client.post(BASE + 'nodes/', {}).status_code, 405)

    def test_local_mode_rejects_remote_even_with_forwarded_header(self):
        r = self.client.get(BASE + 'nodes/', REMOTE_ADDR='192.168.1.3', HTTP_X_FORWARDED_FOR='127.0.0.1')
        self.assertEqual(r.status_code, 403)

    @override_settings(LWB_MOBILE_ALLOWED_NETS=['100.64.0.0/10'])
    def test_local_mode_allows_tailscale_ip(self):
        r = self.client.get(BASE + 'nodes/', REMOTE_ADDR='100.101.1.2')
        self.assertEqual(r.status_code, 200)

    @override_settings(LWB_MOBILE_ALLOWED_NETS=['100.64.0.0/10'])
    def test_local_mode_rejects_ip_outside_allowed_nets(self):
        for addr in ['192.168.1.5', '100.128.0.1', 'not-an-ip']:
            r = self.client.get(BASE + 'nodes/', REMOTE_ADDR=addr, HTTP_X_FORWARDED_FOR='100.101.1.2')
            self.assertEqual(r.status_code, 403, addr)

    @override_settings(LWB_MOBILE_LOCAL_ONLY=False)
    def test_normal_mode_requires_staff(self):
        self.assertIn(self.client.get(BASE + 'nodes/').status_code, [401,403])
        self.client.force_authenticate(user=SimpleNamespace(is_authenticated=True, is_staff=True))
        self.assertEqual(self.client.get(BASE + 'nodes/').status_code, 200)

    def test_empty_filter_and_page_clamp(self):
        r = self.client.get(BASE + 'nodes/?gateway=unknown&page=999')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['page'], 1)
        self.assertEqual(r.data['results'], [])
