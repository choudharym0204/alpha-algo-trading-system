/// Backend permission names (mirrors apps/api auth.py `Permissions`).
class Permissions {
  Permissions._();

  static const String systemRead = 'system:read';
  static const String tradingView = 'trading:view';
  static const String paperTrade = 'trading:paper';
  static const String liveTrade = 'trading:live';
}

/// Authorization is the BACKEND's boundary. This helper only drives what the
/// UI shows/hides; server 401/403 is always the final authority.
bool hasPermission(List<String>? permissions, String required) {
  return permissions != null && permissions.contains(required);
}
