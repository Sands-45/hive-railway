"""
FastAPI HTTP wrapper for HIVE Agent Framework
Allows running HIVE agents via HTTP API on Railway
"""
import os
import sys
import json
from typing import Dict, Any, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Add HIVE to path
sys.path.insert(0, str(Path(__file__).parent / "core"))
sys.path.insert(0, str(Path(__file__).parent / "exports"))

app = FastAPI(
    title="HIVE Agent Framework API",
    description="HTTP API for running and creating HIVE agents",
    version="0.2.0"
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

class AgentCreateRequest(BaseModel):
    agent_name: str
    goal: str
    description: Optional[str] = None
    model: Optional[str] = None

class AgentCreateResponse(BaseModel):
    agent_name: str
    status: str
    message: str
    agent_path: Optional[str] = None
    error: Optional[str] = None

def _create_agent_impl(
    agent_name: str,
    goal: str,
    description: Optional[str] = None
) -> AgentCreateResponse:
    agent_name = agent_name.replace(" ", "_").lower()
    if not agent_name.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(400, "Invalid agent name")

    agent_path = Path(f"/app/exports/{agent_name}")
    if agent_path.exists():
        raise HTTPException(409, f"Agent '{agent_name}' exists")

    agent_path.mkdir(parents=True, exist_ok=True)

    config = {
        "name": agent_name,
        "version": "1.0.0",
        "description": description or goal,
        "goal": goal,
        "type": "api_generated"
    }

    with open(agent_path / "agent.json", "w") as f:
        json.dump(config, f, indent=2)

    code = f'''from typing import Dict, Any

def run(input_data: Dict[str, Any]) -> Dict[str, Any]:
    return {{
        "status": "success",
        "agent": "{agent_name}",
        "goal": "{goal}",
        "input": input_data,
        "note": "Basic template agent"
    }}
'''

    with open(agent_path / "__init__.py", "w") as f:
        f.write(code)

    return AgentCreateResponse(
        agent_name=agent_name,
        status="success",
        message=f"Created! Run with POST /agents/run/{agent_name}",
        agent_path=str(agent_path)
    )

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
    domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "https://your-app.railway.app")
    return {
        "name": "HIVE Agent Framework API",
        "version": "0.2.0",
        "status": "running",
        "new_feature": "✨ Create agents via API!",
        "quick_test": {
            "curl": f'curl -X POST {domain}/agents/run/demo_agent -H "Content-Type: application/json" -d \'{{"task": "Hello!"}}\''
        },
        "create_agent": {
            "curl": f'curl -X POST {domain}/agents/create -H "Content-Type: application/json" -d \'{{"agent_name": "my_agent", "goal": "Analyze data"}}\''
        },
        "endpoints": {
            "health": "GET /health",
            "list_agents": "GET /agents",
            "create_agent": "POST /agents/create - NEW!",
            "run_agent": "POST /agents/run/{name}",
            "get_agent": "GET /agents/{name}",
            "delete_agent": "DELETE /agents/manage/{name}",
            "docs": "GET /docs"
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
                try:
                    with open(agent_dir / "agent.json", "r") as f:
                        config = json.load(f)
                    agents.append({
                        "name": agent_dir.name,
                        "description": config.get("description", ""),
                        "type": config.get("type", "unknown")
                    })
                except:
                    agents.append({"name": agent_dir.name})
    
    return {"agents": agents, "count": len(agents)}

@app.post("/agents/create", response_model=AgentCreateResponse)
async def create_agent(request: AgentCreateRequest):
    """Create a new agent from a goal"""
    try:
        return _create_agent_impl(
            agent_name=request.agent_name,
            goal=request.goal,
            description=request.description
        )
    except HTTPException:
        raise
    except Exception as e:
        return AgentCreateResponse(
            agent_name=request.agent_name,
            status="error",
            message="Failed",
            error=str(e)
        )

@app.post("/agents/run/{agent_name}")
async def run_agent_by_name(agent_name: str, input_data: Dict[str, Any]):
    """Run an agent"""
    try:
        if agent_name == "demo_agent":
            return {
                "agent_name": "demo_agent",
                "status": "success",
                "output": {
                    "message": "Demo agent works! 🎉",
                    "input": input_data,
                    "next": "Create agents via POST /agents/create"
                }
            }
        
        agent_path = Path(f"/app/exports/{agent_name}")
        if not agent_path.exists():
            raise HTTPException(404, f"Agent '{agent_name}' not found")
        
        init_file = agent_path / "__init__.py"
        if init_file.exists():
            import importlib.util
            spec = importlib.util.spec_from_file_location(agent_name, init_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            if hasattr(module, 'run'):
                return {
                    "agent_name": agent_name,
                    "status": "success",
                    "output": module.run(input_data)
                }
        
        raise HTTPException(500, "Agent missing run() function")
        
    except HTTPException:
        raise
    except Exception as e:
        return {"agent_name": agent_name, "status": "error", "error": str(e)}

@app.get("/agents/{agent_name}")
async def get_agent_info(agent_name: str):
    """Get agent info"""
    if agent_name == "demo_agent":
        return {"name": "demo_agent", "type": "built-in", "protected": True}
    
    agent_path = Path(f"/app/exports/{agent_name}")
    if not agent_path.exists():
        raise HTTPException(404, "Agent not found")
    
    with open(agent_path / "agent.json", "r") as f:
        return json.load(f)

@app.delete("/agents/manage/{agent_name}")
async def delete_agent(agent_name: str):
    """Delete an agent"""
    if agent_name == "demo_agent":
        raise HTTPException(403, "Cannot delete demo_agent")
    
    agent_path = Path(f"/app/exports/{agent_name}")
    if not agent_path.exists():
        raise HTTPException(404, "Agent not found")
    
    import shutil
    shutil.rmtree(agent_path)
    return {"status": "success", "message": f"Deleted {agent_name}"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
