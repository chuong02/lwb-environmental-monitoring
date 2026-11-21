import 'package:flutter_test/flutter_test.dart';
import 'package:lwb_mobile/models/telemetry.dart';

void main() {
  test('status boundaries and future timestamp', () {
    const p = FreshnessPolicy();
    final now = DateTime.utc(2026, 1, 1);
    expect(p.status(null, now), 'never');
    expect(p.status(now.subtract(const Duration(seconds: 15)), now), 'live');
    expect(p.status(now.subtract(const Duration(seconds: 16)), now), 'stale');
    expect(p.status(now.subtract(const Duration(seconds: 30)), now), 'stale');
    expect(p.status(now.subtract(const Duration(seconds: 31)), now), 'offline');
    expect(p.status(now.add(const Duration(seconds: 11)), now), 'clock_error');
  });
  test('gateway is part of node identity', () {
    const a = SensorNode(gatewayId: 'A:1', nodeId: 2),
        b = SensorNode(gatewayId: 'A', nodeId: 12);
    expect(a.key, isNot(b.key));
  });
  test('engineering units, numeric conversions and nulls', () {
    final r = SensorReading.fromJson({
      'event_id': 100,
      'gateway_id': 'g',
      'node_id': 99,
      'recv_ts_utc': '2026-01-01T00:00:00Z',
      'pressure_pa': 100790,
      'temperature_c': 25,
      'humidity_percent': null,
      'light_raw': 65535,
      'seq': null,
      'bmp_temperature_c': 24.8,
    });
    expect(r.pressureHpa, 1007.9);
    expect(r.temperature, 25.0);
    expect(r.humidity, isNull);
    expect(r.lightRaw, isNull);
  });
  test('large or empty node pages do not assume IDs 1,2,3', () {
    final p = NodePage.fromJson({
      'results': [
        {'gateway_id': 'many', 'node_id': 999, 'last_seen': null},
      ],
      'summary': {'total': 999},
      'count': 999,
      'page': 40,
      'pages': 40,
      'server_time': '2026-01-01T00:00:00Z',
      'policy': {
        'live_seconds': 15,
        'offline_seconds': 30,
        'future_seconds': 10,
      },
    });
    expect(p.nodes.single.nodeId, 999);
    expect(p.count, 999);
  });
}
