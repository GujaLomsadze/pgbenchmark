import psycopg2
import click
from pgbenchmark.benchmark import Benchmark
from pgbenchmark.server import start_server_background


@click.command()
@click.option('--sql', default='SELECT 1;', help='SQL Statement to Benchmark')
@click.option('--runs', default=1, help='Number of runs for Benchmark')
@click.option('--visualize', default=True, type=click.BOOL, help='Enable visualization for the benchmark')
@click.option('--host', default='localhost', help='Database host')
@click.option('--port', default=5432, help='Database port')
@click.option('--user', default='postgres', help='Database user')
@click.option('--password', default='password', help='Database password')
def main(sql, runs, visualize, host, port, user, password):
    conn = psycopg2.connect(
        dbname="postgres", user=user, password=password, host=host, port=port
    )
    if visualize:
        start_server_background()

    benchmark = Benchmark(conn, runs, visualize=visualize)
    benchmark.set_sql(sql)


if __name__ == "__main__":
    main()
