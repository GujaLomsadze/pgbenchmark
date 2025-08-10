"""Asynchronous benchmark implementation using asyncpg."""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import asyncpg

from ..core.base import BenchmarkConfig
from ..core.exceptions import BenchmarkError, ConnectionError
from ..core.metrics import BenchmarkResult, MetricsCollector, QueryExecution

logger = logging.getLogger(__name__)


class AsyncBenchmark:
    """Asynchronous benchmark using asyncpg."""

    def __init__(
        self,
        connection_params: dict,
        config: Optional[BenchmarkConfig] = None,
        concurrency: int = 10,
    ):
        self.connection_params = self._convert_params(connection_params)
        self.config = config or BenchmarkConfig()
        self.config.validate()

        self.concurrency = concurrency
        self._sql_query: Optional[str] = None
        self._sql_params: Optional[dict] = None
        self._pool: Optional[asyncpg.Pool] = None
        self._is_running = False

    def _convert_params(self, params: dict) -> dict:
        """Convert psycopg2 params to asyncpg format."""
        return {
            "host": params.get("host", "localhost"),
            "port": int(params.get("port", 5432)),
            "user": params.get("user", "postgres"),
            "password": params.get("password", ""),
            "database": params.get("dbname", "postgres"),
        }

    def set_sql(self, sql: str, params: Optional[dict] = None):
        """Set the SQL query to benchmark."""
        if self._is_running:
            raise BenchmarkError("Cannot set SQL while benchmark is running")
        self._sql_query = sql
        self._sql_params = params or {}

    async def _create_pool(self):
        """Create connection pool."""
        try:
            self._pool = await asyncpg.create_pool(
                **self.connection_params,
                min_size=self.concurrency,
                max_size=self.concurrency * 2,
                command_timeout=self.config.timeout,
            )
            logger.info(f"Created async pool with {self.concurrency} connections")
        except Exception as e:
            raise ConnectionError(f"Failed to create connection pool: {e}")

    async def _close_pool(self):
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def _execute_query(self, run_id: int) -> QueryExecution:
        """Execute a single query asynchronously."""
        start_time = datetime.now()
        success = False
        error = None

        retry_count = 0
        while retry_count <= self.config.retry_on_error:
            try:
                async with self._pool.acquire() as conn:
                    # Set timeout if configured
                    if self.config.timeout:
                        await conn.execute(
                            f"SET statement_timeout = {int(self.config.timeout * 1000)}"
                        )

                    # Execute query
                    query_start = time.perf_counter()

                    # Format query with parameters if needed
                    formatted_query = self._format_query()

                    result = await conn.fetch(formatted_query)
                    query_end = time.perf_counter()

                    success = True
                    break

            except asyncio.TimeoutError as e:
                error = f"Query timeout: {e}"
                query_end = time.perf_counter()
                query_start = query_end
                break  # Don't retry on timeout

            except asyncpg.PostgresError as e:
                error = str(e)
                logger.error(f"Query execution failed (attempt {retry_count + 1}): {e}")
                query_end = time.perf_counter()
                query_start = query_end

                retry_count += 1
                if retry_count <= self.config.retry_on_error:
                    await asyncio.sleep(0.5 * retry_count)
                else:
                    break

            except Exception as e:
                error = str(e)
                logger.error(f"Unexpected error during query execution: {e}")
                query_end = time.perf_counter()
                query_start = query_end
                break

        end_time = datetime.now()

        return QueryExecution(
            run_id=run_id,
            start_time=start_time,
            end_time=end_time,
            duration=timedelta(seconds=query_end - query_start),
            success=success,
            error=error,
        )

    def _format_query(self) -> str:
        """Format query with parameters."""
        # Simple parameter substitution for now
        query = self._sql_query
        for key, value in self._sql_params.items():
            query = query.replace(f"{{{key}}}", str(value))
        return query

    async def _execute_warmup(self):
        """Execute warmup queries."""
        if self.config.warmup_runs > 0:
            logger.info(f"Executing {self.config.warmup_runs} warmup runs")

            warmup_tasks = []
            for i in range(self.config.warmup_runs):
                warmup_tasks.append(self._execute_query(run_id=-i - 1))

            # Execute warmup in batches
            for i in range(0, len(warmup_tasks), self.concurrency):
                batch = warmup_tasks[i : i + self.concurrency]
                await asyncio.gather(*batch)

    async def _run_async(self) -> BenchmarkResult:
        """Run benchmark asynchronously."""
        if not self._sql_query:
            raise ValueError("SQL query not set")

        self._is_running = True

        try:
            await self._create_pool()

            # Execute warmup
            await self._execute_warmup()

            collector = MetricsCollector()
            collector.start()

            logger.info(
                f"Executing {self.config.number_of_runs} benchmark runs with concurrency {self.concurrency}"
            )

            # Create all tasks
            all_executions = []

            # Execute in batches to control concurrency
            for batch_start in range(0, self.config.number_of_runs, self.concurrency):
                batch_end = min(
                    batch_start + self.concurrency, self.config.number_of_runs
                )
                batch_tasks = [
                    self._execute_query(run_id)
                    for run_id in range(batch_start, batch_end)
                ]

                # Execute batch
                batch_results = await asyncio.gather(*batch_tasks)

                # Add to collector
                for execution in batch_results:
                    collector.add_execution(execution)
                    all_executions.append(execution)

                # Log progress
                if (batch_end) % 100 == 0:
                    logger.info(
                        f"Completed {batch_end}/{self.config.number_of_runs} runs"
                    )

            collector.end()

            return collector.get_result()

        finally:
            await self._close_pool()
            self._is_running = False

    async def _iter_async(self):
        """Async generator for iterating results."""
        if not self._sql_query:
            raise ValueError("SQL query not set")

        self._is_running = True

        try:
            await self._create_pool()

            # Execute warmup
            await self._execute_warmup()

            logger.info(f"Executing {self.config.number_of_runs} benchmark runs")

            # Execute and yield results
            for batch_start in range(0, self.config.number_of_runs, self.concurrency):
                batch_end = min(
                    batch_start + self.concurrency, self.config.number_of_runs
                )
                batch_tasks = [
                    self._execute_query(run_id)
                    for run_id in range(batch_start, batch_end)
                ]

                # Execute batch
                batch_results = await asyncio.gather(*batch_tasks)

                # Yield results
                for execution in batch_results:
                    yield execution

        finally:
            await self._close_pool()
            self._is_running = False

    def run(self) -> BenchmarkResult:
        """Execute the async benchmark."""
        return asyncio.run(self._run_async())

    def iter_results(self):
        """Synchronous wrapper for async iteration."""

        async def _collect():
            async for execution in self._iter_async():
                results.append(execution)
                yield execution

        # This is a simplified version - in production you might want
        # to use async generators properly
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            gen = _collect()
            while True:
                try:
                    execution = loop.run_until_complete(gen.__anext__())
                    yield execution
                except StopAsyncIteration:
                    break
        finally:
            loop.close()

    def get_status(self) -> Dict[str, Any]:
        """Get current benchmark status."""
        return {
            "is_running": self._is_running,
            "concurrency": self.concurrency,
            "total_runs": self.config.number_of_runs,
            "sql_query": self._sql_query,
        }
