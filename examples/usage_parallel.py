from pgbenchmark import ParallelBenchmark

pg_conn_params = {
    "dbname": "postgres",
    "user": "postgres",
    "password": "asdASD123",
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

    print("===================== Or... Iterate Live and get results per-process =========================")
    for result_from_process in parallel_bench.iter_successful_results():
        print(result_from_process)

    final_results = parallel_bench.get_execution_results()