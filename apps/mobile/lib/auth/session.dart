/// In-memory representation of an established session.
class Session {
  final String accessToken;
  final String refreshToken;
  final DateTime accessExpiresAt;

  const Session({
    required this.accessToken,
    required this.refreshToken,
    required this.accessExpiresAt,
  });

  /// True when the access token is present and not yet expired (5s skew).
  bool isAccessTokenUsable([DateTime? now]) {
    final n = now ?? DateTime.now();
    return n.isBefore(accessExpiresAt.subtract(const Duration(seconds: 5)));
  }
}
