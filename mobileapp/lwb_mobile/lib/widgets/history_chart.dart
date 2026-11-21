import 'dart:math';

import 'package:flutter/material.dart';

import '../models/telemetry.dart';

enum ChartMetric { temperature, humidity, light, pressure }

class _Series {
  final String label;
  final Color color;
  final double? Function(SensorReading) field;
  const _Series(this.label, this.color, this.field);
}

class _MetricSpec {
  final String title, unit;
  final int decimals;
  final bool fixedPercent;
  final List<_Series> series;
  const _MetricSpec(
    this.title,
    this.unit,
    this.decimals,
    this.series, {
    this.fixedPercent = false,
  });
}

final _specs = <ChartMetric, _MetricSpec>{
  ChartMetric.temperature: _MetricSpec('Nhiệt độ', '°C', 1, [
    _Series('HDC1080', const Color(0xFF3569DB), (r) => r.temperature),
    _Series('BMP', const Color(0xFFEF8A23), (r) => r.bmpTemperature),
  ]),
  ChartMetric.humidity: _MetricSpec('Độ ẩm', '%', 0, [
    _Series('Độ ẩm', const Color(0xFF00897B), (r) => r.humidity),
  ], fixedPercent: true),
  ChartMetric.light: _MetricSpec('Ánh sáng', 'raw', 0, [
    _Series('Ánh sáng', const Color(0xFFB8860B), (r) => r.lightRaw),
  ]),
  ChartMetric.pressure: _MetricSpec('Áp suất', 'hPa', 1, [
    _Series('Áp suất', const Color(0xFF7B1FA2), (r) => r.pressureHpa),
  ]),
};

/// Straight-line time chart. Nulls and large gaps break lines. No invented samples.
class HistoryChart extends StatefulWidget {
  final List<SensorReading> data;
  final ChartMetric metric;
  const HistoryChart({
    super.key,
    required this.data,
    this.metric = ChartMetric.temperature,
  });
  @override
  State<HistoryChart> createState() => _HistoryChartState();
}

class _HistoryChartState extends State<HistoryChart> {
  int? selectedIndex;
  @override
  void didUpdateWidget(covariant HistoryChart oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.data != widget.data) selectedIndex = null;
  }

  String _selectedText(_MetricSpec spec, SensorReading r) {
    final parts = spec.series.map((s) {
      final v = s.field(r)?.toStringAsFixed(spec.decimals) ?? '--';
      return spec.series.length > 1 ? '${s.label}: $v' : v;
    });
    return '${formatTime(r.time)} | ${parts.join(' | ')} ${spec.unit}';
  }

  @override
  Widget build(BuildContext context) {
    final spec = _specs[widget.metric]!;
    final title = Text(
      '${spec.title} (${spec.unit})',
      style: const TextStyle(fontWeight: FontWeight.w600),
    );
    if (widget.data.isEmpty) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          title,
          const SizedBox(
            height: 100,
            child: Center(child: Text('Chưa có lịch sử.')),
          ),
        ],
      );
    }
    final hasValues = widget.data.any(
      (r) => spec.series.any((s) => s.field(r) != null),
    );
    if (!hasValues) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          title,
          const SizedBox(
            height: 100,
            child: Center(child: Text('Không có giá trị hợp lệ để vẽ.')),
          ),
        ],
      );
    }
    final i = selectedIndex;
    final selected = i != null && i < widget.data.length
        ? widget.data[i]
        : null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        title,
        const SizedBox(height: 8),
        LayoutBuilder(
          builder: (context, box) => GestureDetector(
            onTapDown: (event) {
              final fraction =
                  ((event.localPosition.dx - 46) / max(1.0, box.maxWidth - 58))
                      .clamp(0.0, 1.0);
              final first = widget.data.first.time.millisecondsSinceEpoch;
              final target =
                  first +
                  fraction *
                      (widget.data.last.time.millisecondsSinceEpoch - first);
              var nearest = 0;
              for (var n = 1; n < widget.data.length; n++) {
                if ((widget.data[n].time.millisecondsSinceEpoch - target)
                        .abs() <
                    (widget.data[nearest].time.millisecondsSinceEpoch - target)
                        .abs()) {
                  nearest = n;
                }
              }
              setState(() => selectedIndex = nearest);
            },
            child: Semantics(
              label: '${widget.data.length} samples. Tap to select a reading.',
              child: CustomPaint(
                size: Size(box.maxWidth, 190),
                painter: _ChartPainter(widget.data, spec, selectedIndex),
              ),
            ),
          ),
        ),
        Text(
          spec.series.map((s) => s.label).join(' | '),
          style: Theme.of(context).textTheme.bodySmall,
        ),
        if (selected != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(_selectedText(spec, selected)),
          ),
      ],
    );
  }
}

