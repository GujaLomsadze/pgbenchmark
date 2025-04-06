import uvicorn
from threading import Thread


def run_server():
    from pgbenchmark.visualizer.api import app
    # TODO: Ability to provide Webserver with custom Port and Host (easy to do, lazy to implement)
    uvicorn.run(app, host="127.0.0.1", port=4761, log_level="critical")


def start_server_background():
    # TODO: Thread is Daemon, it's always running
    #  I need a 100% guarantee here that Thread is killed after Benchmark stops
    t = Thread(target=run_server, daemon=True)
    t.start()
