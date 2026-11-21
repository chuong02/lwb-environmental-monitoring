import 'dart:async';
import 'package:flutter/material.dart';
import '../controllers/detail_controller.dart';
import '../data/api_service.dart';
import '../data/telemetry_repository.dart';
import '../models/telemetry.dart';
import '../widgets/common.dart';
import '../widgets/history_chart.dart';
class DetailScreen extends StatefulWidget {
  final String baseUrl;
  final SensorNode node;
  const DetailScreen({super.key, required this.baseUrl, required this.node});
  @override
  State<DetailScreen> createState() => _DetailScreenState();
}
class _DetailScreenState extends State<DetailScreen> with WidgetsBindingObserver {
  late final DetailController c;
  Timer? ticker;
  @override
  void initState() {
    super.initState(); c = DetailController(TelemetryRepository(ApiService(widget.baseUrl)), widget.node);
    WidgetsBinding.instance.addObserver(this); _start();
  }
  void _start() {
    c.resume(); ticker?.cancel();
    ticker = Timer.periodic(const Duration(seconds: 1), (_) { if (mounted) setState(() {}); });
  }
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) { _start(); } else { c.pause(); ticker?.cancel(); }
  }
  @override
  void dispose() { WidgetsBinding.instance.removeObserver(this); ticker?.cancel(); c.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) => Scaffold(appBar: AppBar(title: Text('Node ${widget.node.nodeId}'), actions: [
    IconButton(onPressed: c.refresh, icon: const Icon(Icons.refresh), tooltip: 'Làm mới'),
  ]), body: AnimatedBuilder(animation: c, builder: (context, _) {
    final snapshot = c.latest;
    final r = c.latest?.reading;
    final node = snapshot?.node ?? widget.node;
    final policy = snapshot?.policy ?? const FreshnessPolicy();
    final state = policy.status(node.lastSeen, c.serverNow);
    final unknown = c.latestError != null || c.connectionStale;
    return Center(child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 1000), child: ListView(
      padding: const EdgeInsets.all(16), children: [
        Card(color: const Color(0xFF183B59), child: Padding(padding: const EdgeInsets.all(20),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Node ${node.nodeId}', style: const TextStyle(fontSize: 30, color: Colors.white, fontWeight: FontWeight.w700)),
            const SizedBox(height: 6), Text('Gateway: ${node.gatewayId}', style: const TextStyle(color: Colors.white70)),
            const SizedBox(height: 10),
            if (unknown) const Chip(label: Text('Chưa xác nhận qua API')) else StatusBadge(state),
            Text('Bản tin gần nhất: ${formatTime(node.lastSeen, date: true)}', style: const TextStyle(color: Colors.white70, fontSize: 12)),
          ]))), const SizedBox(height: 12),
        if (c.latestError != null) MessageBanner('${c.latestError}\nSố đo cũ chỉ để tham khảo.', error: true),
        if (state == 'offline' && !unknown) const MessageBanner('Node quá ngưỡng không có bản tin. Số đo bên dưới là lần nhận cuối.'),
        if (state == 'clock_error') const MessageBanner('Thời gian Gateway ở tương lai so với server. Kiểm tra đồng bộ giờ.', error: true),
        if (c.loadingLatest && snapshot == null) const LinearProgressIndicator(),
        if (snapshot != null && r == null) const MessageBanner('Node đã đăng ký nhưng chưa có bản ghi cảm biến (hoặc lịch sử đã được dọn).'),
        const SizedBox(height: 8), const Text('THÔNG SỐ MÔI TRƯỜNG', style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 12), LayoutBuilder(builder: (context, box) {
          final columns = box.maxWidth >= 720 ? 3 : box.maxWidth >= 310 ? 2 : 1;
          final width = (box.maxWidth - 12 * (columns - 1)) / columns;
          final cards = <Widget>[
            MetricCard(title: 'Nhiệt độ', value: r?.temperature, unit: '°C', source: 'HDC1080', icon: Icons.thermostat_outlined),
            MetricCard(title: 'Độ ẩm', value: r?.humidity, unit: '%', source: 'HDC1080', icon: Icons.water_drop_outlined),
            MetricCard(title: 'Ánh sáng', value: r?.lightRaw, unit: 'raw', source: 'Chưa quy đổi lux', icon: Icons.light_mode_outlined, decimals: 0),
            MetricCard(title: 'Áp suất', value: r?.pressureHpa, unit: 'hPa', source: 'Pa / 100', icon: Icons.speed_outlined),
            MetricCard(title: 'Nhiệt độ BMP', value: r?.bmpTemperature, unit: '°C', source: 'BMP', icon: Icons.thermostat),
          ];
          return Wrap(spacing: 12, runSpacing: 12, children: cards.map((w) => SizedBox(width: width, child: w)).toList());
        }), const SizedBox(height: 18),
        Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Lịch sử đo', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700)), const SizedBox(height: 10),
          Wrap(spacing: 8, children: [30, 60, 100].map((n) => ChoiceChip(label: Text('$n mẫu'), selected: c.limit == n,
            onSelected: (_) => c.setLimit(n))).toList()),
          if (c.historyError != null) Padding(padding: const EdgeInsets.only(top: 10), child: MessageBanner(c.historyError!, error: true)),
          if (c.loadingHistory && c.readings.isEmpty) const LinearProgressIndicator(),
          const SizedBox(height: 14), HistoryChart(data: c.readings), const SizedBox(height: 20),
          HistoryChart(data: c.readings, humidity: true), const SizedBox(height: 12),
          Text('${c.readings.length} bản ghi | Tải lại 15 giây. Khoảng mất dữ liệu lớn được ngắt nối trên đường vẽ.',
            style: Theme.of(context).textTheme.bodySmall),
        ]))), const SizedBox(height: 12),
        Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Thông tin bản tin', style: TextStyle(fontWeight: FontWeight.w700)), const SizedBox(height: 8),
          Text('Gateway: ${node.gatewayId}\nNode ID: ${node.nodeId}\nEvent ID: ${r?.eventId ?? '--'}\n'
            'Sequence: ${r?.seq ?? '--'}\nNhận tại Gateway: ${formatTime(r?.time, date: true)}\n'
            'Lần đọc API: ${formatTime(c.receivedAt, date: true)}'), const SizedBox(height: 10),
          const Text('Dữ liệu: 5 giây | Lịch sử: 15 giây. Dừng truy vấn khi ứng dụng vào nền.'),
        ]))), const SizedBox(height: 20),
      ])));
  }));
}
