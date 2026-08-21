import 'package:flutter/material.dart';

import '../features/shell/feature_definitions.dart';
import 'design/app_status.dart';
import 'design/app_states.dart';

/// Honest "backend boundary not yet exposed" state for a workspace panel.
///
/// Trading data has no REST/WS endpoint yet, so these panels show this state
/// instead of fabricating zeros or mock values (Phase 19 §4 / §55). No Scaffold
/// of its own — it is embedded in the desktop shell's workspace area.
class UnavailableView extends StatelessWidget {
  const UnavailableView({super.key, required this.feature});

  final FeatureDefinition feature;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        const Row(
          children: [
            AppStatusBadge(
              label: 'Unavailable',
              background: Color(0x33F59E0B),
              foreground: AppColors.warn,
            ),
          ],
        ),
        const SizedBox(height: 14),
        Text(
          feature.title,
          style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 8),
        Text(
          feature.description,
          style: const TextStyle(color: AppColors.muted, fontSize: 14),
        ),
        const SizedBox(height: 20),
        const Text(
          'Expected once the backend exposes this endpoint',
          style: TextStyle(color: AppColors.muted, fontSize: 11, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 10),
        ...feature.expectedData.map(
          (item) => Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(
              children: [
                Container(
                  width: 5,
                  height: 5,
                  decoration: const BoxDecoration(color: AppColors.border, shape: BoxShape.circle),
                ),
                const SizedBox(width: 10),
                Text(item, style: const TextStyle(color: AppColors.muted, fontSize: 13)),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        const AppEmptyState(
          title: 'No data shown as zero',
          description:
              'This area is intentionally not wired: the backend does not yet '
              'serve this data over the authenticated API.',
        ),
      ],
    );
  }
}
