"""Base classes for benchmarking."""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .connection import ConnectionManager
from .exceptions import BenchmarkError
from .metrics import BenchmarkResult, MetricsCollector

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkConfig:
    """Configuration for benchmark execution."""

    number_of_runs: int = 100
    warmup_runs: int = 5
    timeout: Optional[float] = None
    collect_explain: bool = False
    collect_buffers: bool = False
    collect_io_timing: bool = False
    retry_on_error: int = 3
    batch_size: Optional[int] = None
    enable_profiling: bool = False

    def validate(self):
        """Validate configuration parameters."""
        if self.number_of_runs < 1:
            raise ValueError("number_of_runs must be at least 1")
        if self.warmup_runs < 0:
            raise ValueError("warmup_runs cannot be negative")
        if self.timeout is not None and self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.retry_on_error < 0:
            raise ValueError("retry_on_error cannot be negative")
        if self.batch_size is not None and self.batch_size <= 0:
            raise ValueError("batch_size must be positive")


class BaseBenchmark(ABC):
    """Abstract base class for all benchmark implementations."""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        config: Optional[BenchmarkConfig] = None,
    ):
        self.connection_manager = connection_manager
        self.config = config or BenchmarkConfig()
        self.config.validate()

        self.metrics_collector = MetricsCollector()
        self._sql_query: Optional[str] = None
        self._sql_params: Optional[Dict[str, Any]] = None
        self._pre_hooks: List[Callable] = []
        self._post_hooks: List[Callable] = []
        self._is_running = False

    def set_sql(self, sql: str, params: Optional[Dict[str, Any]] = None):
        """Set the SQL query to benchmark."""
        if self._is_running:
            raise BenchmarkError("Cannot set SQL while benchmark is running")
        self._sql_query = sql
        self._sql_params = params or {}

    def add_pre_hook(self, hook: Callable):
        """Add a pre-execution hook."""
        if not callable(hook):
            raise ValueError("Hook must be callable")
        self._pre_hooks.append(hook)

    def add_post_hook(self, hook: Callable):
        """Add a post-execution hook."""
        if not callable(hook):
            raise ValueError("Hook must be callable")
        self._post_hooks.append(hook)

    @abstractmethod
    def run(self) -> BenchmarkResult:
        """Execute the benchmark."""
        pass

    @abstractmethod
    def iter_results(self):
        """Iterate over benchmark results as they complete."""
        pass

    def _execute_hooks(self, hooks: List[Callable], context: Dict[str, Any]):
        """Execute a list of hooks with context."""
        for hook in hooks:
            try:
                hook(context)
            except Exception as e:
                logger.warning(f"Hook execution failed: {e}")

    def reset(self):
        """Reset the benchmark state."""
        self.metrics_collector = MetricsCollector()
        self._is_running = False

    def get_status(self) -> Dict[str, Any]:
        """Get current benchmark status."""
        return {
            "is_running": self._is_running,
            "runs_completed": len(self.metrics_collector.executions),
            "total_runs": self.config.number_of_runs,
            "sql_query": self._sql_query,
        }
