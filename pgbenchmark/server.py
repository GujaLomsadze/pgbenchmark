import uvicorn


def run_server():
    from pgbenchmark.visualizer.main import app
    uvicorn.run(app, host="localhost", port=8000, log_level="critical")


def start_server_background():
    run_server()
