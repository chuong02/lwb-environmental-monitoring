import 'dart:async';
import 'dart:math';

/// One in-flight action per task. Capped retry backoff and jitter.
class PollTask {
  final Duration interval;
  final Future<void> Function() action;
  final Random random;
  Timer? _timer;
  bool _active = false, _busy = false, _again = false;
  int _failures = 0;
  PollTask({required this.interval, required this.action, Random? random}) : random = random ?? Random();
  bool get active => _active;
  bool get busy => _busy;
  int get failures => _failures;
  void start() { _active = true; refresh(); }
  void stop() { _active = false; _again = false; _timer?.cancel(); }
  void refresh() {
    if (!_active) return;
    _timer?.cancel();
    if (_busy) { _again = true; } else { unawaited(_run()); }
  }
  Future<void> _run() async {
    if (!_active || _busy) return;
    _busy = true; _again = false;
    final clock = Stopwatch()..start();
    try { await action(); _failures = 0; }
    catch (_) { _failures = min(_failures + 1, 6); }
    finally {
      _busy = false; clock.stop();
      if (_active) {
        final baseMs = _failures == 0 ? interval.inMilliseconds :
            min(60000, interval.inMilliseconds * pow(2, _failures).toInt()) + random.nextInt(1000);
        final delay = _again ? Duration.zero : Duration(milliseconds: max(100, baseMs - clock.elapsedMilliseconds));
        _timer = Timer(delay, _run);
      }
    }
  }
}
