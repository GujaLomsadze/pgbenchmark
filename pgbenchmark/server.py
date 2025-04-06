import uvicorn
from threading import Thread

def run_server():
    from pgbenchmark.visualizer.api import app
    uvicorn.run(app, host="127.0.0.1", port=8000)

def start_server_background():
    t = Thread(target=run_server, daemon=True)
    t.start()
