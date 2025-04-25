from pgbenchmark import ParallelBenchmark
import random


def generate_random_value():
    return round(random.randint(10, 1000), 2)


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

parallel_bench.set_sql_formatter(for_placeholder="random_value", generator=generate_random_value)

if __name__ == '__main__':
    for result_from_process in parallel_bench.iter_successful_results():
        print(result_from_process)

    final_results = parallel_bench.get_execution_results()
