import 'package:flutter/foundation.dart';

import '../models/ws_models.dart';
import 'ws_client.dart';

/// Holds live WebSocket connection status and the last validated event.
/// The app shell reads this to render the connection indicator.
class WsController extends ChangeNotifier {
  WsClient? _client;
  WsStatus _status = WsStatus.closed;
  HealthUpdateEvent? _lastEvent;

  WsStatus get status => _status;
  HealthUpdateEvent? get lastEvent => _lastEvent;

  void start(String token) {
    stop();
    _client = WsClient(
      onStatus: (status) {
        _status = status;
        notifyListeners();
      },
      onEvent: (event) {
        _lastEvent = event;
        notifyListeners();
      },
    );
    _client!.connect(token);
  }

  void stop() {
    _client?.close();
    _client = null;
    _status = WsStatus.closed;
  }
}
