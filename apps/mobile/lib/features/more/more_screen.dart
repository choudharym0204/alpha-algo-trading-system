import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../auth/auth_controller.dart';
import '../../core/permissions.dart';
import '../../widgets/design/app_status.dart';
import '../../widgets/unavailable_view.dart';
import '../shell/feature_definitions.dart';
import 'settings_screen.dart';

class MoreScreen extends StatelessWidget {
  const MoreScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();
    final showTrading = auth.hasPermission(Permissions.tradingView);

    return Scaffold(
      appBar: AppBar(
        title: const Text('More'),
        backgroundColor: AppColors.surfaceRaised,
      ),
      body: ListView(
        children: [
          if (showTrading) ...[
            _MoreTile(
              icon: Icons.analytics_outlined,
              label: 'P&L',
              onTap: () => _open(context, tradingFeatures[4]),
            ),
            _MoreTile(
              icon: Icons.auto_awesome_outlined,
              label: 'Strategies',
              onTap: () => _open(context, tradingFeatures[5]),
            ),
            _MoreTile(
              icon: Icons.shield_outlined,
              label: 'Risk',
              onTap: () => _open(context, tradingFeatures[6]),
            ),
            _MoreTile(
              icon: Icons.business_outlined,
              label: 'Brokers',
              onTap: () => _open(context, tradingFeatures[7]),
            ),
            _MoreTile(
              icon: Icons.compare_arrows,
              label: 'Reconciliation',
              onTap: () => _open(context, tradingFeatures[8]),
            ),
          ],
          _MoreTile(
            icon: Icons.settings_outlined,
            label: 'Settings',
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const SettingsScreen()),
            ),
          ),
        ],
      ),
    );
  }

  void _open(BuildContext context, FeatureDefinition feature) {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => UnavailableView(feature: feature)),
    );
  }
}

class _MoreTile extends StatelessWidget {
  const _MoreTile({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Icon(icon, color: AppColors.muted),
      title: Text(label, style: const TextStyle(color: Colors.white)),
      trailing: const Icon(Icons.chevron_right, color: AppColors.muted),
      onTap: onTap,
    );
  }
}
