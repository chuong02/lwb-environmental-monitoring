import 'package:flutter/material.dart';

import '../models/telemetry.dart';

Color statusColor(String state) => switch (state) {
  'live' => const Color(0xFF00897B),
  'stale' => const Color(0xFFB26A00),
  'offline' => const Color(0xFFB3261E),
  'clock_error' => const Color(0xFF7B1FA2),
  _ => const Color(0xFF607D8B),
};

class StatusBadge extends StatelessWidget {
  final String status;
  const StatusBadge(this.status, {super.key});
  @override
  Widget build(BuildContext context) => Chip(
    visualDensity: VisualDensity.compact,
    avatar: Icon(Icons.circle, size: 10, color: statusColor(status)),
    label: Text(
      statusLabel(status),
      style: TextStyle(color: statusColor(status)),
    ),
    backgroundColor: statusColor(status).withAlpha(18),
    side: BorderSide.none,
  );
}

class MessageBanner extends StatelessWidget {
  final String message;
  final bool error;
  const MessageBanner(this.message, {super.key, this.error = false});
  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    margin: const EdgeInsets.only(bottom: 12),
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: error ? const Color(0xFFFFEBEE) : const Color(0xFFE8F0FE),
      borderRadius: BorderRadius.circular(12),
    ),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(
          error ? Icons.cloud_off : Icons.info_outline,
          size: 20,
          color: error ? Colors.red.shade800 : Colors.blue.shade800,
        ),
        const SizedBox(width: 10),
        Expanded(child: Text(message)),
      ],
    ),
  );
}

class MetricCard extends StatelessWidget {
  final String title, unit, source;
  final double? value;
  final IconData icon;
  final int decimals;
  const MetricCard({
    super.key,
    required this.title,
    required this.value,
    required this.unit,
    required this.source,
    required this.icon,
    this.decimals = 1,
  });
  @override
  Widget build(BuildContext context) => Card(
    margin: EdgeInsets.zero,
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: Theme.of(context).colorScheme.primary),
          const SizedBox(height: 12),
          Text(title),
          const SizedBox(height: 8),
          Wrap(
            crossAxisAlignment: WrapCrossAlignment.end,
            spacing: 5,
            children: [
              Text(
                value?.toStringAsFixed(decimals) ?? '--',
                style: const TextStyle(
                  fontSize: 28,
                  fontWeight: FontWeight.bold,
                ),
              ),
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text(unit),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            value == null ? 'Không có số đo hợp lệ' : source,
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    ),
  );
}
