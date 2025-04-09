"""
ThreadedBenchmark and Benchmark are 2 separate Classes. Since final design is now not fully clear, keeping those two
classes Completely independent of each other.
"""

from .benchmark import Benchmark
from .benchmark_threaded import ThreadedBenchmark
from .benchmark_parallel import ParallelBenchmark
