import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../core/api_error.dart';

/// Thin authenticated REST client over the backend API.
///
/// - Always JSON; always parses the backend structured error envelope.
/// - Throws [ApiError] (status/code/requestId) on any non-2xx response.
/// - Never logs tokens; never exposes raw response bodies on error.
class ApiClient {
  ApiClient({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        _baseUrl = baseUrl ?? AppConfig.apiBaseUrl;

  final http.Client _client;
  final String _baseUrl;

  static const Duration _timeout = Duration(seconds: 15);

  Future<dynamic> get(
    String path, {
    String? token,
    Map<String, String>? query,
  }) {
    return _request('GET', path, token: token, query: query);
  }

  Future<dynamic> post(
    String path, {
    String? token,
    Object? body,
  }) {
    return _request('POST', path, token: token, body: body);
  }

  Future<dynamic> _request(
    String method,
    String path, {
    String? token,
    Object? body,
    Map<String, String>? query,
  }) async {
    final uri = Uri.parse('$_baseUrl$path').replace(
      queryParameters: (query != null && query.isNotEmpty) ? query : null,
    );
    final headers = <String, String>{
      'Content-Type': 'application/json',
      if (token != null) 'Authorization': 'Bearer $token',
    };

    http.Response response;
    try {
      final request = http.Request(method, uri)..headers.addAll(headers);
      if (body != null) {
        request.body = jsonEncode(body);
      }
      final streamed = await _client.send(request).timeout(_timeout);
      response = await http.Response.fromStream(streamed);
    } on TimeoutException {
      throw const ApiError(
        status: 0,
        code: 'NETWORK_TIMEOUT',
        message: 'The request timed out.',
        requestId: 'unknown',
      );
    } on SocketException {
      throw const ApiError(
        status: 0,
        code: 'NETWORK_ERROR',
        message: 'Unable to reach the trading API.',
        requestId: 'unknown',
      );
    } on http.ClientException {
      throw const ApiError(
        status: 0,
        code: 'NETWORK_ERROR',
        message: 'Unable to reach the trading API.',
        requestId: 'unknown',
      );
    }

    final String text = response.body;
    dynamic decoded;
    if (text.isNotEmpty) {
      try {
        decoded = jsonDecode(text);
      } catch (_) {
        decoded = null;
      }
    }

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return decoded;
    }
    throw parseApiError(response.statusCode, decoded);
  }

  void dispose() => _client.close();
}
