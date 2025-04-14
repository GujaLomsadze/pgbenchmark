<div align="center">

# pgbenchmark

[![codecov](https://codecov.io/github/GujaLomsadze/pgbenchmark/graph/badge.svg?token=J2VYSHFE1K)](https://codecov.io/github/GujaLomsadze/pgbenchmark)
![PyPI Version](https://img.shields.io/pypi/v/pgbenchmark.svg)
![PyPI Downloads](https://img.shields.io/pypi/dm/pgbenchmark.svg)

</div>

<h3>
Python package to benchmark query performance on a PostgreSQL database. It allows you to measure the
execution time of queries over multiple runs, providing detailed metrics about each run's performance.
</h3>


---

---

## Installation

```shell
pip install pgbenchmark
```

---

# Example

```python
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
```

#### You can also pass raw SQL as a String, instead of file

```python
benchmark.set_sql("SELECT 1;")
```

#### It also supports SQLAlchemy connection engine

```python
engine = create_engine("postgresql+psycopg2://.......")
conn = engine.connect()

# Set up benchmark class
benchmark = Benchmark(db_connection=conn, number_of_runs=5)
```

# Example with Parallel or Threaded execution

### ⚠️ Please be careful. If you are running on Linux, `pgbenchmark` will load your cores on 100% !!!⚠️

```python
from pgbenchmark import ParallelBenchmark  # <<-------- NEW IMPORT

conn_params = {
    "dbname": "postgres",
    "user": "postgres",
    "password": "",
    "host": "localhost",
    "port": "5432"
}

n_procs = 20  # Number of Processes (Cores basically)
n_runs_per_proc = 1_000

parallel_bench_pg = ParallelBenchmark(
    num_processes=n_procs,
    number_of_runs=n_runs_per_proc,
    db_connection_info=conn_params
)

parallel_bench_pg.set_sql("SELECT * from information_schema.tables;")  # Same as before

""" Unfortunately, as of now, you can't get execution results on the fly. """

parallel_bench_pg.run()  # RUN THE BENCHMARK 

results_pg = parallel_bench_pg.get_execution_results()
print(results_pg)
```

# Example with Template Engine
### From version `0.1.0` pgbenchmark supports simple Template Engine for queries.

```python
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
            INSERT INTO products (name, price, stock_quantity) VALUES ('{{product_name}}', {{price_value}}, 10);
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


# Run Benchmark
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
```

---

[//]: # ()

[//]: # (# Example with CLI)

[//]: # ()

[//]: # (`pgbenchmark` Support CLI for easier and faster usages. If you need to check one quick SQL statement&#40;s&#41; without)

[//]: # (boilerplate and Messing around in code, simply install the library and run:)

[//]: # ()

[//]: # (```shell)

[//]: # (pgbenchmark --sql "SELECT 1;" --runs=1_000_000)

[//]: # (```)

[//]: # ()

[//]: # (### If your benchmark runs long enough, you can view live visualization)

[//]: # ()

[//]: # (### Add `--visualize=True` flag)

[//]: # ()

[//]: # (```shell)

[//]: # (pgbenchmark --sql "SELECT 1;" --runs=1_000_000 --visualize=True)

[//]: # (```)

[//]: # ()

[//]: # (After running pgbenchmark, go)

[//]: # (to <a href="http://127.0.0.1:4761" class="external-link" target="_blank">http://127.0.0.1:4761</a>.)

[//]: # ()

[//]: # (<img src="examples/ui_screenshot.png" alt="img.png" width="900"/>)

[//]: # ()

[//]: # (It is live enough for you to have fun. You can choose between `100ms` and `5000ms` refresh intervals.)
