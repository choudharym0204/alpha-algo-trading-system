import 'dart:convert';

/// Typed WebSocket event model for /api/v1/ws.
///
/// The backend currently emits only HEALTH_UPDATE. Unknown/malformed messages
/// are dropped at the validation boundary and never mutate application state.
class HealthUpdateEvent {
  final String service;
  final String status;
  final String liveTrading;

  const HealthUpdateEvent({
    required this.service,
    required this.status,
    required this.liveTrading,
  });
}

/// Validate + normalize a raw WebSocket message string into a typed event.
///
/// Returns null for anything that is not a well-formed HEALTH_UPDATE, so
/// malformed/unknown payloads never reach repository/UI state.
HealthUpdateEvent? normalizeWsEvent(dynamic raw) {
  if (raw is! String) return null;
  final dynamic parsed;
  try {
    parsed = jsonDecode(raw);
  } catch (_) {
    return null;
  }
  if (parsed is! Map<String, dynamic>) return null;
  if (parsed['type'] != 'HEALTH_UPDATE') return null;
  final payload = parsed['payload'];
  if (payload is! Map<String, dynamic>) return null;
  final service = payload['service'];
  final status = payload['status'];
  final liveTrading = payload['live_trading'];
  if (service is! String || status is! String || liveTrading is! String) {
    return null;
  }
  return HealthUpdateEvent(
    service: service,
    status: status,
    liveTrading: liveTrading,
  );
}
