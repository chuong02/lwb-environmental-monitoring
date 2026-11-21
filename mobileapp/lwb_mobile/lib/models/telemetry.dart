import 'dart:convert';

Map<String, dynamic> jsonObject(Object? value) {
  if (value is! Map<String, dynamic>) {
    throw const FormatException('JSON object required.');
  }
  return value;
}

DateTime? parseTime(Object? value) =>
    value is String ? DateTime.tryParse(value)?.toUtc() : null;
double? parseNumber(Object? value) {
  final n = value is num ? value.toDouble() : null;
  return n != null && n.isFinite ? n : null;
}

String formatTime(DateTime? value, {bool date = false}) {
  if (value == null) return '--';
  final t = value.toLocal();
  String pad(int n) => n.toString().padLeft(2, '0');
  final clock = '${pad(t.hour)}:${pad(t.minute)}:${pad(t.second)}';
  return date ? '$clock ${pad(t.day)}/${pad(t.month)}/${t.year}' : clock;
}

class FreshnessPolicy {
  final int liveSeconds, offlineSeconds, futureSeconds;
  const FreshnessPolicy({
    this.liveSeconds = 15,
    this.offlineSeconds = 30,
    this.futureSeconds = 10,
  });
  factory FreshnessPolicy.fromJson(Object? json) {
    final m = jsonObject(json);
    return FreshnessPolicy(
      liveSeconds: (m['live_seconds'] as num).toInt(),
      offlineSeconds: (m['offline_seconds'] as num).toInt(),
      futureSeconds: (m['future_seconds'] as num).toInt(),
    );
  }
  String status(DateTime? seen, DateTime now) {
    if (seen == null) return 'never';
    final age = now.difference(seen).inMilliseconds / 1000;
    if (age < -futureSeconds) return 'clock_error';
    if (age <= liveSeconds) return 'live';
    if (age <= offlineSeconds) return 'stale';
    return 'offline';
  }
}

String statusLabel(String status) => switch (status) {
  'live' => 'Live',
  'stale' => 'Dữ liệu chậm',
  'offline' => 'Offline',
  'clock_error' => 'Sai giờ',
  _ => 'Chưa có dữ liệu',
};

class SensorNode {
  final String gatewayId;
  final int nodeId;
  final DateTime? lastSeen;

  /// Status computed by the server (host-aware); null if the server omitted it.
  final String? serverStatus;

  /// Server role if provided (host/source/relay).
  final String? role;
  const SensorNode({
    required this.gatewayId,
    required this.nodeId,
    this.lastSeen,
    this.serverStatus,
    this.role,
  });
  bool get isHost => role == 'host' || (role == null && nodeId == 1);

  /// Server status wins; otherwise fall back to the local policy.
  String status(FreshnessPolicy policy, DateTime now) =>
      serverStatus ?? policy.status(lastSeen, now);
  String get key => jsonEncode([gatewayId, nodeId]);
  factory SensorNode.fromJson(Object? json) {
    final m = jsonObject(json);
    return SensorNode(
      gatewayId: m['gateway_id'] as String,
      nodeId: (m['node_id'] as num).toInt(),
      lastSeen: parseTime(m['last_seen']),
      serverStatus: switch (m['status']) {
        'live' ||
        'stale' ||
        'offline' ||
        'never' ||
        'clock_error' => m['status'] as String,
        _ => null,
      },
      role: m['role'] is String ? m['role'] as String : null,
    );
  }
}

class SensorReading {
  final int eventId, nodeId;
  final int? seq;
  final String gatewayId;
  final DateTime time;
  final double? temperature, humidity, bmpTemperature, pressurePa, lightRaw;
  const SensorReading({
    required this.eventId,
    required this.nodeId,
    required this.gatewayId,
    required this.time,
    this.seq,
    this.temperature,
    this.humidity,
    this.bmpTemperature,
    this.pressurePa,
    this.lightRaw,
  });
  bool get hasSensorValues =>
      temperature != null ||
      humidity != null ||
      bmpTemperature != null ||
      pressurePa != null ||
      lightRaw != null;
  double? get pressureHpa => pressurePa == null ? null : pressurePa! / 100;
  factory SensorReading.fromJson(Object? json) {
    final m = jsonObject(json);
    final time = parseTime(m['recv_ts_utc']);
    if (time == null) throw const FormatException('Invalid recv_ts_utc.');
    final raw = parseNumber(m['light_raw']);
    return SensorReading(
      eventId: (m['event_id'] as num).toInt(),
      nodeId: (m['node_id'] as num).toInt(),
      gatewayId: m['gateway_id'] as String,
      seq: (m['seq'] as num?)?.toInt(),
      time: time,
      temperature: parseNumber(m['temperature_c']),
      humidity: parseNumber(m['humidity_percent']),
      bmpTemperature: parseNumber(m['bmp_temperature_c']),
      pressurePa: parseNumber(m['pressure_pa']),
      lightRaw: raw == 65535 ? null : raw,
    );
  }
}

class NodePage {
  final List<SensorNode> nodes;
  final Map<String, int> summary;
  final int count, page, pages;
  final DateTime serverTime;
  final FreshnessPolicy policy;
  const NodePage({
    required this.nodes,
    required this.summary,
    required this.count,
    required this.page,
    required this.pages,
    required this.serverTime,
    required this.policy,
  });
  factory NodePage.fromJson(Map<String, dynamic> m) => NodePage(
    nodes: (m['results'] as List)
        .map(SensorNode.fromJson)
        .toList(growable: false),
    summary: jsonObject(m['summary'])
        .map((k, v) => MapEntry(k, (v as num).toInt())),
    count: (m['count'] as num).toInt(),
    page: (m['page'] as num).toInt(),
    pages: (m['pages'] as num).toInt(),
    serverTime:
        parseTime(m['server_time']) ??
        (throw const FormatException('Missing server_time')),
    policy: FreshnessPolicy.fromJson(m['policy']),
  );
}

class LatestSnapshot {
  final SensorNode node;
  final SensorReading? reading;
  final DateTime serverTime;
  final FreshnessPolicy policy;
  const LatestSnapshot({
    required this.node,
    this.reading,
    required this.serverTime,
    required this.policy,
  });
  factory LatestSnapshot.fromJson(Map<String, dynamic> m) => LatestSnapshot(
    node: SensorNode.fromJson(m['node']),
    reading: m['reading'] == null ? null : SensorReading.fromJson(m['reading']),
    serverTime:
        parseTime(m['server_time']) ??
        (throw const FormatException('Missing server_time')),
    policy: FreshnessPolicy.fromJson(m['policy']),
  );
}
