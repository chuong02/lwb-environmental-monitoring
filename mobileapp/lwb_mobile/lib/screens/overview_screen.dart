import 'dart:async';

import 'package:flutter/material.dart';

import '../controllers/overview_controller.dart';
import '../data/api_service.dart';
import '../data/telemetry_repository.dart';
import '../models/telemetry.dart';
import '../widgets/common.dart';
import '../widgets/connection_dialog.dart';
import 'detail_screen.dart';

class OverviewScreen extends StatefulWidget {
  final String baseUrl;
  final Future<void> Function(String) onChangeUrl;
  const OverviewScreen({
    super.key,
    required this.baseUrl,
    required this.onChangeUrl,
  });
  @override
  State<OverviewScreen> createState() => _OverviewScreenState();
}

class _OverviewScreenState extends State<OverviewScreen>
    with WidgetsBindingObserver {
  late final OverviewController c;
  final gateway = TextEditingController(), query = TextEditingController();
  String status = '';
  Timer? ticker;
  bool routeVisible = true, foreground = true;
  @override
  void initState() {
    super.initState();
    c = OverviewController(TelemetryRepository(ApiService(widget.baseUrl)));
    WidgetsBinding.instance.addObserver(this);
    _start();
  }

  void _start() {
    if (!foreground || !routeVisible) return;
    c.resume();
    ticker?.cancel();
    ticker = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  void _stop() {
    c.pause();
    ticker?.cancel();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    foreground = state == AppLifecycleState.resumed;
    if (foreground) {
      _start();
    } else {
      _stop();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    ticker?.cancel();
    gateway.dispose();
    query.dispose();
    c.dispose();
    super.dispose();
  }

  Future<void> _open(SensorNode node) async {
    routeVisible = false;
    _stop();
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => DetailScreen(baseUrl: widget.baseUrl, node: node),
      ),
    );
    if (!mounted) return;
    routeVisible = true;
    _start();
  }

  Future<void> _settings() async {
    final result = await showDialog<String>(
      context: context,
      builder: (_) => ConnectionDialog(initialUrl: widget.baseUrl),
    );
    if (result != null && mounted) await widget.onChangeUrl(result);
  }

  void _apply() =>
      c.filter(gateway: gateway.text, query: query.text, status: status);
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('LWB Monitor'),
      actions: [
        IconButton(
          tooltip: 'Làm mới',
          onPressed: c.refresh,
          icon: const Icon(Icons.refresh),
        ),
        IconButton(
          tooltip: 'Kết nối',
          onPressed: _settings,
          icon: const Icon(Icons.settings_outlined),
        ),
      ],
    ),
    body: AnimatedBuilder(
      animation: c,
      builder: (context, _) {
        final data = c.data;
        return Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1000),
            child: RefreshIndicator(
              onRefresh: _pullRefresh,
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.all(16),
                children: [
                  Text(
                    'MẠNG CẢM BIẾN',
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.primary,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Danh sách Node',
                    style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '${widget.baseUrl} | Tự cập nhật 2 giây',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  const SizedBox(height: 16),
                  if (c.error != null)
                    MessageBanner(
                      '${c.error}\nDữ liệu giữ lại chỉ là bản đã tải. Ứng dụng tự thử lại.',
                      error: true,
                    ),
                  if (c.error == null && c.connectionStale)
                    const MessageBanner(
                      'Phản hồi API đã cũ. Chưa thể xác nhận kết nối thiết bị.',
                    ),
                  if (data != null)
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        _count(
                          'Tổng',
                          data.summary['total'] ?? 0,
                          Icons.hub_outlined,
                        ),
                        _count(
                          'Live',
                          data.summary['live'] ?? 0,
                          Icons.sensors,
                        ),
                        _count(
                          'Chậm',
                          data.summary['stale'] ?? 0,
                          Icons.schedule,
                        ),
                        _count(
                          'Offline',
                          data.summary['offline'] ?? 0,
                          Icons.sensors_off,
                        ),
                        _count(
                          'Chưa có DL',
                          data.summary['never'] ?? 0,
                          Icons.help_outline,
                        ),
                        if ((data.summary['clock_error'] ?? 0) > 0)
                          _count(
                            'Sai giờ',
                            data.summary['clock_error']!,
                            Icons.warning_amber,
                          ),
                      ],
                    ),
                  const SizedBox(height: 12),
                  Card(
                    child: ExpansionTile(
                      title: const Text('Tìm kiếm và lọc'),
                      initiallyExpanded: true,
                      childrenPadding: const EdgeInsets.all(16),
                      children: [
                        TextField(
                          controller: query,
                          onSubmitted: (_) => _apply(),
                          decoration: const InputDecoration(
                            labelText: 'Node ID hoặc tên Gateway',
                            prefixIcon: Icon(Icons.search),
                          ),
                        ),
                        const SizedBox(height: 12),
                        TextField(
                          controller: gateway,
                          onSubmitted: (_) => _apply(),
                          decoration: const InputDecoration(
                            labelText: 'Gateway chính xác (để trống = tất cả)',
                            hintText: 'border-router',
                          ),
                        ),
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Expanded(
                              child: DropdownButton<String>(
                                value: status,
                                isExpanded: true,
                                items:
                                    [
                                          '',
                                          'live',
                                          'stale',
                                          'offline',
                                          'never',
                                          'clock_error',
                                        ]
                                        .map(
                                          (s) => DropdownMenuItem(
                                            value: s,
                                            child: Text(
                                              s.isEmpty
                                                  ? 'Tất cả trạng thái'
                                                  : statusLabel(s),
                                            ),
                                          ),
                                        )
                                        .toList(),
                                onChanged: (v) {
                                  if (v != null) {
                                    setState(() => status = v);
                                    _apply();
                                  }
                                },
                              ),
                            ),
                            const SizedBox(width: 12),
                            FilledButton(
                              onPressed: _apply,
                              child: const Text('Áp dụng'),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  if (c.loading)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 10),
                      child: LinearProgressIndicator(),
                    ),
                  if (data != null && data.nodes.isEmpty)
                    const MessageBanner(
                      'Không có Node phù hợp. Kiểm tra bộ lọc và MQTT Consumer.',
                    ),
                  if (data != null)
                    ...data.nodes.map(
                      (node) => _nodeCard(
                        node,
                        c.readings[node.key],
                        c.error != null || c.connectionStale
                            ? null
                            : node.status(data.policy, c.serverNow),
                      ),
                    ),
                  if (data != null)
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        IconButton(
                          onPressed: data.page > 1 && !c.loading
                              ? () => c.changePage(data.page - 1)
                              : null,
                          icon: const Icon(Icons.chevron_left),
                        ),
                        Text(
                          'Trang ${data.page}/${data.pages} | ${data.count} Node',
                        ),
                        IconButton(
                          onPressed: data.page < data.pages && !c.loading
                              ? () => c.changePage(data.page + 1)
                              : null,
                          icon: const Icon(Icons.chevron_right),
                        ),
                      ],
                    ),
                  if (c.receivedAt != null)
                    Text(
                      'Lần tải API: ${formatTime(c.receivedAt)}. '
                      'Thống kê theo Gateway / tìm kiếm, trước lọc trạng thái.',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  const SizedBox(height: 20),
                ],
              ),
            ),
          ),
        );
      },
    ),
  );
  Widget _nodeCard(SensorNode node, SensorReading? r, String? state) {
    String fmt(double? v, int d) => v?.toStringAsFixed(d) ?? '--';
    Widget metric(IconData icon, String label, String value) => SizedBox(
      width: 130,
      child: Row(
        children: [
          Icon(icon, size: 20, color: Theme.of(context).colorScheme.primary),
          const SizedBox(width: 6),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: Theme.of(context).textTheme.bodySmall),
                Text(
                  value,
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: () => _open(node),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Node ${node.nodeId}',
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        Text(
                          node.gatewayId,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                  state == null
                      ? const Icon(Icons.cloud_off)
                      : StatusBadge(state),
                ],
              ),
              const SizedBox(height: 12),
              if (node.isHost && !(r?.hasSensorValues ?? false))
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 8),
                  child: Text('Điều phối mạng (không đo cảm biến)'),
                )
              else
                Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  children: [
                    metric(
                      Icons.thermostat_outlined,
                      'Nhiệt độ',
                      r?.temperature == null
                          ? '--'
                          : '${fmt(r!.temperature, 1)} °C',
                    ),
                    metric(
                      Icons.water_drop_outlined,
                      'Độ ẩm',
                      r?.humidity == null ? '--' : '${fmt(r!.humidity, 1)} %',
                    ),
                    metric(
                      Icons.light_mode_outlined,
                      'Ánh sáng',
                      r?.lightRaw == null ? '--' : '${fmt(r!.lightRaw, 0)} raw',
                    ),
                    metric(
                      Icons.speed_outlined,
                      'Áp suất',
                      r?.pressureHpa == null
                          ? '--'
                          : '${fmt(r!.pressureHpa, 1)} hPa',
                    ),
                  ],
                ),
              const SizedBox(height: 10),
              Text(
                'Nhận cuối: ${formatTime(node.lastSeen, date: true)}',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _pullRefresh() async {
    c.refresh();
    await Future<void>.delayed(const Duration(milliseconds: 300));
    for (var i = 0; i < 100 && c.loading; i++) {
      await Future<void>.delayed(const Duration(milliseconds: 100));
    }
  }

  Widget _count(String label, int value, IconData icon) => SizedBox(
    width: 138,
    child: Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, size: 20),
            const SizedBox(height: 6),
            Text(
              '$value',
              style: const TextStyle(fontSize: 25, fontWeight: FontWeight.bold),
            ),
            Text(label),
          ],
        ),
      ),
    ),
  );
}
