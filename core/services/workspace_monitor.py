import os
import json
import asyncio
import logging
from typing import List, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from core.message_bus import MessageBus
from core.workspace.manager import WorkspaceManager

# Setup levels
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("moon.workspace.monitor")

app = FastAPI(title="The Moon - Workspace Monitor")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass

manager = ConnectionManager()
# Global instances (will be injected by orchestrator if running internally)
_bus_instance = MessageBus()
_workspace_instance = WorkspaceManager()

def setup_monitor(bus: MessageBus, workspace: WorkspaceManager):
    global _bus_instance, _workspace_instance
    _bus_instance = bus
    _workspace_instance = workspace
    # Re-subscribe with new instance if needed
    _bus_instance.subscribe("workspace.network", bus_event_handler)

async def bus_event_handler(message):
    """Callback for message bus events to be streamed to the monitor."""
    event_data = {
        "type": "message",
        "sender": message.sender,
        "topic": message.topic,
        "payload": message.payload,
        "target": message.target,
        "timestamp": message.timestamp
    }
    await manager.broadcast(json.dumps(event_data))

@app.on_event("startup")
async def startup_event():
    # Only subscribe if not already injected. 
    # If injected, setup_monitor handles it.
    _bus_instance.subscribe("workspace.network", bus_event_handler)
    logger.info("Monitor Service started and subscribed to workspace.network")

@app.get("/api/status")
async def get_status():
    return {
        "rooms": _workspace_instance.get_all_rooms_status(),
        "history": [
            {
                "sender": m.sender,
                "topic": m.topic,
                "payload": m.payload,
                "target": m.target,
                "timestamp": m.timestamp
            } for m in _bus_instance.get_history()[-20:]
        ]
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial state
        initial_status = {
            "type": "init",
            "rooms": _workspace_instance.get_all_rooms_status()
        }
        await websocket.send_text(json.dumps(initial_status))
        
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

async def start_monitor_service(bus: MessageBus, workspace: WorkspaceManager, port=8081):
    """Starts the monitor service inside the current event loop."""
    setup_monitor(bus, workspace)
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    # Standalone mode
    uvicorn.run(app, host="0.0.0.0", port=8081)