class _ChartPainter extends CustomPainter {
  final List<SensorReading> data;
  final _MetricSpec spec;
  final int? selected;
  _ChartPainter(this.data, this.spec, this.selected);
  void text(Canvas canvas, String s, Offset p, {double width = 75}) {
    final painter = TextPainter(
      text: TextSpan(
        text: s,
        style: const TextStyle(fontSize: 10, color: Color(0xFF607D8B)),
      ),
      textDirection: TextDirection.ltr,
    )..layout(maxWidth: width);
    painter.paint(canvas, p);
  }

  @override
  void paint(Canvas canvas, Size size) {
    final area = Rect.fromLTWH(
      46,
      12,
      max(1.0, size.width - 58),
      size.height - 40,
    );
    final values = <double>[
      for (final r in data)
        for (final s in spec.series)
          if (s.field(r) != null) s.field(r)!,
    ];
    if (values.isEmpty) return;
    double minV = spec.fixedPercent ? 0 : values.reduce(min),
        maxV = spec.fixedPercent ? 100 : values.reduce(max);
    if (!spec.fixedPercent) {
      final pad = max(spec.decimals == 0 ? 1.0 : 0.2, (maxV - minV) * 0.15);
      minV -= pad;
      maxV += pad;
    }
    final t0 = data.first.time.millisecondsSinceEpoch;
    final span = max(1, data.last.time.millisecondsSinceEpoch - t0);
    Offset point(SensorReading r, double v) => Offset(
      area.left +
          (data.length == 1
                  ? 0.5
                  : (r.time.millisecondsSinceEpoch - t0) / span) *
              area.width,
      area.bottom - (v - minV) / (maxV - minV) * area.height,
    );
    final grid = Paint()
      ..color = const Color(0xFFE2E8F0)
      ..strokeWidth = 1;
    for (var n = 0; n <= 4; n++) {
      final y = area.top + area.height * n / 4;
      canvas.drawLine(Offset(area.left, y), Offset(area.right, y), grid);
      text(
        canvas,
        (maxV - (maxV - minV) * n / 4).toStringAsFixed(spec.decimals),
        Offset(0, y - 6),
        width: 43,
      );
    }
    text(
      canvas,
      formatTime(data.first.time),
      Offset(area.left, area.bottom + 8),
    );
    text(
      canvas,
      formatTime(data.last.time),
      Offset(max(area.left, area.right - 55), area.bottom + 8),
    );
    final gaps = <int>[];
    for (var i = 1; i < data.length; i++) {
      final gap = data[i].time.difference(data[i - 1].time).inMilliseconds;
      if (gap > 0) gaps.add(gap);
    }
    gaps.sort();
    final maxGap = gaps.isEmpty
        ? 20000
        : max(20000, gaps[gaps.length ~/ 2] * 3);
    void drawSeries(double? Function(SensorReading) field, Color color) {
      final pen = Paint()
        ..color = color
        ..strokeWidth = 2
        ..style = PaintingStyle.stroke;
      Offset? previous;
      DateTime? previousTime;
      canvas.save();
      canvas.clipRect(area.inflate(2));
      for (final row in data) {
        final value = field(row);
        if (value == null || value < minV || value > maxV) {
          previous = null;
          previousTime = null;
          continue;
        }
        final current = point(row, value);
        if (previous != null &&
            previousTime != null &&
            row.time.difference(previousTime).inMilliseconds <= maxGap) {
          canvas.drawLine(previous, current, pen);
        }
        canvas.drawCircle(current, 2, Paint()..color = color);
        previous = current;
        previousTime = row.time;
      }
      canvas.restore();
    }

    for (final s in spec.series) {
      drawSeries(s.field, s.color);
    }
    if (selected != null && selected! < data.length) {
      final x = point(data[selected!], minV).dx;
      canvas.drawLine(
        Offset(x, area.top),
        Offset(x, area.bottom),
        Paint()..color = Colors.black38,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _ChartPainter old) =>
      old.data != data || old.spec != spec || old.selected != selected;
}
