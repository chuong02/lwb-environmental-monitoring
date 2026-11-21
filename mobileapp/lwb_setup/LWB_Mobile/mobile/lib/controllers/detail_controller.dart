import 'package:flutter/foundation.dart';
import '../data/telemetry_repository.dart';
import '../models/telemetry.dart';
import 'poll_task.dart';
class DetailController extends ChangeNotifier {
  final TelemetryRepository repository;
  final SensorNode initialNode;
  late final PollTask latestPoll, historyPoll;
  LatestSnapshot? latest;
  List<SensorReading> readings = [];
  String? latestError, historyError;
  DateTime? receivedAt, historyReceivedAt;
  Duration serverOffset = Duration.zero;
  int limit = 30, _revision = 0, _historyRevision = 0;
  bool _active = false, _disposed = false, loadingLatest = false, loadingHistory = false;
  DetailController(this.repository, this.initialNode) {
    latestPoll = PollTask(interval: const Duration(seconds: 5), action: _loadLatest);
    historyPoll = PollTask(interval: const Duration(seconds: 15), action: _loadHistory);
  }
  DateTime get serverNow => DateTime.now().toUtc().add(serverOffset);
  bool get connectionStale => receivedAt == null || DateTime.now().difference(receivedAt!).inSeconds > 15;
  void _notify() { if (!_disposed) notifyListeners(); }
  void resume() { _active = true; latestPoll.start(); historyPoll.start(); }
  void pause() {
    _active = false; _revision++; loadingLatest = false; loadingHistory = false;
    latestPoll.stop(); historyPoll.stop(); repository.cancel();
  }
  void refresh() { latestPoll.refresh(); historyPoll.refresh(); }
  void setLimit(int count) {
    if (![30, 60, 100].contains(count) || count == limit) return;
    limit = count; _historyRevision++; readings = []; historyError = null;
    historyPoll.refresh(); _notify();
  }
  Future<void> _loadLatest() async {
    final revision = _revision; loadingLatest = true; _notify();
    try {
      final result = await repository.latest(initialNode);
      if (_disposed || !_active || revision != _revision) return;
      latest = result; latestError = null; receivedAt = DateTime.now();
      serverOffset = result.serverTime.difference(receivedAt!.toUtc());
    } catch (e) {
      if (!_disposed && _active && revision == _revision) latestError = e.toString();
      rethrow;
    } finally {
      if (!_disposed && revision == _revision) { loadingLatest = false; _notify(); }
    }
  }
  Future<void> _loadHistory() async {
    final revision = _revision, historyRevision = _historyRevision;
    loadingHistory = true; _notify();
    try {
      final result = await repository.history(initialNode, limit);
      if (_disposed || !_active || revision != _revision || historyRevision != _historyRevision) return;
      readings = result; historyError = null; historyReceivedAt = DateTime.now();
    } catch (e) {
      if (!_disposed && _active && revision == _revision && historyRevision == _historyRevision) historyError = e.toString();
      rethrow;
    } finally {
      if (!_disposed && revision == _revision && historyRevision == _historyRevision) { loadingHistory = false; _notify(); }
    }
  }
  @override
  void dispose() { _disposed = true; latestPoll.stop(); historyPoll.stop(); repository.dispose(); super.dispose(); }
}
