import 'dart:async';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../config/app_config.dart';
import '../models/ws_models.dart';

enum WsStatus { connecting, open, closed, reconnecting }

/// Authenticated WebSocket client for /api/v1/ws.
///
/// - Connects with the access token as a query param (backend contract).
/// - Validates incoming messages to the known HEALTH_UPDATE shape and drops
///   unknown/malformed payloads (typed event model).
/// - Reconnects with bounded backoff; a user-triggered close stops reconnecting.
class WsClient {
  WsClient({required this.onEvent, required this.onStatus});

  final void Function(HealthUpdateEvent event) onEvent;
  final void Function(WsStatus status) onStatus;

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _subscription;
  Timer? _timer;
  bool _closed = false;
  int _attempt = 0;

  void connect(String token) {
    if (_closed || _channel != null) return;
    onStatus(_attempt == 0 ? WsStatus.connecting : WsStatus.reconnecting);

    final url =
        '${AppConfig.wsUrl}${AppConfig.wsPath}?token=${Uri.encodeQueryComponent(token)}';
    try {
      _channel = WebSocketChannel.connect(Uri.parse(url));
    } catch (_) {
      _scheduleReconnect(token);
      return;
    }

    _subscription = _channel!.stream.listen(
      (data) {
        final event = normalizeWsEvent(data);
        if (event != null) onEvent(event);
      },
      onDone: () => _handleDone(token),
      onError: (Object _) {
        // onDone follows onError; state transitions are driven there.
      },
    );
    _attempt = 0;
    onStatus(WsStatus.open);
  }

  void _handleDone(String token) {
    _reset();
    onStatus(WsStatus.closed);
    _scheduleReconnect(token);
  }

  void _scheduleReconnect(String token) {
    if (_closed) return;
    _timer?.cancel();
    final shift = _attempt.clamp(0, 8).toInt();
    final delayMs = 1000 * (1 << shift);
    _attempt += 1;
    _timer = Timer(Duration(milliseconds: delayMs), () => connect(token));
  }

  void _reset() {
    _subscription?.cancel();
    _subscription = null;
    _channel = null;
  }

  void close() {
    _closed = true;
    _timer?.cancel();
    _timer = null;
    _subscription?.cancel();
    _subscription = null;
    _channel?.sink.close();
    _channel = null;
    onStatus(WsStatus.closed);
  }
}
