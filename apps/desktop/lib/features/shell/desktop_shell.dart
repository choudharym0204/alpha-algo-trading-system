import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../auth/auth_controller.dart';
import '../../repositories/system_controller.dart';
import '../../websocket/ws_controller.dart';
import '../../widgets/design/app_status.dart';
import '../../widgets/unavailable_view.dart';
import '../home/dashboard_screen.dart';
import 'navigation.dart';

/// Desktop trading-terminal shell: persistent left sidebar + top status bar +
/// main workspace. Desktop-native interaction model (density, keyboard
/// shortcuts, multi-column workspace) — not a scaled mobile layout.
class DesktopShell extends StatefulWidget {
  const DesktopShell({super.key});

  @override
  State<DesktopShell> createState() => _DesktopShellState();
}

class _DesktopShellState extends State<DesktopShell> {
  int _index = 0;
  final FocusNode _searchFocus = FocusNode();
  final TextEditingController _searchController = TextEditingController();

  @override
  void dispose() {
    _searchFocus.dispose();
    _searchController.dispose();
    super.dispose();
  }

  List<NavDestination> _visible() {
    final auth = context.read<AuthController>();
    return navDestinations.where((d) => auth.hasPermission(d.permission)).toList();
  }

  void _select(int index) => setState(() => _index = index);

  void _selectById(String id) {
    final i = _visible().indexWhere((d) => d.id == id);
    if (i >= 0) setState(() => _index = i);
  }

  void _focusSearch() => _searchFocus.requestFocus();

