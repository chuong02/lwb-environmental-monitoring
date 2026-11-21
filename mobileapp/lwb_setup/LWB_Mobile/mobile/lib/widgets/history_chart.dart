import 'dart:math';
import 'package:flutter/material.dart';
import '../models/telemetry.dart';

/// Straight-line time chart. Nulls and large gaps break lines. No invented samples.
class HistoryChart extends StatefulWidget {
  final List<SensorReading> data;
  final bool humidity;
  const HistoryChart({super.key, required this.data, this.humidity = false});
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
  @override
  Widget build(BuildContext context) {
    if (widget.data.isEmpty) return const SizedBox(height: 130, child: Center(child: Text('Chưa có lịch sử.')));
    final i = selectedIndex;
    final selected = i != null && i < widget.data.length ? widget.data[i] : null;
    final hasValues = widget.data.any((r) => widget.humidity ? r.humidity != null :
      r.temperature != null || r.bmpTemperature != null);
    if (!hasValues) return const SizedBox(height: 130, child: Center(child: Text('Không có giá trị hợp lệ để vẽ.')));
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(widget.humidity ? 'Độ ẩm (%)' : 'Nhiệt độ (°C)', style: const TextStyle(fontWeight: FontWeight.w600)),
      const SizedBox(height: 8),
      LayoutBuilder(builder: (context, box) => GestureDetector(onTapDown: (event) {
        final fraction = ((event.localPosition.dx - 46) / max(1.0, box.maxWidth - 58)).clamp(0.0, 1.0);
        final first = widget.data.first.time.millisecondsSinceEpoch;
        final target = first + fraction * (widget.data.last.time.millisecondsSinceEpoch - first);
        var nearest = 0;
        for (var n = 1; n < widget.data.length; n++) {
          if ((widget.data[n].time.millisecondsSinceEpoch - target).abs() <
              (widget.data[nearest].time.millisecondsSinceEpoch - target).abs()) nearest = n;
        }
        setState(() => selectedIndex = nearest);
      }, child: Semantics(label: '${widget.data.length} samples. Tap to select a reading.',
        child: CustomPaint(size: Size(box.maxWidth, 190), painter: _ChartPainter(widget.data, widget.humidity, selectedIndex))))),
      Text(widget.humidity ? 'Độ ẩm: xanh lá' : 'HDC1080: xanh dương | BMP: cam', style: Theme.of(context).textTheme.bodySmall),
      if (selected != null) Padding(padding: const EdgeInsets.only(top: 8), child: Text(widget.humidity ?
        '${formatTime(selected.time)} | ${selected.humidity?.toStringAsFixed(1) ?? '--'} %' :
        '${formatTime(selected.time)} | HDC: ${selected.temperature?.toStringAsFixed(1) ?? '--'} | BMP: ${selected.bmpTemperature?.toStringAsFixed(1) ?? '--'} C')),
    ]);
  }
}
class _ChartPainter extends CustomPainter {
  final List<SensorReading> data;
  final bool humidity;
  final int? selected;
  _ChartPainter(this.data, this.humidity, this.selected);
  void text(Canvas canvas, String s, Offset p, {double width = 75}) {
    final painter = TextPainter(text: TextSpan(text: s, style: const TextStyle(fontSize: 10, color: Color(0xFF607D8B))),
      textDirection: TextDirection.ltr)..layout(maxWidth: width);
    painter.paint(canvas, p);
  }
  @override
  void paint(Canvas canvas, Size size) {
    final area = Rect.fromLTWH(46, 12, max(1.0, size.width - 58), size.height - 40);
    final values = data.expand<double>((r) => humidity ? [if (r.humidity != null) r.humidity!] :
      [if (r.temperature != null) r.temperature!, if (r.bmpTemperature != null) r.bmpTemperature!]).toList();
    if (values.isEmpty) return;
    double minV = humidity ? 0 : values.reduce(min), maxV = humidity ? 100 : values.reduce(max);
    if (!humidity) { final pad = max(0.2, (maxV - minV) * 0.15); minV -= pad; maxV += pad; }
    final t0 = data.first.time.millisecondsSinceEpoch;
    final span = max(1, data.last.time.millisecondsSinceEpoch - t0);
    Offset point(SensorReading r, double v) => Offset(area.left +
      (data.length == 1 ? 0.5 : (r.time.millisecondsSinceEpoch - t0) / span) * area.width,
      area.bottom - (v - minV) / (maxV - minV) * area.height);
    final grid = Paint()..color = const Color(0xFFE2E8F0)..strokeWidth = 1;
    for (var n = 0; n <= 4; n++) {
      final y = area.top + area.height * n / 4;
      canvas.drawLine(Offset(area.left, y), Offset(area.right, y), grid);
      text(canvas, (maxV - (maxV - minV) * n / 4).toStringAsFixed(humidity ? 0 : 1), Offset(0, y - 6), width: 43);
    }
    text(canvas, formatTime(data.first.time), Offset(area.left, area.bottom + 8));
    text(canvas, formatTime(data.last.time), Offset(max(area.left, area.right - 55), area.bottom + 8));
    final gaps = <int>[];
    for (var i = 1; i < data.length; i++) {
      final gap = data[i].time.difference(data[i-1].time).inMilliseconds;
      if (gap > 0) gaps.add(gap);
    }
    gaps.sort();
    final maxGap = gaps.isEmpty ? 20000 : max(20000, gaps[gaps.length ~/ 2] * 3);
    void drawSeries(double? Function(SensorReading) field, Color color) {
      final pen = Paint()..color = color..strokeWidth = 2..style = PaintingStyle.stroke;
      Offset? previous;
      DateTime? previousTime;
      canvas.save(); canvas.clipRect(area.inflate(2));
      for (final row in data) {
        final value = field(row);
        if (value == null || value < minV || value > maxV) { previous = null; previousTime = null; continue; }
        final current = point(row, value);
        if (previous != null && previousTime != null && row.time.difference(previousTime).inMilliseconds <= maxGap) {
          canvas.drawLine(previous, current, pen);
        }
        canvas.drawCircle(current, 2, Paint()..color = color);
        previous = current; previousTime = row.time;
      }
      canvas.restore();
    }
    if (humidity) { drawSeries((r) => r.humidity, const Color(0xFF00897B)); }
    else {
      drawSeries((r) => r.temperature, const Color(0xFF3569DB));
      drawSeries((r) => r.bmpTemperature, const Color(0xFFEF8A23));
    }
    if (selected != null && selected! < data.length) {
      final x = point(data[selected!], minV).dx;
      canvas.drawLine(Offset(x, area.top), Offset(x, area.bottom), Paint()..color = Colors.black38);
    }
  }
  @override
  bool shouldRepaint(covariant _ChartPainter old) => old.data != data || old.humidity != humidity || old.selected != selected;
}
