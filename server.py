"""
FastAPI HTTP wrapper for HIVE Agent Framework
Allows running HIVE agents via HTTP API on Railway
"""
import os
import sys
import json
import subprocess
import shutil
from typing import Dict, Any, Optional
from pathlib import Path

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

    source_template = _find_runnable_hive_template_dir()
    shutil.copytree(source_template, agent_path)

    config_path = agent_path / "agent.json"
    if config_path.exists():
        with open(config_path, "r") as f:
            config = json.load(f)
    else:
        config = {}

    config["name"] = agent_name
    config["description"] = description or goal
    config["goal"] = goal
    config["type"] = "api_created_from_template"

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    if not (agent_path / "__main__.py").exists():
        raise HTTPException(
            500,
            (
                f"Template '{source_template}' does not contain __main__.py. "
                "Cannot create a runnable HIVE agent."
            ),
        )

    return AgentCreateResponse(
        agent_name=agent_name,
        status="success",
        message=(
            f"Created runnable HIVE agent from template '{source_template.name}'. "
            f"Run with POST /agents/run/{agent_name}."
        ),
        agent_path=str(agent_path)
    )


def _find_runnable_hive_template_dir() -> Path:
    root = Path(__file__).parent
    examples_dir = root / "examples"
    preferred = os.getenv("HIVE_CREATE_TEMPLATE", "support_ticket_agent")

    candidate_paths = [
        examples_dir / preferred,
        examples_dir / "support_ticket_agent",
        examples_dir / "customer_support_agent",
    ]

    for path in candidate_paths:
        if path.is_dir() and (path / "__main__.py").exists():
            return path

    if examples_dir.exists():
        for path in sorted(examples_dir.iterdir()):
            if path.is_dir() and (path / "__main__.py").exists():
                return path

    # Fallback: repository layouts can vary. Find any runnable template folder.
    fallback_candidates = []
    for main_file in root.rglob("__main__.py"):
        # Avoid using existing exports as templates.
        if "exports" in main_file.parts:
            continue
        parent = main_file.parent
        if (parent / "agent.json").exists():
            fallback_candidates.append(parent)

    if fallback_candidates:
        preferred_names = [
            preferred,
            "support_ticket_agent",
            "customer_support_agent",
            "faq_agent",
        ]
        by_name = {p.name: p for p in fallback_candidates}
        for name in preferred_names:
            if name in by_name:
                return by_name[name]
        return sorted(fallback_candidates)[0]

    raise HTTPException(
        500,
        (
            "No runnable HIVE template found. Expected a folder with __main__.py and agent.json "
            "under /app/examples (or elsewhere in repo). Set HIVE_CREATE_TEMPLATE to a valid folder name."
        ),
    )


def _extract_json_from_stdout(stdout: str) -> Any:
    text = stdout.strip()
    if not text:
        return {"raw_output": ""}

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue

    return {"raw_output": text}


def _looks_like_run_argument_error(stderr: str) -> bool:
    text = (stderr or "").lower()
    markers = [
        "no such option",
        "missing option",
        "missing argument",
        "got unexpected extra argument",
        "invalid value for",
    ]
    return any(marker in text for marker in markers)


def _build_run_arg_attempts(help_text: str, input_data: Dict[str, Any]) -> list[list[str]]:
    lowered = (help_text or "").lower()
    payload_json = json.dumps(input_data)
    attempts: list[list[str]] = []

    def add(args: list[str]) -> None:
        if args not in attempts:
            attempts.append(args)

    option_map = [
        ("--input", payload_json),
        ("--payload", payload_json),
        ("--data", payload_json),
        ("--json", payload_json),
        ("--task", str(input_data.get("task", "")) if "task" in input_data else ""),
        ("--query", str(input_data.get("query", "")) if "query" in input_data else ""),
        ("--question", str(input_data.get("question", "")) if "question" in input_data else ""),
        ("--prompt", str(input_data.get("prompt", "")) if "prompt" in input_data else ""),
        ("--text", str(input_data.get("text", "")) if "text" in input_data else ""),
    ]

    for opt, val in option_map:
        if val and opt in lowered:
            add(["run", opt, val])

    # Fallbacks when help output is unavailable/inconclusive or option probing still fails.
    add(["run", "--input", payload_json])
    add(["run", payload_json])
    if "task" in input_data:
        add(["run", str(input_data["task"])])
        add(["run", "--task", str(input_data["task"])])

    return attempts


