"""Infrastructure configuration for connection pools and service limits."""

# Database connection pool settings
DB_POOL_CONFIG = {
    "max_pool_size": 20,        # CHANGED from 100 to 20 — potential bottleneck
    "min_pool_size": 2,
    "max_idle_time": 300,
    "connection_timeout": 5,
    "retry_attempts": 3,
}

# API Gateway rate limits
API_GATEWAY_CONFIG = {
    "rate_limit_per_second": 500,
    "burst_limit": 1000,
    "timeout_ms": 30000,
}

# Cache configuration
CACHE_CONFIG = {
    "ttl_seconds": 60,
    "max_entries": 10000,
    "eviction_policy": "lru",
}
