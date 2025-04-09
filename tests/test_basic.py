"""
=================================
For now I don't have any meaningful tests.
Trying to figure out how to emulate local database to test this library easily. I have some options but still researching
=================================
"""

from pgbenchmark import Benchmark, ThreadedBenchmark, ParallelBenchmark


def test_benchmark_init():
    bench = Benchmark(db_connection=None, number_of_runs=5)
    assert bench.number_of_runs == 5


# def test_threaded_benchmark_init():
#     bench = ThreadedBenchmark(db_connection_info=None, num_threads=1, number_of_runs=5)
#     assert bench.number_of_runs == 5
#     assert bench.num_threads == 1
#
#
# def test_parallel_benchmark_init():
#     bench = ParallelBenchmark(db_connection_info=None, num_processes=1, number_of_runs=5)
#     assert bench.number_of_runs == 5
#     assert bench.num_processes == 1
