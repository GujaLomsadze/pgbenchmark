from sqlalchemy import create_engine
from pgbenchmark import Benchmark

# Create engine and connection
engine = create_engine("postgresql+psycopg2://postgres:asdASD123@localhost:5433/postgres")
conn = engine.connect()

# Set up benchmark
benchmark = Benchmark(db_connection=conn, number_of_runs=5)
benchmark.set_sql("SELECT 1;")

# Run it manually
for result in benchmark:
    print(result)

print(benchmark.get_summary())
