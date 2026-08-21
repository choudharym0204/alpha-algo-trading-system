import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../auth/auth_controller.dart';
import '../../core/permissions.dart';
import '../../repositories/system_controller.dart';
import '../../websocket/ws_controller.dart';
import '../../widgets/design/app_status.dart';
import '../../widgets/unavailable_view.dart';
import '../home/dashboard_screen.dart';
import '../more/more_screen.dart';
import 'feature_definitions.dart';

class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int _index = 0;

  List<_Tab> _visibleTabs(BuildContext context) {
    final auth = context.read<AuthController>();
    final tabs = <_Tab>[
      _Tab(
        label: 'Home',
        icon: Icons.dashboard_outlined,
        permission: Permissions.systemRead,
        builder: (context) => const DashboardScreen(),
      ),
      _Tab(
        label: 'Markets',
        icon: Icons.show_chart,
        permission: Permissions.tradingView,
        builder: (context) => UnavailableView(feature: tradingFeatures[0]),
      ),
      _Tab(
        label: 'Orders',
        icon: Icons.receipt_long_outlined,
        permission: Permissions.tradingView,
        builder: (context) => UnavailableView(feature: tradingFeatures[1]),
      ),
      _Tab(
        label: 'Positions',
        icon: Icons.pie_chart_outline,
        permission: Permissions.tradingView,
        builder: (context) => UnavailableView(feature: tradingFeatures[2]),
      ),
      _Tab(
        label: 'Portfolio',
        icon: Icons.account_balance_wallet_outlined,
        permission: Permissions.tradingView,
        builder: (context) => UnavailableView(feature: tradingFeatures[3]),
      ),
      _Tab(
        label: 'More',
        icon: Icons.more_horiz,
        permission: Permissions.systemRead,
        builder: (context) => const MoreScreen(),
      ),
    ];
    return tabs.where((tab) => auth.hasPermission(tab.permission)).toList();
  }

  @override
  Widget build(BuildContext context) {
    final tabs = _visibleTabs(context);
    if (_index >= tabs.length) _index = 0;

    return Scaffold(
      appBar: AppBar(
        backgroundColor: AppColors.surfaceRaised,
        title: const Text('Alpha Algo', style: TextStyle(fontSize: 16)),
        actions: [
          Consumer<SystemController>(
            builder: (context, system, _) =>
                TradingModeBadge(liveTrading: system.health?.liveTrading),
          ),
          const SizedBox(width: 12),
          Consumer<WsController>(
            builder: (context, ws, _) => ConnectionIndicator(status: ws.status),
          ),
          IconButton(
            tooltip: 'Sign out',
            icon: const Icon(Icons.logout),
            onPressed: () => context.read<AuthController>().logout(),
          ),
        ],
      ),
      body: IndexedStack(
        index: _index,
        children: tabs.map((tab) => tab.builder(context)).toList(),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (index) => setState(() => _index = index),
        destinations: tabs
            .map(
              (tab) => NavigationDestination(
                icon: Icon(tab.icon),
                label: tab.label,
              ),
            )
            .toList(),
      ),
    );
  }
}

class _Tab {
  final String label;
  final IconData icon;
  final String permission;
  final Widget Function(BuildContext context) builder;

  const _Tab({
    required this.label,
    required this.icon,
    required this.permission,
    required this.builder,
  });
}
