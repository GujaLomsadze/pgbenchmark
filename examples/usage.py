import psycopg2
from pgbenchmark import Benchmark

pg_conn_params = {
    "dbname": "postgres",
    "user": "postgres",
    "password": "",
    "host": "localhost",
    "port": "5432"
}

benchmark = Benchmark(number_of_runs=1000, db_connection=pg_conn_params)
benchmark.set_sql("SELECT 1;")

for iteration in benchmark:
    print(iteration)
