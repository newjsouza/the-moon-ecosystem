"""WorkspaceMonitor v2 — FastAPI backend with WebSocket live feed."""
import asyncio
import json
import logging
from datetime import datetime
from typing import AsyncGenerator

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

logger = logging.getLogger(__name__)

if HAS_FASTAPI:
    app = FastAPI(title="The Moon — Workspace Monitor v2")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    class ConnectionManager:
        def __init__(self):
            self.live_connections = []
            self.metrics_connections = []
        async def connect_live(self, ws): await ws.accept(); self.live_connections.append(ws)
        async def connect_metrics(self, ws): await ws.accept(); self.metrics_connections.append(ws)
        def disconnect(self, ws):
            self.live_connections = [c for c in self.live_connections if c != ws]
            self.metrics_connections = [c for c in self.metrics_connections if c != ws]
        async def broadcast_live(self, message):
            data = json.dumps(message, default=str)
            dead = []
            for ws in self.live_connections:
                try: await ws.send_text(data)
                except: dead.append(ws)
            for ws in dead: self.disconnect(ws)

    manager = ConnectionManager()
    _event_buffer = []

    @app.get("/")
    async def root():
        return {"status": "ok", "service": "The Moon WorkspaceMonitor v2", "timestamp": datetime.now().isoformat()}

    @app.get("/api/status")
    async def get_status():
        try:
            from core.observability.observer import MoonObserver
            observer = MoonObserver.get_instance()
            report = observer.health_report()
            return JSONResponse(content={"status": report.get("system_status", "unknown"), "agents": report.get("agents", {}), "timestamp": datetime.now().isoformat()})
        except Exception as e:
            return JSONResponse(content={"error": str(e), "status": "unavailable"}, status_code=503)

    @app.get("/api/agents")
    async def get_agents():
        try:
            from core.observability.observer import MoonObserver
            observer = MoonObserver.get_instance()
            report = observer.health_report()
            agents = [{"id": aid, "total_calls": m.get("total_calls", 0), "success_rate": m.get("success_rate", 0), "status": "healthy" if m.get("success_rate", 1) >= 0.8 else "degraded"} for aid, m in report.get("agents", {}).items()]
            return JSONResponse(content={"agents": agents, "count": len(agents), "timestamp": datetime.now().isoformat()})
        except Exception as e:
            return JSONResponse(content={"error": str(e)}, status_code=503)

    @app.get("/api/metrics")
    async def get_metrics():
        try:
            from core.observability.observer import MoonObserver
            return JSONResponse(content=MoonObserver.get_instance().health_report())
        except Exception as e:
            return JSONResponse(content={"error": str(e)}, status_code=503)

    @app.get("/api/events")
    async def get_events(limit: int = 50):
        return JSONResponse(content={"events": _event_buffer[-limit:], "total_buffered": len(_event_buffer)})

    @app.websocket("/ws/live")
    async def ws_live(websocket: WebSocket):
        await manager.connect_live(websocket)
        try:
            for event in _event_buffer[-20:]: await websocket.send_text(json.dumps(event, default=str))
            while True:
                await asyncio.sleep(30)
                await websocket.send_text(json.dumps({"type": "ping", "timestamp": datetime.now().isoformat()}))
        except WebSocketDisconnect: manager.disconnect(websocket)
        except: manager.disconnect(websocket)

    @app.websocket("/ws/metrics")
    async def ws_metrics(websocket: WebSocket):
        await manager.connect_metrics(websocket)
        try:
            while True:
                try:
                    from core.observability.observer import MoonObserver
                    payload = {"type": "metrics_update", "data": MoonObserver.get_instance().health_report(), "timestamp": datetime.now().isoformat()}
                    await websocket.send_text(json.dumps(payload, default=str))
                except Exception as e: await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
                await asyncio.sleep(5)
        except WebSocketDisconnect: manager.disconnect(websocket)
        except: manager.disconnect(websocket)

    async def start_messagebus_bridge():
        try:
            from core.message_bus import MessageBus
            bus = MessageBus()
            async def on_event(sender, topic, payload, **kwargs):
                event = {"type": "bus_event", "topic": topic, "sender": sender, "payload": payload if isinstance(payload, dict) else str(payload)[:200], "timestamp": datetime.now().isoformat()}
                _event_buffer.append(event)
                if len(_event_buffer) > 200: _event_buffer.pop(0)
                await manager.broadcast_live(event)
            bus.subscribe("*", on_event)
            logger.info("MessageBus bridge active ✅")
        except Exception as e: logger.warning(f"MessageBus bridge failed: {e}")

    @app.on_event("startup")
    async def on_startup():
        asyncio.create_task(start_messagebus_bridge())
        logger.info("WorkspaceMonitor v2 started on :3000")
else:
    app = None
    logger.warning("FastAPI not installed — WorkspaceMonitor unavailable")
