"""Parallel benchmark implementation using multiprocessing."""

import logging
import multiprocessing as mp
import queue
import time
from functools import partial
from typing import Any, Dict, Generator, List, Optional, Tuple

from ..core.base import BenchmarkConfig
from ..core.connection import ConnectionManager
from ..core.exceptions import BenchmarkError
from ..core.metrics import BenchmarkResult, MetricsCollector, QueryExecution
from .single import SingleThreadBenchmark

logger = logging.getLogger(__name__)


class ParallelBenchmark:
    """Parallel benchmark using multiple processes."""

    def __init__(
        self,
        connection_params: dict,
        num_processes: int = 4,
        config: Optional[BenchmarkConfig] = None,
    ):
        self.connection_params = connection_params
        self.num_processes = min(num_processes, mp.cpu_count())
        self.config = config or BenchmarkConfig()
        self.config.validate()

        self._sql_query: Optional[str] = None
        self._sql_params: Optional[dict] = None
        self._is_running = False

    def set_sql(self, sql: str, params: Optional[dict] = None):
        """Set the SQL query to benchmark."""
        if self._is_running:
            raise BenchmarkError("Cannot set SQL while benchmark is running")
        self._sql_query = sql
        self._sql_params = params or {}

    def run(self) -> BenchmarkResult:
        """Execute parallel benchmark."""
        if not self._sql_query:
            raise ValueError("SQL query not set")

        self._is_running = True

        try:
            # Divide work among processes
            work_distribution = self._calculate_work_distribution()

            logger.info(
                f"Starting parallel benchmark with {self.num_processes} processes"
            )

            # Execute in parallel
            with mp.Pool(processes=self.num_processes) as pool:
                worker_func = partial(
                    self._worker_function,
                    connection_params=self.connection_params,
                    sql_query=self._sql_query,
                    sql_params=self._sql_params,
                    config=self.config,
                )

                results = pool.map(worker_func, work_distribution)

            # Combine results
            return self._combine_results(results)

        finally:
            self._is_running = False

    def iter_results(self) -> Generator[QueryExecution, None, BenchmarkResult]:
        """Iterate over results as they complete across all processes."""
        if not self._sql_query:
            raise ValueError("SQL query not set")

        self._is_running = True

        try:
            # Create a queue for results
            result_queue = mp.Queue()

            # Divide work among processes
            work_distribution = self._calculate_work_distribution()

            # Start worker processes
            processes = []
            for work_item in work_distribution:
                p = mp.Process(
                    target=self._worker_with_queue,
                    args=(
                        work_item,
                        self.connection_params,
                        self._sql_query,
                        self._sql_params,
                        self.config,
                        result_queue,
                    ),
                )
                p.start()
                processes.append(p)

            # Collect results as they come in
            all_executions = []
            total_expected = self.config.number_of_runs

            while len(all_executions) < total_expected:
                try:
                    execution = result_queue.get(timeout=1)
                    if execution is not None:
                        all_executions.append(execution)
                        yield execution
                except queue.Empty:
                    # Check if all processes are still alive
                    if not any(p.is_alive() for p in processes):
                        break

            # Wait for all processes to complete
            for p in processes:
                p.join()

            # Create final result
            return self._create_result_from_executions(all_executions)

        finally:
            self._is_running = False

    def _calculate_work_distribution(self) -> List[Tuple[int, int, int]]:
        """Calculate how to distribute work among processes."""
        runs_per_process = self.config.number_of_runs // self.num_processes
        remainder = self.config.number_of_runs % self.num_processes

        # Calculate warmup distribution
        warmup_per_process = self.config.warmup_runs // self.num_processes
        warmup_remainder = self.config.warmup_runs % self.num_processes

        work_distribution = []
        run_offset = 0

        for i in range(self.num_processes):
            process_runs = runs_per_process + (1 if i < remainder else 0)
            process_warmup = warmup_per_process + (1 if i < warmup_remainder else 0)

            work_distribution.append((i, process_runs, process_warmup, run_offset))
            run_offset += process_runs

        return work_distribution

    @staticmethod
    def _worker_function(
        work_item: Tuple[int, int, int, int],
        connection_params: dict,
        sql_query: str,
        sql_params: dict,
        config: BenchmarkConfig,
    ) -> List[QueryExecution]:
        """Worker function for parallel execution."""
        process_id, num_runs, num_warmup, run_offset = work_item

        logger.info(
            f"Process {process_id}: Starting with {num_runs} runs and {num_warmup} warmup runs"
        )

        # Create connection manager for this process
        conn_manager = ConnectionManager(connection_params)

        # Create single-threaded benchmark
        local_config = BenchmarkConfig(
            number_of_runs=num_runs,
            warmup_runs=num_warmup,
            timeout=config.timeout,
            collect_explain=config.collect_explain,
            collect_buffers=config.collect_buffers,
            collect_io_timing=config.collect_io_timing,
            retry_on_error=config.retry_on_error,
        )

        benchmark = SingleThreadBenchmark(conn_manager, local_config)
        benchmark.set_sql(sql_query, sql_params)

        # Collect results
        executions = []
        for execution in benchmark.iter_results():
            # Adjust run_id to be globally unique
            execution.run_id = run_offset + execution.run_id
            executions.append(execution)

        conn_manager.close()

        logger.info(f"Process {process_id}: Completed {len(executions)} runs")

        return executions

    @staticmethod
    def _worker_with_queue(
        work_item: Tuple[int, int, int, int],
        connection_params: dict,
        sql_query: str,
        sql_params: dict,
        config: BenchmarkConfig,
        result_queue: mp.Queue,
    ):
        """Worker function that sends results through a queue."""
        process_id, num_runs, num_warmup, run_offset = work_item

        try:
            # Create connection manager for this process
            conn_manager = ConnectionManager(connection_params)

            # Create single-threaded benchmark
            local_config = BenchmarkConfig(
                number_of_runs=num_runs,
                warmup_runs=num_warmup,
                timeout=config.timeout,
                collect_explain=config.collect_explain,
                collect_buffers=config.collect_buffers,
                collect_io_timing=config.collect_io_timing,
                retry_on_error=config.retry_on_error,
            )

            benchmark = SingleThreadBenchmark(conn_manager, local_config)
            benchmark.set_sql(sql_query, sql_params)

            # Send results through queue as they complete
            for execution in benchmark.iter_results():
                # Adjust run_id to be globally unique
                execution.run_id = run_offset + execution.run_id
                result_queue.put(execution)

            conn_manager.close()

        except Exception as e:
            logger.error(f"Process {process_id} failed: {e}")

    def _combine_results(self, results: List[List[QueryExecution]]) -> BenchmarkResult:
        """Combine results from all workers."""
        collector = MetricsCollector()
        collector.start()

        # Flatten and add all executions
        for worker_results in results:
            for execution in worker_results:
                collector.add_execution(execution)

        collector.end()
        return collector.get_result()

    def _create_result_from_executions(
        self, executions: List[QueryExecution]
    ) -> BenchmarkResult:
        """Create a benchmark result from a list of executions."""
        collector = MetricsCollector()
        collector.start()

        for execution in executions:
            collector.add_execution(execution)

        collector.end()
        return collector.get_result()

    def get_status(self) -> Dict[str, Any]:
        """Get current benchmark status."""
        return {
            "is_running": self._is_running,
            "num_processes": self.num_processes,
            "total_runs": self.config.number_of_runs,
            "sql_query": self._sql_query,
        }
