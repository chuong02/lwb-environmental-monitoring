import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/telemetry.dart';

class ApiException implements Exception {
  final String message;
  final int? statusCode;
  const ApiException(this.message, [this.statusCode]);
  @override
  String toString() => message;
}

class ApiService {
  final Uri base;
  final http.Client Function() _clientFactory;
  final Set<http.Client> _activeClients = {};
  bool _closed = false;
  ApiService(String baseUrl, {http.Client Function()? clientFactory})
    : base = validateBase(baseUrl),
      _clientFactory = clientFactory ?? http.Client.new;
  static Uri validateBase(String value) {
    final uri = Uri.tryParse(value.trim());
    if (uri == null ||
        !['http', 'https'].contains(uri.scheme) ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment ||
        (uri.path.isNotEmpty && uri.path != '/')) {
      throw const FormatException(
        'Nhap URL goc, vi du http://100.x.x.x:8001 (khong them /api).',
      );
    }
    return uri.replace(path: '');
  }

  Future<Map<String, dynamic>> get(
    String path, [
    Map<String, String>? query,
  ]) async {
    if (_closed) throw const ApiException('Kết nối da dong.');
    final client = _clientFactory();
    _activeClients.add(client);
    final uri = base.replace(
      path: '/api/mobile/v1/$path',
      queryParameters: query,
    );
    try {
      final result = await client
          .get(uri, headers: {'Accept': 'application/json'})
          .timeout(const Duration(seconds: 8));
      if (result.statusCode != 200) {
        final hint = switch (result.statusCode) {
          401 || 403 => 'API tu choi truy cap. Kiem tra server local port 8001 / quyen tai khoan.',
          404 =>
            'Khong tim thay API hoac Node. Kiem tra da cai backend Mobile V1.',
          429 => 'Qua nhieu yeu cau. Ung dung se thu lai cham hon.',
          _ => 'May chu tra HTTP ${result.statusCode}.',
        };
        throw ApiException(hint, result.statusCode);
      }
      return jsonObject(jsonDecode(utf8.decode(result.bodyBytes)));
    } on TimeoutException {
      throw const ApiException(
        'Qua 8 giay chua co phan hoi. Kiem tra WSL va Django.',
      );
    } on FormatException {
      throw const ApiException(
        'Phan hoi khong dung JSON Mobile V1. Kiem tra URL /api/mobile/v1/.',
      );
    } on http.ClientException {
      throw const ApiException(
        'Khong ket noi duoc API. Kiem tra server, dia chi va mang.',
      );
    } finally {
      // Closing cancels the actual request after a timeout, not just the Future.
      client.close();
      _activeClients.remove(client);
    }
  }

  void cancelActive() {
    for (final client in _activeClients.toList()) {
      client.close();
    }
    _activeClients.clear();
  }

  void close() {
    _closed = true;
    cancelActive();
  }
}
