import 'package:flutter/foundation.dart';
import '../data/telemetry_repository.dart';
import '../models/telemetry.dart';
import 'poll_task.dart';
class OverviewController extends ChangeNotifier {
  final TelemetryRepository repository;
  late final PollTask polling;
  NodePage? data;
  String gateway = '', query = '', status = '';
  String? error;
  int page = 1, _revision = 0;
  bool loading = false, _disposed = false, _active = false;
  DateTime? receivedAt;
  Duration serverOffset = Duration.zero;
  OverviewController(this.repository) {
    polling = PollTask(interval: const Duration(seconds: 15), action: _load);
  }
  DateTime get serverNow => DateTime.now().toUtc().add(serverOffset);
  bool get connectionStale => receivedAt != null && DateTime.now().difference(receivedAt!).inSeconds > 30;
  void _notify() { if (!_disposed) notifyListeners(); }
  void resume() { _active = true; polling.start(); }
  void pause() { _active = false; _revision++; loading = false; polling.stop(); repository.cancel(); }
  void refresh() => polling.refresh();
  void filter({required String gateway, required String query, required String status}) {
    this.gateway = gateway.trim(); this.query = query.trim(); this.status = status;
    page = 1; _revision++; data = null; error = null; refresh(); _notify();
  }
  void changePage(int value) { page = value; _revision++; data = null; error = null; refresh(); _notify(); }
  Future<void> _load() async {
    final revision = _revision; loading = true; _notify();
    try {
      final result = await repository.nodes(page: page, gateway: gateway, query: query, status: status);
      if (_disposed || !_active || revision != _revision) return;
      data = result; page = result.page; error = null; receivedAt = DateTime.now();
      serverOffset = result.serverTime.difference(receivedAt!.toUtc());
    } catch (e) {
      if (!_disposed && _active && revision == _revision) error = e.toString();
      rethrow;
    } finally {
      if (!_disposed && revision == _revision) { loading = false; _notify(); }
    }
  }
  @override
  void dispose() { _disposed = true; polling.stop(); repository.dispose(); super.dispose(); }
}
