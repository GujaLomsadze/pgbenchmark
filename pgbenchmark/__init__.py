from .analyzers.statistics import StatisticalAnalyzer
from .benchmarks.async_bench import AsyncBenchmark
from .benchmarks.parallel import ParallelBenchmark
from .benchmarks.single import SingleThreadBenchmark
from .benchmarks.stress import StressBenchmark
from .core.base import BenchmarkConfig
from .core.connection import ConnectionManager
from .core.metrics import BenchmarkResult, QueryExecution

# from .analyzers.patterns import PatternAnalyzer
# from .analyzers.reports import ReportGenerator

__version__ = "2.0.0"

__all__ = [
    "SingleThreadBenchmark",
    "ParallelBenchmark",
    "AsyncBenchmark",
    "StressBenchmark",
    "BenchmarkConfig",
    "ConnectionManager",
    "BenchmarkResult",
    "QueryExecution",
    "StatisticalAnalyzer",
    # "PatternAnalyzer",
    # "ReportGenerator",
]


# Convenience function for quick benchmarking
def quick_benchmark(sql, connection_params=None, runs=100):
    """Quick benchmark function for simple use cases."""
    from .benchmarks.single import SingleThreadBenchmark
    from .core.base import BenchmarkConfig
    from .core.connection import ConnectionManager

    config = BenchmarkConfig(number_of_runs=runs)
    conn_manager = ConnectionManager(connection_params)
    benchmark = SingleThreadBenchmark(conn_manager, config)
    benchmark.set_sql(sql)
    return benchmark.run()
