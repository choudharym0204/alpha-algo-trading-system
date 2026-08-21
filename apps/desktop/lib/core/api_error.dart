/// Normalized backend error, safe to render (no raw stack traces).
///
/// Mirrors the backend structured error envelope:
/// `{ error: { code, message, request_id, details } }` (see apps/api errors.py).
class ApiError implements Exception {
  final int status;
  final String code;
  final String message;
  final String requestId;
  final Map<String, dynamic> details;

  const ApiError({
    required this.status,
    required this.code,
    required this.message,
    required this.requestId,
    this.details = const {},
  });

  bool get isUnauthorized => status == 401;
  bool get isForbidden => status == 403;
  bool get isRateLimited => status == 429;
  bool get isNetworkError => status == 0;

  @override
  String toString() => 'ApiError($status $code: $message)';
}

/// Parse the backend structured error envelope into an [ApiError].
///
/// On a body that does not match the envelope shape (proxy/gateway error),
/// falls back to a generic error and never trusts/echoes an arbitrary body.
ApiError parseApiError(int status, dynamic body) {
  if (body is Map<String, dynamic>) {
    final error = body['error'];
    if (error is Map<String, dynamic>) {
      final code = error['code'];
      final message = error['message'];
      final requestId = error['request_id'];
      if (code is String && message is String && requestId is String) {
        final details = error['details'];
        return ApiError(
          status: status,
          code: code,
          message: message,
          requestId: requestId,
          details: details is Map<String, dynamic> ? details : const {},
        );
      }
    }
  }
  return ApiError(
    status: status,
    code: 'UNEXPECTED_RESPONSE',
    message: 'The server returned an unexpected response.',
    requestId: 'unknown',
  );
}
