import 'package:flutter/material.dart';

import '../data/api_service.dart';

class ConnectionDialog extends StatefulWidget {
  final String initialUrl;
  const ConnectionDialog({super.key, required this.initialUrl});
  @override
  State<ConnectionDialog> createState() => _ConnectionDialogState();
}

class _ConnectionDialogState extends State<ConnectionDialog> {
  late final TextEditingController editor;
  String? validation;
  @override
  void initState() {
    super.initState();
    editor = TextEditingController(text: widget.initialUrl);
  }

  @override
  void dispose() {
    editor.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Kết nối Django API'),
    content: SizedBox(
      width: 440,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text(
            'Điện thoại thật (Tailscale): http://100.x.x.x:8001\nAndroid Emulator: http://10.0.2.2:8001\nKhông dùng cổng React 5173.',
          ),
          const SizedBox(height: 12),
          TextField(
            controller: editor,
            autocorrect: false,
            keyboardType: TextInputType.url,
            decoration: InputDecoration(
              labelText: 'Backend URL',
              hintText: 'http://100.x.x.x:8001',
              errorText: validation,
            ),
          ),
          const SizedBox(height: 12),
          const Text('Bản giám sát nội bộ. Chưa có đăng nhập / điều khiển.'),
        ],
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Hủy'),
      ),
      FilledButton(
        onPressed: () {
          try {
            final uri = ApiService.validateBase(editor.text);
            Navigator.pop(context, uri.toString());
          } on FormatException catch (e) {
            setState(() => validation = e.message);
          }
        },
        child: const Text('Lưu'),
      ),
    ],
  );
}
