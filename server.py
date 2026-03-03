"""
FastAPI HTTP wrapper for HIVE Agent Framework
Allows running HIVE agents via HTTP API on Railway
"""
import os
import sys
import json
from typing import Dict, Any, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

# Add HIVE to path
sys.path.insert(0, str(Path(__file__).parent / "core"))
sys.path.insert(0, str(Path(__file__).parent / "exports"))

app = FastAPI(
    title="HIVE Agent Framework API",
    description="HTTP API for running HIVE agents",
    version="0.1.0"
)

# Request/Response Models
class AgentRunRequest(BaseModel):
    agent_name: str
    input_data: Dict[str, Any]
    stream: bool = False

class AgentRunResponse(BaseModel):
    agent_name: str
    status: str
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

# Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint for Railway"""
    try:
        import framework
        return {"status": "healthy", "framework": "loaded"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )

@app.get("/")
async def root():
    """Root endpoint with API info"""
    return {
        "name": "HIVE Agent Framework API",
        "version": "0.1.0",
        "endpoints": {
            "health": "/health",
            "list_agents": "/agents",
            "run_agent": "/agents/run",
            "docs": "/docs"
        }
    }

@app.get("/agents")
async def list_agents():
    """List all available agents"""
    exports_dir = Path("/app/exports")
    agents = []
    
    if exports_dir.exists():
        for agent_dir in exports_dir.iterdir():
            if agent_dir.is_dir() and (agent_dir / "agent.json").exists():
                agents.append({
                    "name": agent_dir.name,
                    "path": str(agent_dir)
                })
    
    return {"agents": agents, "count": len(agents)}

@app.post("/agents/run", response_model=AgentRunResponse)
async def run_agent(request: AgentRunRequest, background_tasks: BackgroundTasks):
    """
    Run a HIVE agent with provided input
    
    Example:
    {
        "agent_name": "my_agent",
        "input_data": {"task": "Your task here"},
        "stream": false
    }
    """
    try:
        # Import HIVE runner
        from framework.runner import AgentRunner
        
        # Construct agent path
        agent_path = Path(f"/app/exports/{request.agent_name}")
        
        if not agent_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Agent '{request.agent_name}' not found"
            )
        
        # Run the agent
        runner = AgentRunner(str(agent_path))
        result = runner.run(input_data=request.input_data)
        
        return AgentRunResponse(
            agent_name=request.agent_name,
            status="success",
            output=result
        )
        
    except Exception as e:
        return AgentRunResponse(
            agent_name=request.agent_name,
            status="error",
            error=str(e)
        )

@app.post("/agents/{agent_name}/run")
async def run_agent_by_name(
    agent_name: str,
    input_data: Dict[str, Any]
):
    """Simplified endpoint to run agent by name"""
    request = AgentRunRequest(
        agent_name=agent_name,
        input_data=input_data
    )
    return await run_agent(request, BackgroundTasks())

# WebSocket endpoint for streaming (optional)
# @app.websocket("/agents/{agent_name}/stream")
# async def stream_agent(websocket: WebSocket, agent_name: str):
#     await websocket.accept()
#     # Implement streaming logic here
#     pass

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
