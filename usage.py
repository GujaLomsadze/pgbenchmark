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
benchmark.set_sql("SELECT 100000;")

for result in benchmark:
    pass

print(benchmark.get_execution_results())
# {'runs': 1000, 'min_time': '0.000046', 'max_time': '0.00107', 'avg_time': '0.000065'}
# {'runs': 1000, 'min_time': '0.000047', 'max_time': '0.000256', 'avg_time':'0.000054'}
