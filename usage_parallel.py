import multiprocessing
from pprint import pprint

from pgbenchmark import ParallelBenchmark

if __name__ == '__main__':
    multiprocessing.freeze_support()

    conn_params = {
        "dbname": "postgres",
        "user": "postgres",
        "password": "asdASD123",
        "host": "localhost",
        "port": "5432"
    }

    n_procs = 20
    n_runs_per_proc = 100_000

    parallel_bench_pg = ParallelBenchmark(
        num_processes=n_procs,
        number_of_runs=n_runs_per_proc,
        db_connection_info=conn_params
    )
    parallel_bench_pg.set_sql("SELECT 1;")  # Faster query

    """ Unfortunately, as of now, you can't get execution results on the fly. """

    parallel_bench_pg.run()

    results_pg = parallel_bench_pg.get_execution_results()
    pprint(results_pg)
