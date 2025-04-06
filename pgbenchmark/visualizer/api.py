import json
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
import asyncio
from pgbenchmark.benchmark import shared_benchmark
from pgbenchmark.visualizer.dashboard import get_dashboard_html

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return get_dashboard_html()


@app.get("/data", response_class=JSONResponse)
async def get_data():
    if shared_benchmark:
        return shared_benchmark._run_timestamps
    return []


@app.websocket("/ws/data")
async def websocket_data(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            if shared_benchmark and shared_benchmark._run_timestamps:
                data = shared_benchmark._run_timestamps[-1]
                await websocket.send_text(json.dumps(data))

            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        print("Client disconnected")
