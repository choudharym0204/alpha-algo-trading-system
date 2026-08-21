import '../models/auth_models.dart';
import '../network/api_client.dart';

/// Data-access for the backend auth contract (login / refresh / me).
class AuthRepository {
  AuthRepository(this._api);

  final ApiClient _api;

  Future<TokenResponse> login(String email, String password) async {
    final data = await _api.post(
      '/api/v1/auth/login',
      body: LoginRequest(email: email, password: password).toJson(),
    );
    return TokenResponse.fromJson(data as Map<String, dynamic>);
  }

  Future<TokenResponse> refresh(String refreshToken) async {
    final data = await _api.post(
      '/api/v1/auth/refresh',
      body: RefreshRequest(refreshToken: refreshToken).toJson(),
    );
    return TokenResponse.fromJson(data as Map<String, dynamic>);
  }

  Future<CurrentUser> me(String token) async {
    final data = await _api.get('/api/v1/auth/me', token: token);
    return CurrentUser.fromJson(data as Map<String, dynamic>);
  }
}
