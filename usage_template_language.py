import random
import string

from pgbenchmark import ParallelBenchmark

conn_params = {
    "dbname": "postgres",
    "user": "postgres",
    "password": "asdASD123",
    "host": "localhost",
    "port": "5432"
}

n_procs = 20
n_runs_per_proc = 10


# Generator Function for Random Product Price
def generate_random_price():
    return round(random.randint(10, 1000), 2)


# Generator Function for Random Product Name (String)
def generate_random_string(length=10):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))


parallel_bench_pg = ParallelBenchmark(
    num_processes=n_procs,
    number_of_runs=n_runs_per_proc,
    db_connection_info=conn_params
)

# Define the SQL Query Template
query = """
        INSERT INTO products (name, price, stock_quantity)
        VALUES ('{{product_name}}', {{price_value}}, 10);
        """

# ===============================
# Note that similar to Jinja2, you have to define template variables within Query
#   {{product_name}}
#   {{price_value}}
# ===============================

parallel_bench_pg.set_sql(query)

# Set formatters
parallel_bench_pg.set_sql_formatter(for_placeholder="price_value", generator=generate_random_price)
parallel_bench_pg.set_sql_formatter(for_placeholder="product_name", generator=generate_random_string)

if __name__ == '__main__':
    # Run the Parallel Benchmark
    parallel_bench_pg.run()

    results_pg = parallel_bench_pg.get_execution_results()

    throughput = results_pg["throughput_runs_per_sec"]
    avg_time = results_pg["avg_time"]

    print("\n=============================================================================")
    print("                           Benchmark Results                             ")
    print("=============================================================================")
    print(f"Throughput (runs/sec): {throughput}")
    print(f"Average Execution Time (sec): {avg_time}")
