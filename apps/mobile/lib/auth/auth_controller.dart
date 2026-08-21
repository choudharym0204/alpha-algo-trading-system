import 'package:flutter/foundation.dart';

import '../core/api_error.dart';
import '../models/auth_models.dart';
import 'auth_repository.dart';
import 'session.dart';
import 'token_store.dart';

enum AuthStatus { loading, authenticated, unauthenticated }

/// Auth state machine: login / refresh / restore / logout against the real
/// backend contract. Tokens are held in secure storage (via [TokenStore]) and
/// the in-memory [Session]; the backend remains the security authority.
class AuthController extends ChangeNotifier {
  AuthController({
    required AuthRepository repository,
    required TokenStore tokenStore,
  })  : _repository = repository,
        _tokenStore = tokenStore;

  final AuthRepository _repository;
  final TokenStore _tokenStore;

  AuthStatus _status = AuthStatus.loading;
  CurrentUser? _user;
  Session? _session;
  ApiError? _error;

  AuthStatus get status => _status;
  CurrentUser? get user => _user;
  ApiError? get error => _error;
  Session? get session => _session;
  String? get accessToken => _session?.accessToken;

  bool hasPermission(String permission) => _user?.hasPermission(permission) ?? false;

  Session _toSession(TokenResponse token) {
    return Session(
      accessToken: token.accessToken,
      refreshToken: token.refreshToken,
      accessExpiresAt: DateTime.now().add(Duration(seconds: token.expiresIn)),
    );
  }

  Future<void> _applyUser(String accessToken) async {
    _user = await _repository.me(accessToken);
    _status = AuthStatus.authenticated;
    _error = null;
    notifyListeners();
  }

  /// Restore a persisted session on app launch. There is no stored expiry, so
  /// we validate the access token via `/me` directly and fall back to refresh
  /// on a 401.
  Future<void> restore() async {
    _status = AuthStatus.loading;
    notifyListeners();
    try {
      final access = await _tokenStore.readAccessToken();
      if (access == null) {
        _status = AuthStatus.unauthenticated;
        notifyListeners();
        return;
      }
      final refresh = await _tokenStore.readRefreshToken();
      _session = Session(
        accessToken: access,
        refreshToken: refresh ?? '',
        accessExpiresAt: DateTime.now(),
      );
      try {
        await _applyUser(access);
        return;
      } on ApiError catch (e) {
        if (!e.isUnauthorized) rethrow;
      }
      if (refresh != null && refresh.isNotEmpty) {
        await _refresh();
        return;
      }
      await _logout(clearStorage: true);
    } on ApiError catch (e) {
      await _fail(e);
    } catch (_) {
      await _fail(const ApiError(
        status: 0,
        code: 'RESTORE_FAILED',
        message: 'Unable to restore the session.',
        requestId: 'unknown',
      ));
    }
  }

  Future<void> _refresh() async {
    final session = _session;
    if (session == null || session.refreshToken.isEmpty) {
      await _logout(clearStorage: true);
      return;
    }
    final token = await _repository.refresh(session.refreshToken);
    await _tokenStore.writeTokens(
      access: token.accessToken,
      refresh: token.refreshToken,
    );
    _session = _toSession(token);
    await _applyUser(token.accessToken);
  }

  Future<void> login(String email, String password) async {
    _status = AuthStatus.loading;
    _error = null;
    notifyListeners();
    try {
      final token = await _repository.login(email, password);
      await _tokenStore.writeTokens(
        access: token.accessToken,
        refresh: token.refreshToken,
      );
      _session = _toSession(token);
      await _applyUser(token.accessToken);
    } on ApiError catch (e) {
      await _fail(e);
    } catch (_) {
      await _fail(const ApiError(
        status: 0,
        code: 'LOGIN_FAILED',
        message: 'Unable to sign in. Please try again.',
        requestId: 'unknown',
      ));
    }
  }

  Future<void> logout() => _logout(clearStorage: true);

  Future<void> _logout({required bool clearStorage}) async {
    if (clearStorage) {
      await _tokenStore.clear();
    }
    _session = null;
    _user = null;
    _error = null;
    _status = AuthStatus.unauthenticated;
    notifyListeners();
  }

  Future<void> _fail(ApiError error) async {
    await _tokenStore.clear();
    _session = null;
    _user = null;
    _error = error;
    _status = AuthStatus.unauthenticated;
    notifyListeners();
  }
}
