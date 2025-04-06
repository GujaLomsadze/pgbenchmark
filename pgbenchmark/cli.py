import time

import psycopg2
import click
from pgbenchmark.benchmark import Benchmark
from pgbenchmark.server import start_server_background


@click.command()
@click.option('--sql', default='SELECT 1;', help='SQL Statement to Benchmark')
@click.option('--runs', default=1000, help='Number of runs for Benchmark')
@click.option('--visualize', default=True, type=click.BOOL, help='Enable visualization for the benchmark')
@click.option('--host', default='localhost', help='Database host')
@click.option('--port', default=5433, help='Database port')
@click.option('--user', default='postgres', help='Database user')
@click.option('--password', default='asdASD123', help='Database password')
def main(sql, runs, visualize, host, port, user, password):
    print(host, port, user, password)

    conn = psycopg2.connect(
        dbname="postgres",
        user=user,
        password=password,
        host=host,
        port=port
    )

    if visualize:
        start_server_background()

    benchmark = Benchmark(conn, runs)
    benchmark.set_sql("select 1;")

    i = 0
    for result in benchmark:
        print(result)
        if i == 1000:
            benchmark.set_sql("SELECT pg_sleep(0.1);")
        time.sleep(0.01)
        i += 1



if __name__ == "__main__":
    main()
