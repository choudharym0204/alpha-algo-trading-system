import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'auth/auth_controller.dart';
import 'auth/auth_repository.dart';
import 'auth/token_store.dart';
import 'features/auth/login_screen.dart';
import 'features/shell/app_shell.dart';
import 'network/api_client.dart';
import 'repositories/system_controller.dart';
import 'repositories/system_repository.dart';
import 'websocket/ws_controller.dart';
import 'widgets/design/app_status.dart';

class AlphaAlgoApp extends StatefulWidget {
  const AlphaAlgoApp({super.key});

  @override
  State<AlphaAlgoApp> createState() => _AlphaAlgoAppState();
}

class _AlphaAlgoAppState extends State<AlphaAlgoApp> {
  final ApiClient _api = ApiClient();
  late final AuthController _authController = AuthController(
    repository: AuthRepository(_api),
    tokenStore: SecureTokenStore(),
  );
  late final SystemController _systemController = SystemController(SystemRepository(_api));
  late final WsController _wsController = WsController();

  @override
  void initState() {
    super.initState();
    _authController.addListener(_syncWs);
    _authController.restore();
    _systemController.start();
  }

  void _syncWs() {
    if (_authController.status == AuthStatus.authenticated) {
      final token = _authController.accessToken;
      if (token != null) {
        _wsController.start(token);
      }
    } else {
      _wsController.stop();
    }
  }

  @override
  void dispose() {
    _authController.removeListener(_syncWs);
    _wsController.dispose();
    _systemController.dispose();
    _authController.dispose();
    _api.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider<AuthController>.value(value: _authController),
        ChangeNotifierProvider<SystemController>.value(value: _systemController),
        ChangeNotifierProvider<WsController>.value(value: _wsController),
      ],
      child: MaterialApp(
        title: 'Alpha Algo',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          useMaterial3: true,
          brightness: Brightness.dark,
          scaffoldBackgroundColor: AppColors.surface,
          colorScheme: const ColorScheme.dark(
            primary: AppColors.accent,
            secondary: AppColors.info,
            surface: AppColors.surfaceRaised,
          ),
        ),
        home: const RootGate(),
      ),
    );
  }
}

/// Switches between splash / login / shell based on auth status.
class RootGate extends StatelessWidget {
  const RootGate({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();
    switch (auth.status) {
      case AuthStatus.loading:
        return const _SplashScreen();
      case AuthStatus.unauthenticated:
        return const LoginScreen();
      case AuthStatus.authenticated:
        return const AppShell();
    }
  }
}

class _SplashScreen extends StatelessWidget {
  const _SplashScreen();

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: Center(child: CircularProgressIndicator()),
    );
  }
}
