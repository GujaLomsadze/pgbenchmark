import click
from pgbenchmark.server import start_server_background


@click.command()
def main():
    start_server_background()
    print("[ http://127.0.0.1:4761 ] Click to view Live benchmark timeseries")


if __name__ == "__main__":
    main()
