import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lwb_mobile/data/api_service.dart';
void main() {
  test('query parameters encode gateway names correctly', () async {
    final api = ApiService('http://10.0.2.2:8001', clientFactory: () => MockClient((request) async {
      expect(request.url.path, '/api/mobile/v1/nodes/25/latest/');
      expect(request.url.queryParameters['gateway'], 'plant A:edge/1');
      return http.Response('{"ok":true}', 200);
    }));
    expect(await api.get('nodes/25/latest/', {'gateway': 'plant A:edge/1'}), {'ok': true}); api.close();
  });
  test('HTTP failure is not interpreted as an empty node list', () async {
    final api = ApiService('http://localhost:8001', clientFactory: () => MockClient((_) async => http.Response('error', 503)));
    await expectLater(api.get('nodes/'), throwsA(isA<ApiException>())); api.close();
  });
  test('wrong legacy response is rejected', () async {
    final api = ApiService('http://localhost:8001', clientFactory: () => MockClient((_) async => http.Response('[]', 200)));
    await expectLater(api.get('nodes/'), throwsA(isA<ApiException>())); api.close();
  });
  test('credentials in base URL and API suffix are rejected', () {
    expect(() => ApiService.validateBase('http://u:p@host'), throwsFormatException);
    expect(() => ApiService.validateBase('http://localhost:8001/api'), throwsFormatException);
  });
}
