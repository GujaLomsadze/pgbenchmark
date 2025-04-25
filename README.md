<div align="center">

# pgbenchmark

[//]: # ([![codecov]&#40;https://codecov.io/github/GujaLomsadze/pgbenchmark/graph/badge.svg?token=J2VYSHFE1K&#41;]&#40;https://codecov.io/github/GujaLomsadze/pgbenchmark&#41;)
![PyPI Version](https://img.shields.io/pypi/v/pgbenchmark.svg?style=for-the-badge)
![PyPI - Downloads](https://img.shields.io/pypi/dm/pgbenchmark?style=for-the-badge)

</div>

<h3>
Python package to benchmark query performance on a PostgreSQL database. It allows you to measure the
execution time of queries over multiple runs, providing detailed metrics about each run's performance.
</h3>

---

### Please consider

1. Main purpose of this library is to easily microbenchmark queries without boilerplate.
2. This tool is not for Database Administrators (Yet).
3. There's a lot of re-thinking and work in progress ongoing on this project
4. Most of the things will be backwards-compatible, but some things might deprecate/break in future releases.
5. Since I'm developing this library as I go, mostly for my personal use, code here and there is sub-optimal.

---

## Installation

```shell
pip install pgbenchmark
```

---

# Example

#### For ParallelBenchmark, please scroll down....

```python
import psycopg2
from pgbenchmark import Benchmark

conn = psycopg2.connect(
    dbname="postgres",
    user="postgres",
    password="  << Your Password >> ",
    host="localhost",
    port="5432"
)

benchmark = Benchmark(db_connection=conn, number_of_runs=1000)
benchmark.set_sql("SELECT 1;")

for result in benchmark:
    # {'run': X, 'sent_at': <DATETIME WITH MS>, 'duration': '0.000064'}
    pass

""" View Summary """
print(benchmark.get_execution_results())

# {'runs': 1000,
#      'min_time': '0.000576',
#      'max_time': '0.014741',
#      'avg_time': '0.0007',
#      'median_time': '0.000642',
#      'percentiles': {'p25': '0.000612',
#                      'p50': '0.000642',
#                      'p75': '0.000696',
#                      'p99': '0.001331'}
#      }
```

#### You can also pass SQL file, instead of query string

```python
benchmark.set_sql("./test.sql")
```

---

# Interactive | No-Code Mode

### Simply run in your terminal:

```shell
pgbenchmark
```

You'll see the ouput

```terminaloutput
[ http://127.0.0.1:8000 ] Click to open pgbenchmark Interface
```

![img](https://raw.githubusercontent.com/GujaLomsadze/pgbenchmark/main/UI.png)

### Configuration on the right, rest is very intuitive.

Pause and Resume buttons are not working for now :(

# More Examples

### Standard 'Benchmark' class allow all kinds of connections

1. Providing Nothing at all. Benchmark will use standard default factory values

```python
from pgbenchmark import Benchmark

benchmark = Benchmark(number_of_runs=1000)
benchmark.set_sql("SELECT 1;")

for iteration in benchmark:
    pass
```

2. Providing Connection Details as Dict.

```python
from pgbenchmark import Benchmark

params = {
    "dbname": "postgres",
    "host": "localhost",
    "port": "5432",
    "user": "postgres",
    "password": "postgres",
}

benchmark = Benchmark(db_connection=params, number_of_runs=1000)
benchmark.set_sql("SELECT 1;")

for iteration in benchmark:
    pass
```

3. Psycopg2 connection object directly

```python
from pgbenchmark import Benchmark

params = {
    "dbname": "postgres",
    "host": "localhost",
    "port": "5432",
    "user": "postgres",
    "password": "postgres",
}

benchmark = Benchmark(db_connection=params, number_of_runs=1000)
benchmark.set_sql("SELECT 1;")

for iteration in benchmark:
    pass
```

---

# Example with Parallel execution

### ⚠️ Please be careful. If you are running on Linux, `pgbenchmark` will load your cores on 100% !!!⚠️

```python
from pgbenchmark import ParallelBenchmark

pg_conn_params = {
    "dbname": "postgres",
    "user": "postgres",
    "password": "",
    "host": "localhost",
    "port": "5432"
}

# --- Configuration ---
N_PROCS = 20
N_RUNS_PER_PROC = 1000
SQL_QUERY = "SELECT 1;"

parallel_bench = ParallelBenchmark(
    num_processes=N_PROCS,
    number_of_runs=N_RUNS_PER_PROC,
    db_connection_info=pg_conn_params
)
parallel_bench.set_sql(SQL_QUERY)

if __name__ == '__main__':

    print("===================== Simply `run()` and get results at the end ==============================")

    parallel_bench.run()

    print("===================== Or... Iterate Live and get results per-process =========================")
    for result_from_process in parallel_bench.iter_successful_results():
        print(result_from_process)

    final_results = parallel_bench.get_execution_results()
```

# Example with Template Engine

### From version `0.1.0` pgbenchmark supports simple Template Engine for queries.

<h3>

To emulate "real" scenarios, with different random or pre-defined queries, you can use `set_sql_formatter` method <br>
to generate queries. Same syntax as Jinja2 using `{{ [X] }}` for variables.

</h3>

```python
def generate_random_value():
    return round(random.randint(10, 1000), 2)


N_RUNS_PER_PROC = 1000

SQL_QUERY = "SELECT {{random_value}};"

# ....

parallel_bench.set_sql(SQL_QUERY)

"""===================== use `ANY` function to generate values for your query =============================="""
parallel_bench.set_sql_formatter(for_placeholder="random_value", generator=generate_random_value)
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
