import psycopg2
from pgbenchmark import Benchmark

conn = psycopg2.connect(
    dbname="postgres",
    user="postgres",
    password="asdASD123",
    host="localhost",
    port="5433"
)

benchmark = Benchmark(db_connection=conn, number_of_runs=1000)
benchmark.set_sql("SELECT 1;")

for result in benchmark:
    pass

print(benchmark.get_execution_results())