def _run_hive_cli(agent_path: Path, input_data: Dict[str, Any], env: Dict[str, str], timeout_seconds: int) -> Any:
    payload_json = json.dumps(input_data)
    attempts: list[list[str]] = [
        ["uv", "run", "hive", "run", str(agent_path), "--input", payload_json],
        ["uv", "run", "hive", "run", str(agent_path), payload_json],
    ]
    if "task" in input_data:
        attempts.append(["uv", "run", "hive", "run", str(agent_path), "--task", str(input_data["task"])])

    last_error = ""
    for cmd in attempts:
        proc = subprocess.run(
            cmd,
            cwd=str(Path(__file__).parent),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if proc.returncode == 0:
            output_text = (proc.stdout or proc.stderr or "").strip()
            return _extract_json_from_stdout(output_text)

        err = (proc.stderr or proc.stdout or "").strip()
        last_error = err
        # Keep trying all known invocation shapes before failing.
        continue

    raise HTTPException(
        500,
        (
            f"HIVE orchestration run failed for '{agent_path.name}' via 'hive run'. "
            f"Last error: {last_error or 'unknown error'}"
        ),
    )


def _run_hive_orchestrated_agent(agent_name: str, input_data: Dict[str, Any]) -> Any:
    # Primary execution path: stable HIVE CLI for exported agents.
    agent_path = EXPORTS_DIR / agent_name
    timeout_seconds = int(os.getenv("HIVE_RUN_TIMEOUT_SECONDS", "300"))
    prefix = ["uv", "run", "python", "-m", agent_name]
    env = os.environ.copy()
    existing_path = env.get("PYTHONPATH", "")
    exports_path = str(EXPORTS_DIR)
    env["PYTHONPATH"] = f"{exports_path}{os.pathsep}{existing_path}" if existing_path else exports_path

    try:
        return _run_hive_cli(agent_path, input_data, env, timeout_seconds)
    except HTTPException:
        # Fall back to module-level run signatures for maximum compatibility.
        pass

    help_proc = subprocess.run(
        prefix + ["run", "--help"],
        cwd=str(Path(__file__).parent),
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )
    help_text = f"{help_proc.stdout}\n{help_proc.stderr}"
    attempts = _build_run_arg_attempts(help_text, input_data)

    last_error = ""
    for args in attempts:
        proc = subprocess.run(
            prefix + args,
            cwd=str(Path(__file__).parent),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if proc.returncode == 0:
            return _extract_json_from_stdout(proc.stdout)

        err = (proc.stderr or proc.stdout or "").strip()
        last_error = err

        # Keep trying all known invocation shapes before failing.
        continue

    raise HTTPException(
        500,
        (
            f"HIVE orchestration run failed for '{agent_name}' after trying multiple run argument formats. "
            f"Last error: {last_error or 'unknown error'}"
        ),
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
        "new_feature": "✨ Run exported HIVE agents via API!",
        "quick_test": {
            "curl": f'curl -X POST {domain}/agents/run/demo_agent -H "Content-Type: application/json" -d \'{{"task": "Hello!"}}\''
        },
        "create_agent": {
            "curl": f'curl -X POST {domain}/agents/create -H "Content-Type: application/json" -d \'{{"agent_name": "my_agent", "goal": "Analyze data"}}\''
        },
        "endpoints": {
            "health": "GET /health",
            "list_agents": "GET /agents",
            "create_agent": "POST /agents/create - runnable template clone",
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

        if not (agent_path / "__main__.py").exists():
            raise HTTPException(
                409,
                (
                    f"Agent '{agent_name}' is not a runnable HIVE export. "
                    "Deploy an exported HIVE agent package (must include __main__.py)."
                ),
            )

        return {
            "agent_name": agent_name,
            "status": "success",
            "output": _run_hive_orchestrated_agent(agent_name, input_data),
        }
        
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
    
    shutil.rmtree(agent_path)
    return {"status": "success", "message": f"Deleted {agent_name}"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
