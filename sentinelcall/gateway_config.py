"""API Gateway timeout and circuit breaker settings."""

GATEWAY_TIMEOUTS = {
    "payment-service": {"timeout_ms": 5000, "circuit_breaker_threshold": 5},
    "user-service": {"timeout_ms": 3000, "circuit_breaker_threshold": 10},
    "notification-service": {"timeout_ms": 2000, "circuit_breaker_threshold": 15},
    "database-primary": {"timeout_ms": 10000, "circuit_breaker_threshold": 3},
}
