import 'package:flutter/material.dart';

import '../../core/trading_mode.dart';
import '../../websocket/ws_client.dart' show WsStatus;

/// Minimal terminal palette.
abstract final class AppColors {
  static const surface = Color(0xFF0B0F17);
  static const surfaceRaised = Color(0xFF111827);
  static const border = Color(0xFF1F2937);
  static const accent = Color(0xFF22C55E);
  static const sell = Color(0xFFEF4444);
  static const warn = Color(0xFFF59E0B);
  static const info = Color(0xFF38BDF8);
  static const muted = Color(0xFF9CA3AF);
}

/// Status badge: a colored pill with TEXT. State is never communicated by
/// color alone (non-color-only indication).
class AppStatusBadge extends StatelessWidget {
  const AppStatusBadge({
    super.key,
    required this.label,
    this.background = AppColors.border,
    this.foreground = AppColors.muted,
  });

  final String label;
  final Color background;
  final Color foreground;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: foreground,
          fontSize: 11,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

/// Authoritative trading-mode badge. Reflects the backend `live_trading` signal
/// only — it has no toggle and cannot enable LIVE.
class TradingModeBadge extends StatelessWidget {
  const TradingModeBadge({super.key, this.liveTrading});

  final String? liveTrading;

  @override
  Widget build(BuildContext context) {
    final mode = resolveTradingMode(liveTrading);
    return switch (mode) {
      TradingMode.live => const AppStatusBadge(
          label: 'LIVE',
          background: Color(0x33EF4444),
          foreground: AppColors.sell,
        ),
      TradingMode.paper => const AppStatusBadge(
          label: 'PAPER',
          background: Color(0x3338BDF8),
          foreground: AppColors.info,
        ),
      TradingMode.unknown => const AppStatusBadge(
          label: 'MODE UNKNOWN',
          background: Color(0x33F59E0B),
          foreground: AppColors.warn,
        ),
    };
  }
}

/// WebSocket connection indicator: dot + text (never color-only).
class ConnectionIndicator extends StatelessWidget {
  const ConnectionIndicator({super.key, required this.status});

  final WsStatus status;

  @override
  Widget build(BuildContext context) {
    final (tone, label) = switch (status) {
      WsStatus.connecting => (AppColors.warn, 'Connecting'),
      WsStatus.open => (AppColors.accent, 'Connected'),
      WsStatus.closed => (AppColors.sell, 'Disconnected'),
      WsStatus.reconnecting => (AppColors.warn, 'Reconnecting'),
    };
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(color: tone, shape: BoxShape.circle),
        ),
        const SizedBox(width: 6),
        Text(label, style: const TextStyle(color: AppColors.muted, fontSize: 12)),
      ],
    );
  }
}