  Widget _workspace(NavDestination dest) {
    if (dest.id == 'dashboard') return const DashboardScreen();
    final feature = featureFor(dest.id);
    if (feature != null) return UnavailableView(feature: feature);
    return const Center(
      child: Text('Unavailable', style: TextStyle(color: AppColors.muted)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();
    final destinations = _visible();
    if (destinations.isEmpty) return const SizedBox.shrink();
    if (_index >= destinations.length) _index = 0;
    final current = destinations[_index];

    return CallbackShortcuts(
      bindings: <ShortcutActivator, VoidCallback>{
        const SingleActivator(LogicalKeyboardKey.digit1, control: true): () => _selectById('dashboard'),
        const SingleActivator(LogicalKeyboardKey.digit2, control: true): () => _selectById('markets'),
        const SingleActivator(LogicalKeyboardKey.digit3, control: true): () => _selectById('orders'),
        const SingleActivator(LogicalKeyboardKey.digit4, control: true): () => _selectById('positions'),
        const SingleActivator(LogicalKeyboardKey.keyK, control: true): _focusSearch,
      },
      child: Focus(
        autofocus: true,
        child: Scaffold(
          backgroundColor: AppColors.surface,
          body: Row(
            children: [
              _Sidebar(
                destinations: destinations,
                selectedIndex: _index,
                onSelect: _select,
                searchController: _searchController,
                searchFocus: _searchFocus,
              ),
              const VerticalDivider(width: 1, color: AppColors.border),
              Expanded(
                child: Column(
                  children: [
                    _TopBar(
                      title: current.label,
                      subject: auth.user?.subject,
                      onSignOut: auth.logout,
                    ),
                    const Divider(height: 1, color: AppColors.border),
                    Expanded(child: _workspace(current)),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Sidebar extends StatefulWidget {
  const _Sidebar({
    required this.destinations,
    required this.selectedIndex,
    required this.onSelect,
    required this.searchController,
    required this.searchFocus,
  });

  final List<NavDestination> destinations;
  final int selectedIndex;
  final ValueChanged<int> onSelect;
  final TextEditingController searchController;
  final FocusNode searchFocus;

  @override
  State<_Sidebar> createState() => _SidebarState();
}

class _SidebarState extends State<_Sidebar> {
  @override
  void initState() {
    super.initState();
    widget.searchController.addListener(_onSearch);
  }

  @override
  void didUpdateWidget(covariant _Sidebar oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.searchController != widget.searchController) {
      oldWidget.searchController.removeListener(_onSearch);
      widget.searchController.addListener(_onSearch);
    }
  }

  @override
  void dispose() {
    widget.searchController.removeListener(_onSearch);
    super.dispose();
  }

  void _onSearch() => setState(() {});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 224,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: TextField(
              controller: widget.searchController,
              focusNode: widget.searchFocus,
              style: const TextStyle(color: Colors.white, fontSize: 13),
              decoration: InputDecoration(
                hintText: 'Search (Ctrl+K)',
                hintStyle: const TextStyle(color: AppColors.muted, fontSize: 12),
                prefixIcon: const Icon(Icons.search, size: 16, color: AppColors.muted),
                isDense: true,
                filled: true,
                fillColor: AppColors.surfaceRaised,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(6),
                  borderSide: const BorderSide(color: AppColors.border),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(6),
                  borderSide: const BorderSide(color: AppColors.border),
                ),
              ),
            ),
          ),
          const Divider(height: 1, color: AppColors.border),
          Expanded(child: _filteredList()),
        ],
      ),
    );
  }

  Widget _filteredList() {
    final q = widget.searchController.text.trim().toLowerCase();
    final filtered = q.isEmpty
        ? widget.destinations
        : widget.destinations.where((d) => d.label.toLowerCase().contains(q)).toList();

    if (filtered.isEmpty) {
      return const Center(
        child: Text('No matching section', style: TextStyle(color: AppColors.muted, fontSize: 12)),
      );
    }
    return ListView.builder(
      itemCount: filtered.length,
      itemBuilder: (context, i) {
        final dest = filtered[i];
        final originalIndex = widget.destinations.indexOf(dest);
        final selected = originalIndex == widget.selectedIndex;
        return _SidebarItem(
          destination: dest,
          selected: selected,
          onTap: () => widget.onSelect(originalIndex),
        );
      },
    );
  }
}

class _SidebarItem extends StatelessWidget {
  const _SidebarItem({
    required this.destination,
    required this.selected,
    required this.onTap,
  });

  final NavDestination destination;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
        color: selected ? const Color(0x1A22C55E) : Colors.transparent,
        child: Row(
          children: [
            Icon(destination.icon, size: 17, color: selected ? AppColors.accent : AppColors.muted),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                destination.label,
                style: TextStyle(
                  color: selected ? Colors.white : AppColors.muted,
                  fontSize: 13,
                  fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                ),
              ),
            ),
            if (destination.shortcutDigit != null)
              Text(
                'Ctrl+${destination.shortcutDigit}',
                style: const TextStyle(color: AppColors.border, fontSize: 10),
              ),
          ],
        ),
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({
    required this.title,
    required this.subject,
    required this.onSignOut,
  });

  final String title;
  final String? subject;
  final VoidCallback onSignOut;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 48,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      color: AppColors.surfaceRaised,
      child: Row(
        children: [
          const Text('Alpha Algo', style: TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w700)),
          const SizedBox(width: 8),
          const Text('·', style: TextStyle(color: AppColors.muted)),
          const SizedBox(width: 8),
          Text(title, style: const TextStyle(color: AppColors.muted, fontSize: 13)),
          const Spacer(),
          Consumer<SystemController>(
            builder: (context, system, _) => TradingModeBadge(liveTrading: system.health?.liveTrading),
          ),
          const SizedBox(width: 14),
          Consumer<WsController>(
            builder: (context, ws, _) => ConnectionIndicator(status: ws.status),
          ),
          if (subject != null) ...[
            const SizedBox(width: 14),
            Tooltip(
              message: subject!,
              child: Text(
                subject!.length > 12 ? '${subject!.substring(0, 12)}…' : subject!,
                style: const TextStyle(color: AppColors.muted, fontSize: 11),
              ),
            ),
          ],
          const SizedBox(width: 4),
          IconButton(
            tooltip: 'Sign out',
            icon: const Icon(Icons.logout, size: 18, color: AppColors.muted),
            onPressed: onSignOut,
          ),
        ],
      ),
    );
  }
}
