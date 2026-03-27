"""Payment service retry configuration."""

RETRY_CONFIG = {
    "max_retries": 3,
    "backoff_factor": 0.5,
    "retry_on_status": [502, 503, 504],
    "timeout_per_request": 10,
}

async def with_retry(fn, config=None):
    """Execute function with exponential backoff retry."""
    cfg = config or RETRY_CONFIG
    for attempt in range(cfg["max_retries"]):
        try:
            return await fn()
        except Exception as e:
            if attempt == cfg["max_retries"] - 1:
                raise
            import asyncio
            await asyncio.sleep(cfg["backoff_factor"] * (2 ** attempt))
