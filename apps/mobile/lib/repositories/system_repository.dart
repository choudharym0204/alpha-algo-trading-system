import '../models/system_models.dart';
import '../network/api_client.dart';

/// Data-access for the backend system endpoints (health / readiness).
class SystemRepository {
  SystemRepository(this._api);

  final ApiClient _api;

  Future<HealthStatus> health() async {
    final data = await _api.get('/api/v1/system/health');
    return HealthStatus.fromJson(data as Map<String, dynamic>);
  }

  Future<ReadinessStatus> readiness() async {
    final data = await _api.get('/api/v1/system/ready');
    return ReadinessStatus.fromJson(data as Map<String, dynamic>);
  }
}
