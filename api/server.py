import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger("moon.api")

app = FastAPI(title="The Moon — Cyber-Agentic API")

# Allow Frontend (Vite)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CommandRequest(BaseModel):
    command: str
    target_agent: str = "orchestrator"


@app.get("/api/health")
async def health_check(request: Request):
    """Returns general system health and uptime."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    
    status = "offline"
    agents_count = 0
    if orchestrator:
        status = "online"
        agents_count = len(orchestrator._agents)

    return {
        "status": status,
        "timestamp": datetime.now().isoformat(),
        "agents_active": agents_count,
        "version": "v1.cyber"
    }


@app.get("/api/agents")
async def get_agents(request: Request):
    """Returns the list of active agents and their circuit breaker states."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if not orchestrator:
        return {"error": "Orchestrator not attached to API state"}

    agents_data = []
    
    # Core Agents
    for name, agent in orchestrator._agents.items():
        circuit = orchestrator._circuits.get(name)
        circuit_status = "open" if (circuit and circuit.open) else "closed"
        
        # Pull extra state from Sentinel if available
        extra = {}
        if name == "MoonSentinelAgent":
            extra = agent._get_status()

        agents_data.append({
            "name": name,
            "description": agent.description,
            "priority": agent.priority.name,
            "circuit_breaker": circuit_status,
            "extra": extra
        })
        
    return {"agents": agents_data}


@app.get("/api/logs/stream")
async def stream_logs(request: Request):
    """SSE endpoint to stream moon_system.log in real-time."""
    moon_dir = Path(__file__).parent.parent
    log_file = moon_dir / "moon_system.log"
    
    async def log_generator():
        if not log_file.exists():
            yield {"data": "Log file not found."}
            return

        with open(log_file, "r") as f:
            # Go to the end of file, minus 100 lines for context
            lines = f.readlines()
            for line in lines[-50:]:
                yield {"data": line.strip()}
            
            # Now continuously watch for new lines
            while True:
                if await request.is_disconnected():
                    break
                
                line = f.readline()
                if line:
                    yield {"data": line.strip()}
                else:
                    await asyncio.sleep(0.5)

    return EventSourceResponse(log_generator())


@app.post("/api/command")
async def send_command(req: CommandRequest, request: Request):
    """Dispatches a command to the system."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if not orchestrator:
        return {"error": "Orchestrator offline"}

    cmd = req.command.strip()
    logger.info(f"API Command received: {cmd} targeted to {req.target_agent}")

    if req.target_agent.lower() == "orchestrator":
        # Dispatch via orchestrator main execute
        # Create a task so it doesn't block the API response
        asyncio.create_task(orchestrator.execute(cmd, action="api_command"))
        return {"status": "dispatched", "message": f"Orchestrator running: {cmd}"}
    
    elif req.target_agent in orchestrator._agents:
        # Dispatch to specific agent
        agent = orchestrator._agents[req.target_agent]
        asyncio.create_task(agent.execute(cmd, action="api_command"))
        return {"status": "dispatched", "message": f"{req.target_agent} running: {cmd}"}
    
    return {"error": f"Agent {req.target_agent} not found"}

@app.get("/api/agents/{agent_name}")
async def get_agent_details(agent_name: str, request: Request):
    """Returns deep details about a specific agent."""
    orch = request.app.state.orchestrator
    if agent_name not in orch._agents:
        return {"error": "Agent not found"}
        
    agent = orch._agents[agent_name]
    circuit = orch._circuits.get(agent_name)
    
    # Safely extract memory or state if available
    memory = []
    if hasattr(agent, "_memory"):
        # Just grab the last 5 entries to avoid massive payloads
        mem_list = getattr(agent, "_memory", [])
        memory = mem_list[-5:] if isinstance(mem_list, list) else []
        
    return {
        "name": agent.name,
        "description": agent.description,
        "priority": agent.priority.name if hasattr(agent.priority, "name") else str(agent.priority),
        "status": "offline" if circuit and circuit.open else "online",
        "failures": circuit.failures if circuit else 0,
        "memory": memory,
        "current_task": getattr(agent, "current_task", None),
    }

class AgentActionRequest(BaseModel):
    action: str
    payload: Optional[Dict[str, Any]] = None

@app.post("/api/agents/{agent_name}/action")
async def agent_action(agent_name: str, req: AgentActionRequest, request: Request):
    """Send a direct control action to an agent."""
    orch = request.app.state.orchestrator
    if agent_name not in orch._agents:
        return {"error": "Agent not found"}
        
    message = f"Action '{req.action}' received by {agent_name}."
    
    # Special handling for UI requests
    if req.action == "ping":
        return {"status": "success", "message": f"Pong from {agent_name}!"}
        
    # Default success response to show UI tracking
    return {"status": "success", "message": message, "action": req.action}

@app.get("/api/tasks")
async def get_active_tasks(request: Request):
    """Returns the orchestrator's proactive loop status and background automations."""
    orch = request.app.state.orchestrator
    tasks = []
    
    # 1. Sentinel
    tasks.append({
        "id": "sentinel-proactive",
        "name": "MoonSentinel Vigilance Loop",
        "status": "running",
        "type": "daemon",
        "details": "Monitoring tech trends and ecosystem health natively."
    })
    
    # 2. Main loop
    if orch._autonomous_task and not orch._autonomous_task.done():
        tasks.append({
            "id": "orchestrator-autonomous",
            "name": "Orchestrator Proactive Loop",
            "status": "running",
            "type": "loop",
            "details": "Central event horizon executing background workflows."
        })
    else:
        tasks.append({
            "id": "orchestrator-autonomous",
            "name": "Orchestrator Proactive Loop",
            "status": "stalled",
            "type": "loop",
            "details": "The loop is currently inactive or crashed."
        })
        
    # Expand to any other known background loops
    return {"tasks": tasks}

@app.get("/api/reports")
async def get_reports():
    """Returns the latest intelligence and trend reports gathered by Sentinel."""
    moon_dir = Path(__file__).parent.parent
    reports_file = moon_dir / "data" / "sentinel_initiatives.json"
    
    if not reports_file.exists():
        return {"reports": []}
    
    try:
        with open(reports_file, "r") as f:
            initiatives = json.load(f)
            
        reports = [
            req for req in initiatives 
            if req.get("type") == "tech_trend"
        ]
        
        # Sort newest first based on timestamp
        reports.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return {"reports": reports[:10]}
    except Exception as e:
        logger.error(f"Error reading reports: {e}")
        return {"reports": []}

