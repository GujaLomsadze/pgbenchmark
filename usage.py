import psycopg2
from pgbenchmark import Benchmark

conn = psycopg2.connect(
    "<< YOUR CONNECTION >>"
)

benchmark = Benchmark(db_connection=conn, number_of_runs=1000)
benchmark.set_sql("./test.sql")

for result in benchmark:
    # {'run': X, 'sent_at': <DATETIME WITH MS>, 'duration': '0.000064'}
    pass

""" View Summary """
print(benchmark.get_execution_results())
# {'runs': 1000, 'min_time': '0.00005', 'max_time': '0.000287', 'avg_time': '0.000072'}
