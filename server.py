"""
FastAPI HTTP wrapper for HIVE Agent Framework
Allows running HIVE agents via HTTP API on Railway
"""
import os
import sys
import json
from typing import Dict, Any, Optional
from pathlib import Path
from urllib import request as urllib_request
from urllib import error as urllib_error

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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

# Allow browser clients to call the API (handles CORS preflight OPTIONS).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

EXPORTS_DIR = Path(os.getenv("EXPORTS_DIR", "/app/exports"))

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

    agent_path = EXPORTS_DIR / agent_name
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


def _call_openai(agent_name: str, goal: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")

    model = os.getenv("DEFAULT_MODEL", "gpt-4.1-mini")
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            f"You are agent '{agent_name}'. Goal: {goal}. "
                            "Use the input data to perform the task and return a practical answer."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": json.dumps(input_data)}],
            },
        ],
        "temperature": 0.2,
    }
    req = urllib_request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    content = body.get("output_text")
    if not content:
        output = body.get("output", [])
        text_parts = []
        for item in output:
            if not isinstance(item, dict):
                continue
            for block in item.get("content", []):
                if not isinstance(block, dict):
                    continue
                if block.get("type") in ("output_text", "text"):
                    text = block.get("text")
                    if text:
                        text_parts.append(text)
        content = "\n".join(text_parts).strip()

    if not content:
        raise RuntimeError("OpenAI returned empty response")
    return {
        "provider": "openai",
        "model": model,
        "response": content,
    }


def _call_anthropic(agent_name: str, goal: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    model = os.getenv("DEFAULT_MODEL", "claude-sonnet-4-20250514")
    payload = {
        "model": model,
        "max_tokens": 1200,
        "system": (
            f"You are agent '{agent_name}'. Goal: {goal}. "
            "Use the input data to perform the task and return a practical answer."
        ),
        "messages": [{"role": "user", "content": json.dumps(input_data)}],
    }
    req = urllib_request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    blocks = body.get("content", [])
    text_parts = [
        block.get("text", "") for block in blocks if isinstance(block, dict) and block.get("type") == "text"
    ]
    content = "\n".join([t for t in text_parts if t]).strip()
    if not content:
        raise RuntimeError("Anthropic returned empty response")
    return {
        "provider": "anthropic",
        "model": model,
        "response": content,
    }


def _call_gemini(agent_name: str, goal: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not configured")

    model = os.getenv("DEFAULT_MODEL", "gemini-2.5-flash")
    payload = {
        "systemInstruction": {
            "parts": [
                {
                    "text": (
                        f"You are agent '{agent_name}'. Goal: {goal}. "
                        "Use the input data to perform the task and return a practical answer."
                    )
                }
            ]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": json.dumps(input_data)}],
            }
        ],
        "generationConfig": {"temperature": 0.2},
    }
    req = urllib_request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    candidates = body.get("candidates", [])
    text_parts = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            if isinstance(part, dict):
                text = part.get("text")
                if text:
                    text_parts.append(text)
    content = "\n".join(text_parts).strip()
    if not content:
        raise RuntimeError("Gemini returned empty response")
    return {
        "provider": "google",
        "model": model,
        "response": content,
    }


def _run_api_generated_agent(agent_name: str, config: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
    goal = config.get("goal") or config.get("description") or "Solve the requested task."
    model = os.getenv("DEFAULT_MODEL", "").lower()
    try:
        if model.startswith("claude") and os.getenv("ANTHROPIC_API_KEY"):
            llm_result = _call_anthropic(agent_name, goal, input_data)
        elif model.startswith("gemini") and os.getenv("GOOGLE_API_KEY"):
            llm_result = _call_gemini(agent_name, goal, input_data)
        elif model.startswith(("gpt", "o1", "o3", "o4")) and os.getenv("OPENAI_API_KEY"):
            llm_result = _call_openai(agent_name, goal, input_data)
        elif os.getenv("OPENAI_API_KEY"):
            llm_result = _call_openai(agent_name, goal, input_data)
        elif os.getenv("ANTHROPIC_API_KEY"):
            llm_result = _call_anthropic(agent_name, goal, input_data)
        elif os.getenv("GOOGLE_API_KEY"):
            llm_result = _call_gemini(agent_name, goal, input_data)
        else:
            raise HTTPException(
                500,
                "No supported LLM API key found. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY."
            )
    except urllib_error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            err_body = str(e)
        raise HTTPException(502, f"LLM request failed: {err_body}") from e
    except urllib_error.URLError as e:
        raise HTTPException(502, f"LLM network error: {str(e)}") from e
    except RuntimeError as e:
        raise HTTPException(502, str(e)) from e

    return {
        "status": "success",
        "agent": agent_name,
        "goal": goal,
        "input": input_data,
        "provider": llm_result["provider"],
        "model": llm_result["model"],
        "response": llm_result["response"],
    }

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
    exports_dir = EXPORTS_DIR
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
        
        agent_path = EXPORTS_DIR / agent_name
        if not agent_path.exists():
            raise HTTPException(404, f"Agent '{agent_name}' not found")

        config_file = agent_path / "agent.json"
        config = {}
        if config_file.exists():
            with open(config_file, "r") as f:
                config = json.load(f)

        if config.get("type") == "api_generated":
            return {
                "agent_name": agent_name,
                "status": "success",
                "output": _run_api_generated_agent(agent_name, config, input_data),
            }
        
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
    
    agent_path = EXPORTS_DIR / agent_name
    if not agent_path.exists():
        raise HTTPException(404, "Agent not found")
    
    with open(agent_path / "agent.json", "r") as f:
        return json.load(f)

@app.delete("/agents/manage/{agent_name}")
async def delete_agent(agent_name: str):
    """Delete an agent"""
    if agent_name == "demo_agent":
        raise HTTPException(403, "Cannot delete demo_agent")
    
    agent_path = EXPORTS_DIR / agent_name
    if not agent_path.exists():
        raise HTTPException(404, "Agent not found")
    
    import shutil
    shutil.rmtree(agent_path)
    return {"status": "success", "message": f"Deleted {agent_name}"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
