"""Database connection management."""

import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional, Union

import psycopg2
from psycopg2 import pool

from .exceptions import ConnectionError as BenchmarkConnectionError

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages database connections with pooling support."""

    def __init__(
        self,
        connection_params: Union[
            Dict[str, Any], psycopg2.extensions.connection, None
        ] = None,
        pool_size: int = 5,
        max_overflow: int = 10,
    ):
        self._connection_params = self._normalize_params(connection_params)
        self._pool = None
        self._single_conn = None
        self._pool_size = pool_size
        self._max_overflow = max_overflow

        if isinstance(connection_params, psycopg2.extensions.connection):
            self._single_conn = connection_params
        else:
            self._initialize_pool(pool_size, pool_size + max_overflow)

    def _normalize_params(self, params):
        """Normalize connection parameters."""
        if params is None:
            return {
                "dbname": "postgres",
                "user": "postgres",
                "password": "",
                "host": "localhost",
                "port": "5432",
            }
        elif isinstance(params, dict):
            # Ensure all required parameters are present
            defaults = {
                "dbname": "postgres",
                "user": "postgres",
                "password": "",
                "host": "localhost",
                "port": "5432",
            }
            return {**defaults, **params}
        elif isinstance(params, psycopg2.extensions.connection):
            return None  # Using existing connection
        else:
            raise ValueError("Invalid connection parameters")

    def _initialize_pool(self, min_size: int, max_size: int):
        """Initialize connection pool."""
        if self._connection_params:
            try:
                self._pool = psycopg2.pool.ThreadedConnectionPool(
                    min_size, max_size, **self._connection_params
                )
                logger.info(
                    f"Connection pool initialized with {min_size}-{max_size} connections"
                )
            except psycopg2.Error as e:
                raise BenchmarkConnectionError(f"Failed to create connection pool: {e}")

    @contextmanager
    def get_connection(self, retry_attempts: int = 3, retry_delay: float = 1.0):
        """Get a connection from the pool or return single connection."""
        last_error = None

        for attempt in range(retry_attempts):
            try:
                if self._single_conn:
                    # Check if connection is still valid
                    if self._single_conn.closed:
                        raise BenchmarkConnectionError("Connection is closed")
                    yield self._single_conn
                    return
                elif self._pool:
                    conn = self._pool.getconn()
                    try:
                        # Test connection
                        with conn.cursor() as cursor:
                            cursor.execute("SELECT 1")
                        yield conn
                        return
                    finally:
                        self._pool.putconn(conn)
                else:
                    raise BenchmarkConnectionError("No connection available")
            except Exception as e:
                last_error = e
                if attempt < retry_attempts - 1:
                    logger.warning(
                        f"Connection attempt {attempt + 1} failed: {e}. Retrying..."
                    )
                    time.sleep(retry_delay)

        raise BenchmarkConnectionError(f"All connection attempts failed: {last_error}")

    def execute_query(
        self, query: str, params: Optional[tuple] = None, fetch: bool = True
    ):
        """Execute a query and optionally fetch results."""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                if fetch and cursor.description:
                    return cursor.fetchall()
                return None

    def test_connection(self) -> bool:
        """Test if connection is working."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    return cursor.fetchone()[0] == 1
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def get_connection_info(self) -> Dict[str, Any]:
        """Get information about the current connection."""
        info = {}
        try:
            with self.get_connection() as conn:
                info["status"] = "connected" if not conn.closed else "closed"
                info["encoding"] = conn.encoding
                info["isolation_level"] = conn.isolation_level

                with conn.cursor() as cursor:
                    cursor.execute("SELECT version()")
                    info["server_version"] = cursor.fetchone()[0]

                    cursor.execute("SELECT current_database()")
                    info["database"] = cursor.fetchone()[0]

                    cursor.execute("SELECT current_user")
                    info["user"] = cursor.fetchone()[0]

        except Exception as e:
            info["error"] = str(e)

        return info

    def close(self):
        """Close all connections."""
        if self._pool:
            self._pool.closeall()
            logger.info("Connection pool closed")
        if self._single_conn and not self._single_conn.closed:
            self._single_conn.close()
            logger.info("Single connection closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
