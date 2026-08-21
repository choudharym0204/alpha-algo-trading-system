/// TypeScript/Dart mirror of the backend Pydantic auth schemas
/// (apps/api/.../schemas/auth.py). Hand-maintained to match the backend exactly.
class TokenResponse {
  final String accessToken;
  final String refreshToken;
  final String tokenType;
  final int expiresIn;

  const TokenResponse({
    required this.accessToken,
    required this.refreshToken,
    required this.tokenType,
    required this.expiresIn,
  });

  factory TokenResponse.fromJson(Map<String, dynamic> json) {
    return TokenResponse(
      accessToken: json['access_token'] as String,
      refreshToken: json['refresh_token'] as String,
      tokenType: (json['token_type'] as String?) ?? 'bearer',
      expiresIn: json['expires_in'] as int,
    );
  }
}

class LoginRequest {
  final String email;
  final String password;

  const LoginRequest({required this.email, required this.password});

  Map<String, dynamic> toJson() => {'email': email, 'password': password};
}

class RefreshRequest {
  final String refreshToken;

  const RefreshRequest({required this.refreshToken});

  Map<String, dynamic> toJson() => {'refresh_token': refreshToken};
}

class CurrentUser {
  final String subject;
  final List<String> permissions;

  const CurrentUser({required this.subject, required this.permissions});

  factory CurrentUser.fromJson(Map<String, dynamic> json) {
    final perms = json['permissions'];
    return CurrentUser(
      subject: json['subject'] as String,
      permissions: perms is List ? perms.cast<String>() : const <String>[],
    );
  }

  bool hasPermission(String permission) => permissions.contains(permission);
}
