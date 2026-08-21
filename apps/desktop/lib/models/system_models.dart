/// Mirror of the backend system schemas (apps/api/.../schemas/health.py).
class HealthStatus {
  final String service;
  final String status;
  final String liveTrading;

  const HealthStatus({
    required this.service,
    required this.status,
    required this.liveTrading,
  });

  factory HealthStatus.fromJson(Map<String, dynamic> json) {
    return HealthStatus(
      service: json['service'] as String,
      status: json['status'] as String,
      liveTrading: json['live_trading'] as String,
    );
  }
}

class ReadinessStatus extends HealthStatus {
  final Map<String, String> checks;

  const ReadinessStatus({
    required super.service,
    required super.status,
    required super.liveTrading,
    required this.checks,
  });

  factory ReadinessStatus.fromJson(Map<String, dynamic> json) {
    final checks = json['checks'];
    return ReadinessStatus(
      service: json['service'] as String,
      status: json['status'] as String,
      liveTrading: json['live_trading'] as String,
      checks: checks is Map<String, dynamic>
          ? checks.map((k, v) => MapEntry(k, v.toString()))
          : const <String, String>{},
    );
  }
}
