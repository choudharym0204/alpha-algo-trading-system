import 'dart:io' show Platform;

/// Public-only environment configuration.
///
/// The mobile app points at the backend via these URLs only. Nothing here can
/// ever surface a secret, and no widget reads `Platform.environment` ad hoc.
/// Production builds read from `--dart-define` (see README); the values below
/// are local-development defaults.
class AppConfig {
  AppConfig._();

  static const String _definedApi =
      String.fromEnvironment('API_BASE_URL', defaultValue: '');
  static const String _definedWs =
      String.fromEnvironment('WS_URL', defaultValue: '');

  /// Backend REST base URL (no trailing slash).
  static String get apiBaseUrl =>
      _definedApi.isNotEmpty ? _strip(_definedApi) : _defaultApiBaseUrl;

  /// Backend WebSocket base URL (ws:// or wss://, no trailing slash).
  static String get wsUrl => _definedWs.isNotEmpty ? _strip(_definedWs) : _defaultWsUrl;

  static const String wsPath = '/api/v1/ws';

  // Android emulator reaches the host machine via 10.0.2.2; iOS simulator and
  // desktop use localhost. Physical devices must pass --dart-define.
  static String get _defaultApiBaseUrl =>
      Platform.isAndroid ? 'http://10.0.2.2:8000' : 'http://localhost:8000';

  static String get _defaultWsUrl =>
      Platform.isAndroid ? 'ws://10.0.2.2:8000' : 'ws://localhost:8000';

  static String _strip(String value) => value.endsWith('/')
      ? value.substring(0, value.length - 1)
      : value;
}
