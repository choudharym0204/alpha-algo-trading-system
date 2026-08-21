import 'dart:async';

import 'package:flutter/foundation.dart';

import '../core/api_error.dart';
import '../models/system_models.dart';
import 'system_repository.dart';

/// Polls backend health/readiness (public) and tracks staleness so the UI never
/// implies freshness after polling has gone quiet.
class SystemController extends ChangeNotifier {
  SystemController(this._repository);

  final SystemRepository _repository;

  static const Duration _pollInterval = Duration(seconds: 15);
  static const Duration _staleAfter = Duration(seconds: 45);

  HealthStatus? _health;
  ReadinessStatus? _readiness;
  bool _loading = true;
  bool _stale = false;
  ApiError? _error;
  DateTime _lastSuccess = DateTime.fromMillisecondsSinceEpoch(0);
  Timer? _timer;

  HealthStatus? get health => _health;
  ReadinessStatus? get readiness => _readiness;
  bool get loading => _loading;
  bool get stale => _stale;
  ApiError? get error => _error;

  void start() {
    _load();
    _timer = Timer.periodic(_pollInterval, (_) => _load());
  }

  Future<void> refresh() => _load();

  Future<void> _load() async {
    try {
      final results = await Future.wait<dynamic>([
        _repository.health(),
        _repository.readiness(),
      ]);
      _health = results[0] as HealthStatus;
      _readiness = results[1] as ReadinessStatus;
      _error = null;
      _lastSuccess = DateTime.now();
      _stale = false;
    } on ApiError catch (e) {
      _error = e;
      _stale = DateTime.now().difference(_lastSuccess) > _staleAfter;
    } catch (_) {
      _error = const ApiError(
        status: 0,
        code: 'SYSTEM_ERROR',
        message: 'Failed to load system status.',
        requestId: 'unknown',
      );
      _stale = DateTime.now().difference(_lastSuccess) > _staleAfter;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}
