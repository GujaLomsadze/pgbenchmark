import psycopg2
from pgbenchmark import Benchmark

conn = psycopg2.connect(
    dbname="postgres",
    user="postgres",
    password="asdASD123",
    host="localhost",
    port="5433"
)

n_runs = 1_000

benchmark = Benchmark(db_connection=conn, number_of_runs=n_runs)
benchmark.set_sql("select * from information_schema.tables;")

for result in benchmark:
    print(result)
    # {'sent_at': '2025-04-18T14:17:00.891971+00:00', 'duration': '0.000612'}

print(benchmark.get_execution_results())
# print(benchmark.get_execution_timeseries())
