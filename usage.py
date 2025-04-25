import psycopg2
from pgbenchmark import Benchmark

benchmark = Benchmark(number_of_runs=1000, db_connection={"password": "asdASD123"})
benchmark.set_sql("SELECT 1;")

for iteration in benchmark:
    print(iteration)
