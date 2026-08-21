import 'package:flutter/material.dart';

import '../../core/permissions.dart';
import 'feature_definitions.dart';

/// A shell navigation destination (left sidebar entry).
class NavDestination {
  final String id;
  final String label;
  final IconData icon;
  final String permission;

  /// Optional Ctrl/Cmd+digit shortcut (1-based).
  final int? shortcutDigit;

  const NavDestination({
    required this.id,
    required this.label,
    required this.icon,
    required this.permission,
    this.shortcutDigit,
  });
}

/// Persistent sidebar destinations (desktop shell). `dashboard` renders the
/// live dashboard; every other destination is an honest "Unavailable" state
/// until the backend exposes its data endpoint.
const List<NavDestination> navDestinations = [
  NavDestination(id: 'dashboard', label: 'Dashboard', icon: Icons.dashboard_outlined, permission: Permissions.systemRead, shortcutDigit: 1),
  NavDestination(id: 'markets', label: 'Markets', icon: Icons.show_chart, permission: Permissions.tradingView, shortcutDigit: 2),
  NavDestination(id: 'watchlist', label: 'Watchlist', icon: Icons.star_border, permission: Permissions.tradingView),
  NavDestination(id: 'charts', label: 'Charts', icon: Icons.candlestick_chart_outlined, permission: Permissions.tradingView),
  NavDestination(id: 'orders', label: 'Orders', icon: Icons.receipt_long_outlined, permission: Permissions.tradingView, shortcutDigit: 3),
  NavDestination(id: 'positions', label: 'Positions', icon: Icons.pie_chart_outline, permission: Permissions.tradingView, shortcutDigit: 4),
  NavDestination(id: 'portfolio', label: 'Portfolio', icon: Icons.account_balance_wallet_outlined, permission: Permissions.tradingView),
  NavDestination(id: 'pnl', label: 'P&L', icon: Icons.trending_up, permission: Permissions.tradingView),
  NavDestination(id: 'strategies', label: 'Strategies', icon: Icons.hub_outlined, permission: Permissions.tradingView),
  NavDestination(id: 'risk', label: 'Risk', icon: Icons.shield_outlined, permission: Permissions.tradingView),
  NavDestination(id: 'brokers', label: 'Brokers', icon: Icons.link, permission: Permissions.tradingView),
  NavDestination(id: 'reconciliation', label: 'Reconcile', icon: Icons.fact_check_outlined, permission: Permissions.tradingView),
  NavDestination(id: 'settings', label: 'Settings', icon: Icons.settings_outlined, permission: Permissions.systemRead),
];

/// Resolve the [FeatureDefinition] for a destination id, or null when the
/// destination has a dedicated screen (e.g. `dashboard`).
FeatureDefinition? featureFor(String id) {
  for (final f in tradingFeatures) {
    if (f.id == id) return f;
  }
  return null;
}
