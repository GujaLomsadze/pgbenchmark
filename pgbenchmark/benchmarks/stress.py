"""Stress testing benchmark implementation."""

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import psutil

from ..core.base import BenchmarkConfig
from ..core.connection import ConnectionManager
from ..core.exceptions import BenchmarkError
from ..core.metrics import BenchmarkResult, MetricsCollector, QueryExecution
from .parallel import ParallelBenchmark
from .single import SingleThreadBenchmark

logger = logging.getLogger(__name__)


@dataclass
class StressTestConfig:
    """Configuration for stress testing."""

    test_type: str = "sustained"  # sustained, ramp_up, spike, soak
    duration_seconds: int = 60
    target_qps: Optional[int] = None
    ramp_up_time: int = 10
    ramp_down_time: int = 10
    spike_multiplier: float = 3.0
    concurrent_connections: int = 10
    monitor_resources: bool = True
    monitor_interval: float = 1.0


class StressBenchmark:
    """Stress testing benchmark with various load patterns."""

    def __init__(
        self,
        connection_params: dict,
        benchmark_config: Optional[BenchmarkConfig] = None,
        stress_config: Optional[StressTestConfig] = None,
    ):
        self.connection_params = connection_params
        self.benchmark_config = benchmark_config or BenchmarkConfig()
        self.stress_config = stress_config or StressTestConfig()

        self._sql_query: Optional[str] = None
        self._sql_params: Optional[dict] = None
        self._is_running = False
        self._stop_event = threading.Event()
        self._resource_data: List[Dict[str, Any]] = []
        self._monitor_thread: Optional[threading.Thread] = None

    def set_sql(self, sql: str, params: Optional[dict] = None):
        """Set the SQL query to stress test."""
        if self._is_running:
            raise BenchmarkError("Cannot set SQL while stress test is running")
        self._sql_query = sql
        self._sql_params = params or {}

    def run(self) -> Dict[str, Any]:
        """Execute the stress test."""
        if not self._sql_query:
            raise ValueError("SQL query not set")

        self._is_running = True
        self._stop_event.clear()
        self._resource_data = []

        try:
            # Start resource monitoring if enabled
            if self.stress_config.monitor_resources:
                self._start_resource_monitoring()

            # Execute the appropriate stress test
            if self.stress_config.test_type == "sustained":
                result = self._run_sustained_load()
            elif self.stress_config.test_type == "ramp_up":
                result = self._run_ramp_up()
            elif self.stress_config.test_type == "spike":
                result = self._run_spike_test()
            elif self.stress_config.test_type == "soak":
                result = self._run_soak_test()
            else:
                raise ValueError(
                    f"Unknown stress test type: {self.stress_config.test_type}"
                )

            # Stop resource monitoring
            self._stop_event.set()
            if self._monitor_thread:
                self._monitor_thread.join()

            # Add resource data to result
            result["resource_metrics"] = self._analyze_resource_data()

            return result

        finally:
            self._is_running = False
            self._stop_event.set()

    def _start_resource_monitoring(self):
        """Start monitoring system resources in a separate thread."""

        def monitor():
            while not self._stop_event.is_set():
                try:
                    cpu_percent = psutil.cpu_percent(interval=None)
                    memory = psutil.virtual_memory()
                    disk_io = psutil.disk_io_counters()
                    net_io = psutil.net_io_counters()

                    self._resource_data.append(
                        {
                            "timestamp": datetime.now(),
                            "cpu_percent": cpu_percent,
                            "memory_percent": memory.percent,
                            "memory_used_mb": memory.used / (1024 * 1024),
                            "disk_read_mb": disk_io.read_bytes / (1024 * 1024)
                            if disk_io
                            else 0,
                            "disk_write_mb": disk_io.write_bytes / (1024 * 1024)
                            if disk_io
                            else 0,
                            "network_sent_mb": net_io.bytes_sent / (1024 * 1024)
                            if net_io
                            else 0,
                            "network_recv_mb": net_io.bytes_recv / (1024 * 1024)
                            if net_io
                            else 0,
                        }
                    )

                    time.sleep(self.stress_config.monitor_interval)
                except Exception as e:
                    logger.error(f"Resource monitoring error: {e}")

        self._monitor_thread = threading.Thread(target=monitor, daemon=True)
        self._monitor_thread.start()
        logger.info("Started resource monitoring")

    def _run_sustained_load(self) -> Dict[str, Any]:
        """Run sustained load test at constant QPS."""
        logger.info(
            f"Running sustained load test for {self.stress_config.duration_seconds} seconds"
        )

        # Use parallel benchmark for sustained load
        parallel_bench = ParallelBenchmark(
            self.connection_params,
            num_processes=self.stress_config.concurrent_connections,
            config=self.benchmark_config,
        )
        parallel_bench.set_sql(self._sql_query, self._sql_params)

        start_time = datetime.now()
        executions = []

        # Run for specified duration
        while (
            datetime.now() - start_time
        ).total_seconds() < self.stress_config.duration_seconds:
            if self.stress_config.target_qps:
                # Rate limiting to achieve target QPS
                delay = 1.0 / self.stress_config.target_qps
                time.sleep(delay)

            # Execute a batch of queries
            conn_manager = ConnectionManager(self.connection_params)
            single_bench = SingleThreadBenchmark(conn_manager, self.benchmark_config)
            single_bench.set_sql(self._sql_query, self._sql_params)
            single_bench.config.number_of_runs = 1
            single_bench.config.warmup_runs = 0

            for execution in single_bench.iter_results():
                executions.append(execution)

            conn_manager.close()

        end_time = datetime.now()

        # Calculate metrics
        return self._create_stress_result(executions, start_time, end_time)

    def _run_ramp_up(self) -> Dict[str, Any]:
        """Run ramp-up test, gradually increasing load."""
        logger.info(
            f"Running ramp-up test over {self.stress_config.ramp_up_time} seconds"
        )

        start_time = datetime.now()
        executions = []

        # Calculate load steps
        steps = 10
        step_duration = self.stress_config.ramp_up_time / steps
        max_connections = self.stress_config.concurrent_connections

        for step in range(steps):
            current_connections = int((step + 1) / steps * max_connections)
            logger.info(
                f"Ramp-up step {step + 1}/{steps}: {current_connections} connections"
            )

            # Run with current number of connections
            parallel_bench = ParallelBenchmark(
                self.connection_params,
                num_processes=current_connections,
                config=self.benchmark_config,
            )
            parallel_bench.set_sql(self._sql_query, self._sql_params)
            parallel_bench.config.number_of_runs = current_connections * 10

            step_result = parallel_bench.run()
            executions.extend(step_result.executions)

            time.sleep(step_duration)

        # Sustained period at max load
        logger.info("Running at maximum load")
        sustained_duration = self.stress_config.duration_seconds
