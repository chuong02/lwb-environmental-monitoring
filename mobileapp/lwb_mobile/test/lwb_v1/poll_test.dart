import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:lwb_mobile/controllers/poll_task.dart';

void main() {
  testWidgets('polling does not overlap and stops while inactive', (
    tester,
  ) async {
    var calls = 0;
    final gate = Completer<void>();
    final p = PollTask(
      interval: const Duration(seconds: 5),
      action: () async {
        calls++;
        await gate.future;
      },
    );
    p.start();
    p.refresh();
    p.refresh();
    await tester.pump(const Duration(seconds: 20));
    expect(calls, 1);
    p.stop();
    gate.complete();
    await tester.pump();
    await tester.pump(const Duration(seconds: 30));
    expect(calls, 1);
    expect(p.active, false);
  });
  testWidgets('resume refreshes immediately', (tester) async {
    var calls = 0;
    final p = PollTask(
      interval: const Duration(seconds: 15),
      action: () async {
        calls++;
      },
    );
    p.start();
    await tester.pump();
    expect(calls, 1);
    p.stop();
    await tester.pump(const Duration(seconds: 30));
    expect(calls, 1);
    p.start();
    await tester.pump();
    expect(calls, 2);
    p.stop();
  });
}
