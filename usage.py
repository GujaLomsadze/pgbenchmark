import psycopg2
from pgbenchmark import Benchmark

conn = psycopg2.connect(
    dbname="postgres",
    user="postgres",
    password="asdASD123",
    host="localhost",
    port="5432"
)

n_runs = 1_000

benchmark = Benchmark(db_connection=conn, number_of_runs=n_runs)
benchmark.set_sql("./test.sql")

for result in benchmark:
    print(result)
    # pass

print(benchmark.get_execution_results())
# print(benchmark.get_execution_timeseries())
