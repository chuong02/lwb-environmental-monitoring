import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'data/api_service.dart';
import 'screens/overview_screen.dart';

const defaultBackend = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://10.0.2.2:8001',
);
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = SharedPreferencesAsync();
  String saved;
  try {
    saved = await prefs.getString('lwb_backend_url') ?? defaultBackend;
    ApiService.validateBase(saved);
  } catch (_) {
    saved = defaultBackend;
  }
  try {
    ApiService.validateBase(saved);
  } on FormatException catch (e) {
    runApp(
      MaterialApp(
        home: Scaffold(
          body: SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Text('Cau hinh Backend URL khong hop le: ${e.message}'),
            ),
          ),
        ),
      ),
    );
    return;
  }
  runApp(LwbApp(initialUrl: saved, preferences: prefs));
}

class LwbApp extends StatefulWidget {
  final String initialUrl;
  final SharedPreferencesAsync preferences;
  const LwbApp({
    super.key,
    required this.initialUrl,
    required this.preferences,
  });
  @override
  State<LwbApp> createState() => _LwbAppState();
}

class _LwbAppState extends State<LwbApp> {
  late String baseUrl;
  @override
  void initState() {
    super.initState();
    baseUrl = widget.initialUrl;
  }

  Future<void> _save(String value) async {
    try {
      await widget.preferences.setString('lwb_backend_url', value);
    } catch (_) {
      /* Apply to the current session even when local persistence fails. */
    }
    if (mounted) setState(() => baseUrl = value);
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    debugShowCheckedModeBanner: false,
    title: 'LWB Monitor',
    theme: ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF205CAD)),
      scaffoldBackgroundColor: const Color(0xFFF4F7FB),
      appBarTheme: const AppBarTheme(
        backgroundColor: Color(0xFFF4F7FB),
        centerTitle: false,
      ),
      inputDecorationTheme: InputDecorationTheme(
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
      ),
    ),
    home: OverviewScreen(
      key: ValueKey(baseUrl),
      baseUrl: baseUrl,
      onChangeUrl: _save,
    ),
  );
}
