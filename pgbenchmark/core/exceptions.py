"""Custom exceptions for pgbenchmark."""


class BenchmarkError(Exception):
    """Base exception for benchmark errors."""

    pass


class ConnectionError(BenchmarkError):
    """Database connection error."""

    pass


class ConfigurationError(BenchmarkError):
    """Configuration error."""

    pass


class QueryError(BenchmarkError):
    """Query execution error."""

    pass


class ValidationError(BenchmarkError):
    """Validation error."""

    pass


class TimeoutError(BenchmarkError):
    """Query timeout error."""

    pass


class PoolError(BenchmarkError):
    """Connection pool error."""

    pass
