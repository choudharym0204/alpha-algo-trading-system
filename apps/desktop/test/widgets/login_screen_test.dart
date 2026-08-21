import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:alpha_algo_desktop/auth/auth_controller.dart';
import 'package:alpha_algo_desktop/auth/auth_repository.dart';
import 'package:alpha_algo_desktop/auth/token_store.dart';
import 'package:alpha_algo_desktop/features/auth/login_screen.dart';
import 'package:alpha_algo_desktop/network/api_client.dart';

class _FakeTokenStore implements TokenStore {
  @override
  Future<String?> readAccessToken() async => null;

  @override
  Future<String?> readRefreshToken() async => null;

  @override
  Future<void> writeTokens({required String access, required String refresh}) async {}

  @override
  Future<void> clear() async {}
}

class _FakeAuthRepository extends AuthRepository {
  _FakeAuthRepository() : super(ApiClient());
}

void main() {
  testWidgets('shows validation errors on empty submit', (tester) async {
    final controller = AuthController(
      repository: _FakeAuthRepository(),
      tokenStore: _FakeTokenStore(),
    );
    await tester.pumpWidget(
      ChangeNotifierProvider<AuthController>.value(
        value: controller,
        child: const MaterialApp(home: LoginScreen()),
      ),
    );
    await tester.tap(find.text('Sign in'));
    await tester.pump();
    expect(find.text('Email is required'), findsOneWidget);
    expect(find.text('Password is required'), findsOneWidget);
  });

  testWidgets('shows fail-closed PAPER messaging', (tester) async {
    final controller = AuthController(
      repository: _FakeAuthRepository(),
      tokenStore: _FakeTokenStore(),
    );
    await tester.pumpWidget(
      ChangeNotifierProvider<AuthController>.value(
        value: controller,
        child: const MaterialApp(home: LoginScreen()),
      ),
    );
    expect(find.text('Live trading is disabled by the backend.'), findsOneWidget);
    expect(find.text('PAPER mode'), findsOneWidget);
  });
}
