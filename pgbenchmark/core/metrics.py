"""Metrics collection and calculation."""

import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


@dataclass
class QueryExecution:
    """Single query execution metrics."""

    run_id: int
    start_time: datetime
    end_time: datetime
    duration: timedelta
    success: bool
    error: Optional[str] = None
    explain_plan: Optional[Dict[str, Any]] = None
    buffer_stats: Optional[Dict[str, Any]] = None
    io_stats: Optional[Dict[str, Any]] = None

    @property
    def duration_ms(self) -> float:
        """Duration in milliseconds."""
        return self.duration.total_seconds() * 1000

    @property
    def duration_us(self) -> float:
        """Duration in microseconds."""
        return self.duration.total_seconds() * 1000000

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "run_id": self.run_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error,
            "explain_plan": self.explain_plan,
            "buffer_stats": self.buffer_stats,
            "io_stats": self.io_stats,
        }


@dataclass
class BenchmarkResult:
    """Complete benchmark results with statistics."""

    executions: List[QueryExecution]
    total_runs: int
    successful_runs: int
    failed_runs: int
    start_time: datetime
    end_time: datetime

    # Statistics
    min_time_ms: float = field(init=False)
    max_time_ms: float = field(init=False)
    avg_time_ms: float = field(init=False)
    median_time_ms: float = field(init=False)
    stddev_time_ms: float = field(init=False)
    percentiles: Dict[str, float] = field(init=False)

    # Advanced metrics
    throughput_qps: float = field(init=False)  # Queries per second
    latency_distribution: Dict[str, int] = field(init=False)
    cv: float = field(init=False)  # Coefficient of variation

    def __post_init__(self):
        """Calculate statistics after initialization."""
        self._calculate_statistics()

    def _calculate_statistics(self):
        """Calculate all statistics from executions."""
        if not self.executions:
            self._set_empty_stats()
            return

        successful_durations = [e.duration_ms for e in self.executions if e.success]

        if not successful_durations:
            self._set_empty_stats()
            return

        self.min_time_ms = min(successful_durations)
        self.max_time_ms = max(successful_durations)
        self.avg_time_ms = statistics.mean(successful_durations)
        self.median_time_ms = statistics.median(successful_durations)

        if len(successful_durations) > 1:
            self.stddev_time_ms = statistics.stdev(successful_durations)
            self.cv = (
                (self.stddev_time_ms / self.avg_time_ms) if self.avg_time_ms > 0 else 0
            )
        else:
            self.stddev_time_ms = 0
            self.cv = 0

        # Calculate percentiles
        self.percentiles = self._calculate_percentiles(successful_durations)

        # Calculate throughput
        total_time_seconds = (self.end_time - self.start_time).total_seconds()
        self.throughput_qps = (
            self.successful_runs / total_time_seconds if total_time_seconds > 0 else 0
        )

        # Calculate latency distribution
        self.latency_distribution = self._calculate_latency_distribution(
            successful_durations
        )

    def _set_empty_stats(self):
        """Set empty statistics when no data available."""
        self.min_time_ms = 0
        self.max_time_ms = 0
        self.avg_time_ms = 0
        self.median_time_ms = 0
        self.stddev_time_ms = 0
        self.cv = 0
        self.percentiles = {}
        self.throughput_qps = 0
        self.latency_distribution = {}

    def _calculate_percentiles(self, durations: List[float]) -> Dict[str, float]:
        """Calculate percentiles from durations."""
        if not durations:
            return {}

        sorted_durations = sorted(durations)
        percentiles = {}

        for p in [25, 50, 75, 90, 95, 99, 99.9]:
            idx = int(len(sorted_durations) * p / 100)
            idx = min(idx, len(sorted_durations) - 1)
            percentiles[f"p{p}"] = sorted_durations[idx]

        return percentiles

    def _calculate_latency_distribution(self, durations: List[float]) -> Dict[str, int]:
        """Calculate latency distribution buckets."""
        buckets = {
            "<1ms": 0,
            "1-5ms": 0,
            "5-10ms": 0,
            "10-50ms": 0,
            "50-100ms": 0,
            "100-500ms": 0,
            "500ms-1s": 0,
            "1s-5s": 0,
            ">5s": 0,
        }

        for d in durations:
            if d < 1:
                buckets["<1ms"] += 1
            elif d < 5:
                buckets["1-5ms"] += 1
            elif d < 10:
                buckets["5-10ms"] += 1
            elif d < 50:
                buckets["10-50ms"] += 1
            elif d < 100:
                buckets["50-100ms"] += 1
            elif d < 500:
                buckets["100-500ms"] += 1
            elif d < 1000:
                buckets["500ms-1s"] += 1
            elif d < 5000:
                buckets["1s-5s"] += 1
            else:
                buckets[">5s"] += 1

        return buckets

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the benchmark results."""
        return {
            "total_runs": self.total_runs,
            "successful_runs": self.successful_runs,
            "failed_runs": self.failed_runs,
            "success_rate": (self.successful_runs / self.total_runs * 100)
            if self.total_runs > 0
            else 0,
            "duration_seconds": (self.end_time - self.start_time).total_seconds(),
            "min_ms": self.min_time_ms,
            "max_ms": self.max_time_ms,
            "avg_ms": self.avg_time_ms,
            "median_ms": self.median_time_ms,
            "stddev_ms": self.stddev_time_ms,
            "cv": self.cv,
            "throughput_qps": self.throughput_qps,
        }

    def to_json(self, include_executions: bool = False) -> str:
        """Export results to JSON."""
        data = {
            "summary": self.get_summary(),
            "statistics": {
                "min_ms": self.min_time_ms,
                "max_ms": self.max_time_ms,
                "avg_ms": self.avg_time_ms,
                "median_ms": self.median_time_ms,
                "stddev_ms": self.stddev_time_ms,
                "cv": self.cv,
                "percentiles": self.percentiles,
                "throughput_qps": self.throughput_qps,
            },
            "latency_distribution": self.latency_distribution,
            "metadata": {
                "start_time": self.start_time.isoformat(),
                "end_time": self.end_time.isoformat(),
            },
        }

        if include_executions:
            data["executions"] = [e.to_dict() for e in self.executions]

        return json.dumps(data, indent=2)


class MetricsCollector:
    """Collects and aggregates benchmark metrics."""

    def __init__(self):
        self.executions: List[QueryExecution] = []
        self._start_time: Optional[datetime] = None
        self._end_time: Optional[datetime] = None
        self._is_collecting = False

    def start(self):
        """Mark the start of benchmarking."""
        self._start_time = datetime.now()
        self._is_collecting = True

    def end(self):
        """Mark the end of benchmarking."""
        self._end_time = datetime.now()
        self._is_collecting = False

    def add_execution(self, execution: QueryExecution):
        """Add a query execution result."""
        if not self._is_collecting:
            raise RuntimeError("Metrics collector is not started")
        self.executions.append(execution)

    def get_result(self) -> BenchmarkResult:
        """Get the complete benchmark result."""
        if not self._start_time or not self._end_time:
            raise RuntimeError("Benchmark not properly started/ended")

        successful = [e for e in self.executions if e.success]
        failed = [e for e in self.executions if not e.success]

        return BenchmarkResult(
            executions=self.executions,
            total_runs=len(self.executions),
            successful_runs=len(successful),
            failed_runs=len(failed),
            start_time=self._start_time,
            end_time=self._end_time,
        )

    def get_current_stats(self) -> Dict[str, Any]:
        """Get current statistics while collecting."""
        successful = [e for e in self.executions if e.success]
        failed = [e for e in self.executions if not e.success]

        stats = {
            "total_runs": len(self.executions),
            "successful_runs": len(successful),
            "failed_runs": len(failed),
            "is_collecting": self._is_collecting,
        }

        if successful:
            durations = [e.duration_ms for e in successful]
            stats.update(
                {
                    "current_avg_ms": statistics.mean(durations),
                    "current_min_ms": min(durations),
                    "current_max_ms": max(durations),
                }
            )

        return stats

    def reset(self):
        """Reset the collector."""
        self.executions = []
        self._start_time = None
        self._end_time = None
        self._is_collecting = False
