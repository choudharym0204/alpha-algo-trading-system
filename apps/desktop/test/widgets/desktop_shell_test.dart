import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:alpha_algo_desktop/auth/auth_controller.dart';
import 'package:alpha_algo_desktop/auth/auth_repository.dart';
import 'package:alpha_algo_desktop/auth/token_store.dart';
import 'package:alpha_algo_desktop/features/shell/desktop_shell.dart';
import 'package:alpha_algo_desktop/models/auth_models.dart';
import 'package:alpha_algo_desktop/network/api_client.dart';
import 'package:alpha_algo_desktop/repositories/system_controller.dart';
import 'package:alpha_algo_desktop/repositories/system_repository.dart';
import 'package:alpha_algo_desktop/websocket/ws_controller.dart';

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

  @override
  Future<TokenResponse> login(String email, String password) async => const TokenResponse(
        accessToken: 'a',
        refreshToken: 'r',
        tokenType: 'bearer',
        expiresIn: 900,
      );

  @override
  Future<CurrentUser> me(String token) async => const CurrentUser(
        subject: 'user-1',
        permissions: ['system:read', 'trading:view'],
      );
}

Future<AuthController> _authenticated() async {
  final auth = AuthController(repository: _FakeAuthRepository(), tokenStore: _FakeTokenStore());
  await auth.login('a@b.c', 'x');
  return auth;
}

Widget _shell(AuthController auth, SystemController system, WsController ws) {
  return MultiProvider(
    providers: [
      ChangeNotifierProvider<AuthController>.value(value: auth),
      ChangeNotifierProvider<SystemController>.value(value: system),
      ChangeNotifierProvider<WsController>.value(value: ws),
    ],
    child: const MaterialApp(home: DesktopShell()),
  );
}

void main() {
  testWidgets('renders sidebar destinations and top bar', (tester) async {
    tester.view.physicalSize = const Size(1600, 1200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final auth = await _authenticated();
    await tester.pumpWidget(_shell(auth, SystemController(SystemRepository(ApiClient())), WsController()));
    await tester.pump();

    expect(find.text('Alpha Algo'), findsOneWidget);
    expect(find.text('Dashboard'), findsWidgets); // sidebar + top-bar title
    expect(find.text('Markets'), findsOneWidget);
    expect(find.text('Watchlist'), findsOneWidget);
    expect(find.text('Orders'), findsOneWidget);
    expect(find.text('Positions'), findsOneWidget);
    expect(find.text('Settings'), findsOneWidget);
    expect(find.byTooltip('Sign out'), findsOneWidget);
  });

  testWidgets('navigates to a trading workspace on click', (tester) async {
    tester.view.physicalSize = const Size(1600, 1200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final auth = await _authenticated();
    await tester.pumpWidget(_shell(auth, SystemController(SystemRepository(ApiClient())), WsController()));
    await tester.pump();

    await tester.tap(find.text('Orders'));
    await tester.pump();
    expect(find.text('Unavailable'), findsOneWidget);
  });

  testWidgets('sign out transitions to unauthenticated', (tester) async {
    tester.view.physicalSize = const Size(1600, 1200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final auth = await _authenticated();
    await tester.pumpWidget(_shell(auth, SystemController(SystemRepository(ApiClient())), WsController()));
    await tester.pump();

    await tester.tap(find.byTooltip('Sign out'));
    await tester.pump();
    expect(auth.status, AuthStatus.unauthenticated);
  });
}
