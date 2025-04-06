from pgbenchmark import Benchmark


def test_benchmark_init():
    bench = Benchmark(db_connection=None, number_of_runs=5)
    assert bench.number_of_runs == 5
