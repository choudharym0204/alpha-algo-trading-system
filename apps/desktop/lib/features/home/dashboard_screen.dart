import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/trading_mode.dart';
import '../../repositories/system_controller.dart';
import '../../websocket/ws_controller.dart';
import '../../widgets/design/app_states.dart';
import '../../widgets/design/app_status.dart';

/// Desktop dashboard: dense multi-column readout of the only data the backend
/// actually exposes (health/readiness + live-trading + WebSocket). Trading
/// metrics remain honestly "Unavailable" (never zero) until endpoints exist.
class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final system = context.watch<SystemController>();

    if (system.loading) {
      return const Padding(
        padding: EdgeInsets.all(20),
        child: Column(
          children: [
            AppSkeleton(height: 96),
            AppSkeleton(height: 96),
            AppSkeleton(height: 96),
          ],
        ),
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
      padding: const EdgeInsets.all(20),
      children: [
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            _StatCard(label: 'Service', value: health?.status ?? 'unknown'),
            _StatCard(label: 'Trading mode', value: resolveTradingMode(health?.liveTrading).name.toUpperCase()),
            _StatCard(label: 'API', value: checks['api'] ?? 'unknown'),
            _StatCard(label: 'Database', value: checks['database'] ?? 'unknown'),
            _StatCard(label: 'Broker', value: checks['broker'] ?? 'unknown'),
          ],
        ),
        const SizedBox(height: 12),
        _SafetyCard(liveTrading: health?.liveTrading),
        const SizedBox(height: 12),
        const _WsCard(),
        const SizedBox(height: 20),
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
        const Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            _UnavailableMetric(label: 'Portfolio value'),
            _UnavailableMetric(label: 'Cash / available funds'),
            _UnavailableMetric(label: 'Daily P&L'),
            _UnavailableMetric(label: 'Risk status'),
          ],
        ),
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
    return SizedBox(
      width: 200,
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: AppColors.surfaceRaised,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: AppColors.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label.toUpperCase(), style: const TextStyle(color: AppColors.muted, fontSize: 10)),
            const SizedBox(height: 4),
            Text(
              value,
              style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
            ),
          ],
        ),
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
          const Text(liveBlockedReason, style: TextStyle(color: AppColors.muted, fontSize: 12)),
        ],
      ),
    );
  }
}

class _WsCard extends StatelessWidget {
  const _WsCard();

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
    return SizedBox(
      width: 240,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: AppColors.surfaceRaised,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: AppColors.border),
        ),
        child: Row(
          children: [
            Expanded(
              child: Text(
                label,
                style: const TextStyle(color: AppColors.muted, fontSize: 13),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            const SizedBox(width: 8),
            const Text('Unavailable', style: TextStyle(color: AppColors.warn, fontSize: 12)),
          ],
        ),
      ),
    );
  }
}
