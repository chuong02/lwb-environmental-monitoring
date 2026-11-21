import '../models/telemetry.dart';
import 'api_service.dart';
class TelemetryRepository {
  final ApiService api;
  TelemetryRepository(this.api);
  Future<NodePage> nodes({int page = 1, String gateway = '', String query = '', String status = ''}) async =>
      NodePage.fromJson(await api.get('nodes/', {'page': '$page', 'page_size': '25',
        if (gateway.isNotEmpty) 'gateway': gateway, if (query.isNotEmpty) 'q': query,
        if (status.isNotEmpty) 'status': status}));
  Future<LatestSnapshot> latest(SensorNode node) async => LatestSnapshot.fromJson(
      await api.get('nodes/${node.nodeId}/latest/', {'gateway': node.gatewayId}));
  Future<List<SensorReading>> history(SensorNode node, int limit) async {
    final m = await api.get('nodes/${node.nodeId}/history/', {'gateway': node.gatewayId, 'limit': '$limit'});
    final rows = (m['results'] as List).map(SensorReading.fromJson).toList();
    rows.sort((a, b) => a.time.compareTo(b.time)); return rows;
  }
  void cancel() => api.cancelActive();
  void dispose() => api.close();
}
