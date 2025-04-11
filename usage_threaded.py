from pgbenchmark import ThreadedBenchmark

"""
Compared to standard non-threaded usage, ThreadedBenchmark creates a connection by itself, therefore instead of
connection object, parameters must be provided.

Reasoning:
    1) Using separate connections per Thread. Emulating different users
    2) Connection might close before Client/User executes benchmark with `run()`
    3) PostgreSQl connection object is not Thread-Safe. Might cause racing conditions or corrupted Data.
"""

conn_params = {
    "dbname": "postgres",
    "user": "postgres",
    "password": "",
    "host": "localhost",
    "port": "5432"
}

n_threads = 20
n_total_runs_per_thread = 1

threaded_bench = ThreadedBenchmark(
    num_threads=n_threads,
    number_of_runs=n_total_runs_per_thread,
    db_connection_info=conn_params
)

# Query that sleeps for 1 second
threaded_bench.set_sql("SELECT 1;")

threaded_bench.run()

results = threaded_bench.get_execution_results()
print(results)

# Optionally get the timeseries data
# timeseries = threaded_benchmark_pg.get_execution_timeseries()
# print("\nTimeseries sample (first 5):")
# for record in timeseries[:5]:
#     print(record)
