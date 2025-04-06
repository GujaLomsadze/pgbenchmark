# pgbenchmark/visualizer/api.py
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from pgbenchmark.pgbenchmark.benchmark import shared_benchmark
from pgbenchmark.pgbenchmark.visualizer.dashboard import get_dashboard_html

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return get_dashboard_html()


@app.get("/data", response_class=JSONResponse)
async def get_data():
    if shared_benchmark:
        return shared_benchmark._run_timestamps
    return []
