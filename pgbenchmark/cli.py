import time

import psycopg2
import click
from pgbenchmark.benchmark import Benchmark
from pgbenchmark.server import start_server_background


@click.command()
@click.option('--sql', default='SELECT 1;', help='SQL Statement to Benchmark')
@click.option('--runs', default=1000, help='Number of runs for Benchmark')
@click.option('--visualize', default=False, type=click.BOOL, help='Enable visualization for the benchmark')
@click.option('--host', default='localhost', help='Database host')
@click.option('--port', default=5433, help='Database port')
@click.option('--user', default='postgres', help='Database user')
@click.option('--password', default='asdASD123', help='Database password')
def main(sql, runs, visualize, host, port, user, password):
    conn = psycopg2.connect(
        dbname="postgres",
        user=user,
        password=password,
        host=host,
        port=port
    )

    if visualize:
        start_server_background()
        print("[ http://127.0.0.1:4761 ] Click to view Live benchmark timeseries")

    benchmark = Benchmark(conn, runs)
    benchmark.set_sql(sql)

    for _ in benchmark:
        pass

    print(f"\n--- Benchmark Complete\n")

    execution_results = benchmark.get_execution_results()

    print(f"Runs: [{execution_results['runs']}]")
    print(f"Minimum Time: [{execution_results['min_time']}] seconds")
    print(f"Maximum Time: [{execution_results['max_time']}] seconds")
    print(f"Average Time: [{execution_results['avg_time']}] seconds")


if __name__ == "__main__":
    main()
