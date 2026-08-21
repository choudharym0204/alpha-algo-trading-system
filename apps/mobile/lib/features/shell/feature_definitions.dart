import '../../core/permissions.dart';

/// A trading-domain screen definition. Each screen is gated on a backend
/// permission and — until the backend exposes its data endpoint — renders an
/// honest "Unavailable" state rather than fabricated data.
class FeatureDefinition {
  final String id;
  final String title;
  final String description;
  final List<String> expectedData;
  final String permission;

  const FeatureDefinition({
    required this.id,
    required this.title,
    required this.description,
    required this.expectedData,
    required this.permission,
  });
}

/// Trading-domain screens whose backend endpoints are not yet exposed.
const List<FeatureDefinition> tradingFeatures = [
  FeatureDefinition(
    id: 'markets',
    title: 'Markets',
    description:
        'Market data (LTP, change, volume, freshness) is served by the backend '
        'market-data provider, which has no authenticated REST/WS endpoint yet.',
    expectedData: ['LTP / quote', 'Change / change %', 'Volume', 'Timestamp', 'Freshness'],
    permission: Permissions.tradingView,
  ),
  FeatureDefinition(
    id: 'orders',
    title: 'Orders',
    description:
        'Order listing and entry require OMS/Execution REST endpoints, which '
        'are not exposed yet. No order can be submitted until the backend routes exist.',
    expectedData: ['Open orders', 'History', 'Status / filled / remaining', 'Avg fill price'],
    permission: Permissions.tradingView,
  ),
  FeatureDefinition(
    id: 'positions',
    title: 'Positions',
    description:
        'Position data comes from the Phase 11 Position Engine; no position '
        'REST endpoint is exposed yet.',
    expectedData: ['Instrument', 'Quantity / side', 'Average entry', 'Reference price'],
    permission: Permissions.tradingView,
  ),
  FeatureDefinition(
    id: 'portfolio',
    title: 'Portfolio',
    description:
        'Portfolio aggregates come from the Phase 12 Portfolio Engine; no '
        'portfolio REST endpoint is exposed yet.',
    expectedData: ['Value', 'Cash / funds', 'Gross / net exposure', 'Status'],
    permission: Permissions.tradingView,
  ),
  FeatureDefinition(
    id: 'pnl',
    title: 'P&L',
    description:
        'P&L figures come from the Phase 13 P&L Engine; no P&L REST endpoint '
        'is exposed yet.',
    expectedData: ['Realized / unrealized', 'Gross / costs / net', 'Daily P&L'],
    permission: Permissions.tradingView,
  ),
  FeatureDefinition(
    id: 'strategies',
    title: 'Strategies',
    description:
        'Strategy status comes from the Phase 4/5 runtime; no strategy REST/WS '
        'endpoint is exposed yet.',
    expectedData: ['Name / version', 'Run status', 'Signals', 'Health'],
    permission: Permissions.tradingView,
  ),
  FeatureDefinition(
    id: 'risk',
    title: 'Risk',
    description:
        'Risk state comes from the Phase 6 Risk Engine; no risk REST endpoint '
        'is exposed yet. The global halt is reflected on the dashboard.',
    expectedData: ['Risk status', 'Rejections', 'Circuit breaker', 'Global halt'],
    permission: Permissions.tradingView,
  ),
  FeatureDefinition(
    id: 'brokers',
    title: 'Brokers',
    description:
        'Broker adapter status comes from the Phase 10 adapters; no broker REST '
        'endpoint is exposed yet. Credentials never reach the app.',
    expectedData: ['Broker name', 'Connection state', 'Health', 'Capabilities'],
    permission: Permissions.tradingView,
  ),
  FeatureDefinition(
    id: 'reconciliation',
    title: 'Reconciliation',
    description:
        'Reconciliation state comes from the Phase 14 engine; no reconciliation '
        'REST endpoint is exposed yet.',
    expectedData: ['Latest run', 'Matched / mismatched', 'Severity'],
    permission: Permissions.tradingView,
  ),
];
