"""Single-threaded benchmark implementation."""

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Generator, Optional

import psycopg2

from ..core.base import BaseBenchmark, BenchmarkConfig
from ..core.connection import ConnectionManager
from ..core.exceptions import QueryError, TimeoutError
from ..core.metrics import BenchmarkResult, QueryExecution
from ..formatters.sql import SQLFormatter

logger = logging.getLogger(__name__)


class SingleThreadBenchmark(BaseBenchmark):
    """Single-threaded benchmark implementation."""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        config: Optional[BenchmarkConfig] = None,
    ):
        super().__init__(connection_manager, config)
        self.sql_formatter = SQLFormatter()
        self._current_run = 0

    def run(self) -> BenchmarkResult:
        """Execute the benchmark synchronously."""
        if not self._sql_query:
            raise ValueError("SQL query not set")

        self._is_running = True
        self.metrics_collector.start()

        try:
            # Execute warmup runs
            logger.info(f"Executing {self.config.warmup_runs} warmup runs")
            for i in range(self.config.warmup_runs):
                self._execute_single_query(warmup=True, warmup_id=i)

            # Execute actual benchmark runs
            logger.info(f"Executing {self.config.number_of_runs} benchmark runs")
            for run_id in range(self.config.number_of_runs):
                self._current_run = run_id
                execution = self._execute_single_query(run_id=run_id)
                if execution:
                    self.metrics_collector.add_execution(execution)

                # Log progress periodically
                if (run_id + 1) % 100 == 0:
                    logger.info(
                        f"Completed {run_id + 1}/{self.config.number_of_runs} runs"
                    )
        finally:
            self._is_running = False
            self.metrics_collector.end()

        return self.metrics_collector.get_result()

    def iter_results(self) -> Generator[QueryExecution, None, BenchmarkResult]:
        """Iterate over benchmark results as they complete."""
        if not self._sql_query:
            raise ValueError("SQL query not set")

        self._is_running = True
        self.metrics_collector.start()

        try:
            # Execute warmup runs
            logger.info(f"Executing {self.config.warmup_runs} warmup runs")
            for i in range(self.config.warmup_runs):
                self._execute_single_query(warmup=True, warmup_id=i)

            # Execute and yield results
            logger.info(f"Executing {self.config.number_of_runs} benchmark runs")
            for run_id in range(self.config.number_of_runs):
                self._current_run = run_id
                execution = self._execute_single_query(run_id=run_id)
                if execution:
                    self.metrics_collector.add_execution(execution)
                    yield execution
        finally:
            self._is_running = False
            self.metrics_collector.end()

        return self.metrics_collector.get_result()

    def _execute_single_query(
        self, run_id: int = 0, warmup: bool = False, warmup_id: int = 0
    ) -> Optional[QueryExecution]:
        """Execute a single query and measure performance."""

        # Format SQL with parameters
        formatted_sql = self.sql_formatter.format(self._sql_query, self._sql_params)

        # Pre-execution hooks
        context = {
            "run_id": run_id if not warmup else f"warmup_{warmup_id}",
            "warmup": warmup,
            "sql": formatted_sql,
        }
        self._execute_hooks(self._pre_hooks, context)

        start_time = datetime.now()
        success = False
        error = None
        explain_plan = None
        buffer_stats = None
        io_stats = None
        retry_count = 0

        while retry_count <= self.config.retry_on_error:
            try:
                with self.connection_manager.get_connection() as conn:
                    with conn.cursor() as cursor:
                        # Set timeout if configured
                        if self.config.timeout:
                            cursor.execute(
                                "SET LOCAL statement_timeout = %s",
                                (int(self.config.timeout * 1000),),
                            )
                        # Collect EXPLAIN if configured and not warmup
                        if self.config.collect_explain and not warmup:
                            try:
                                cursor.execute(
                                    f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {formatted_sql}"
                                )
                                explain_plan = cursor.fetchone()[0]
                            except psycopg2.Error as e:
                                logger.warning(f"Failed to collect EXPLAIN: {e}")

                        # Collect initial buffer stats if configured
                        if self.config.collect_buffers and not warmup:
                            cursor.execute(
                                "SELECT * FROM pg_stat_database WHERE datname = current_database()"
                            )
                            initial_buffer_stats = (
                                dict(
                                    zip(
                                        [desc[0] for desc in cursor.description],
                                        cursor.fetchone(),
                                    )
                                )
                                if cursor.rowcount > 0
                                else None
                            )

                        query_start = time.perf_counter()
                        cursor.execute(formatted_sql)
                        query_end = time.perf_counter()

                        # Fetch results to ensure query completion
                        if cursor.description:
                            results = cursor.fetchall()
                            row_count = len(results)
                        else:
                            row_count = cursor.rowcount

                        success = True

                        # Collect final buffer stats if configured
                        if (
                            self.config.collect_buffers
                            and not warmup
                            and initial_buffer_stats
                        ):
                            cursor.execute(
                                "SELECT * FROM pg_stat_database WHERE datname = current_database()"
                            )
                            final_buffer_stats = (
                                dict(
                                    zip(
                                        [desc[0] for desc in cursor.description],
                                        cursor.fetchone(),
                                    )
                                )
                                if cursor.rowcount > 0
                                else None
                            )

                            # Calculate buffer stat differences
                            if final_buffer_stats:
                                buffer_stats = {
                                    key: final_buffer_stats.get(key, 0)
                                    - initial_buffer_stats.get(key, 0)
                                    for key in [
                                        "blks_read",
                                        "blks_hit",
                                        "tup_returned",
                                        "tup_fetched",
                                    ]
                                    if key in final_buffer_stats
                                }

                        # Collect IO timing if configured
                        if self.config.collect_io_timing and not warmup:
                            cursor.execute(
                                "SELECT * FROM pg_stat_statements WHERE query = %s",
                                (formatted_sql,),
                            )
                            if cursor.rowcount > 0:
                                io_stats = dict(
                                    zip(
                                        [desc[0] for desc in cursor.description],
                                        cursor.fetchone(),
                                    )
                                )

                        break  # This is a very important break here ;d

            except psycopg2.extensions.QueryCanceledError as e:
                error = f"Query timeout: {e}"
                logger.warning(f"Query timeout on run {run_id}: {e}")
                query_end = time.perf_counter()

        if warmup:
            return None

        return QueryExecution(
            run_id=run_id,
            start_time=start_time,
            end_time=datetime.now(),
            duration=timedelta(seconds=query_end - query_start),
            success=success,
            error=error,
            explain_plan=explain_plan,
            buffer_stats=buffer_stats,
        )
