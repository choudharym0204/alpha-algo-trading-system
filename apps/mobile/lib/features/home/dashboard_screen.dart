import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/trading_mode.dart';
import '../../repositories/system_controller.dart';
import '../../websocket/ws_controller.dart';
import '../../widgets/design/app_states.dart';
import '../../widgets/design/app_status.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final system = context.watch<SystemController>();

    if (system.loading) {
      return ListView(
        padding: const EdgeInsets.all(16),
        children: const [
          AppSkeleton(height: 96),
          AppSkeleton(height: 96),
          AppSkeleton(height: 96),
        ],
      );
    }

    if (system.error != null && system.health == null) {
      return AppErrorState(
        message: system.error!.message,
        onRetry: () => context.read<SystemController>().refresh(),
      );
    }

    final health = system.health;
    final readiness = system.readiness;
    final checks = readiness?.checks ?? const <String, String>{};

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Row(
          children: [
            Expanded(
              child: _StatCard(
                label: 'Service',
                value: health?.status ?? 'unknown',
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _StatCard(
                label: 'Trading mode',
                value: resolveTradingMode(health?.liveTrading).name.toUpperCase(),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: _StatCard(label: 'API', value: checks['api'] ?? 'unknown'),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _StatCard(label: 'Database', value: checks['database'] ?? 'unknown'),
            ),
          ],
        ),
        const SizedBox(height: 12),
        _SafetyCard(liveTrading: health?.liveTrading),
        const SizedBox(height: 12),
        _WsCard(),
        const SizedBox(height: 16),
        const Text(
          'Trading metrics',
          style: TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 4),
        const Text(
          'The backend does not yet expose trading data over the authenticated API. '
          'Metrics below are Unavailable — not zero — until their endpoints exist.',
          style: TextStyle(color: AppColors.muted, fontSize: 12),
        ),
        const SizedBox(height: 8),
        const _UnavailableMetric(label: 'Portfolio value'),
        const _UnavailableMetric(label: 'Cash / available funds'),
        const _UnavailableMetric(label: 'Daily P&L'),
        const _UnavailableMetric(label: 'Risk status'),
      ],
    );
  }
}

class _StatCard extends StatelessWidget {
  const _StatCard({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.surfaceRaised,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label.toUpperCase(),
            style: const TextStyle(color: AppColors.muted, fontSize: 10),
          ),
          const SizedBox(height: 4),
          Text(
            value,
            style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}

class _SafetyCard extends StatelessWidget {
  const _SafetyCard({required this.liveTrading});

  final String? liveTrading;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.surfaceRaised,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'Trading safety',
                style: TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600),
              ),
              TradingModeBadge(liveTrading: liveTrading),
            ],
          ),
          const SizedBox(height: 8),
          const Text(
            liveBlockedReason,
            style: TextStyle(color: AppColors.muted, fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class _WsCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final ws = context.watch<WsController>();
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.surfaceRaised,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Real-time gateway',
            style: TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 8),
          ConnectionIndicator(status: ws.status),
          if (ws.lastEvent != null) ...[
            const SizedBox(height: 6),
            Text(
              'status: ${ws.lastEvent!.status}, live_trading: ${ws.lastEvent!.liveTrading}',
              style: const TextStyle(color: AppColors.muted, fontSize: 12),
            ),
          ],
        ],
      ),
    );
  }
}

class _UnavailableMetric extends StatelessWidget {
  const _UnavailableMetric({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 4),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.surfaceRaised,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(color: AppColors.muted, fontSize: 13)),
          const Text(
            'Unavailable',
            style: TextStyle(color: AppColors.warn, fontSize: 12),
          ),
        ],
      ),
    );
  }
}
