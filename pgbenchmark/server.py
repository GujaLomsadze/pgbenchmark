import uvicorn
from threading import Thread


def run_server():
    from pgbenchmark.visualizer.main import app
    uvicorn.run(app, host="127.0.0.1", port=4761, log_level="critical")


def start_server_background():
    t = Thread(target=run_server, daemon=True)
    t.start()
