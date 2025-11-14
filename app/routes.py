"""API routes for the application."""
import asyncio
import secrets
from typing import Optional, List
import json

from fastapi import APIRouter, HTTPException, Cookie, Header
from fastapi.responses import JSONResponse

from app.models import (
    LoginRequest,
    VMCreateRequest,
    VMActionRequest,
    AgentRegisterRequest,
    AgentInfo,
    AgentHeartbeat,
    VMInfoExtended
)
from app.auth import sessions, users, check_auth
from app.multipass import run_multipass_command, get_vm_ip
from app.agents import agent_registry
from app.remote_executor import get_executor_factory


# Create router
router = APIRouter()


# ==================== Authentication Routes ====================

@router.post("/api/auth/login")
async def login(req: LoginRequest):
    """Login endpoint."""
    if req.username in users and users[req.username] == req.password:
        # Create session
        session_id = secrets.token_urlsafe(32)
        sessions[session_id] = {"username": req.username}

        # Create response with cookie
        response = JSONResponse({"success": True, "message": "Login successful"})
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            samesite="lax",
            max_age=86400  # 24 hours
        )

        return response
    else:
        raise HTTPException(status_code=401, detail="Invalid credentials")


@router.post("/api/auth/logout")
async def logout(session_id: Optional[str] = Cookie(None)):
    """Logout endpoint."""
    if session_id and session_id in sessions:
        del sessions[session_id]

    response = JSONResponse({"success": True, "message": "Logged out"})
    response.delete_cookie("session_id")
    return response


@router.get("/api/auth/check")
async def check_auth_endpoint(session_id: Optional[str] = Cookie(None)):
    """Check if user is authenticated."""
    if check_auth(session_id):
        return JSONResponse({
            "authenticated": True,
            "username": sessions[session_id]["username"]
        })
    else:
        return JSONResponse({"authenticated": False})


# ==================== Agent Management Routes ====================

@router.post("/api/agent/register")
async def register_agent(req: AgentRegisterRequest, x_api_key: Optional[str] = Header(None)):
    """Register a new agent."""
    # Optional: Add authentication check here if needed
    agent_info = agent_registry.register_agent(req)
    return JSONResponse({
        "success": True,
        "message": f"Agent '{req.agent_id}' registered successfully",
        "agent": agent_info.model_dump(mode='json')
    })


@router.delete("/api/agent/unregister/{agent_id}")
async def unregister_agent(agent_id: str, session_id: Optional[str] = Cookie(None)):
    """Unregister an agent."""
    if not check_auth(session_id):
        raise HTTPException(status_code=401, detail="Not authenticated")

    success = agent_registry.unregister_agent(agent_id)
    if success:
        return JSONResponse({
            "success": True,
            "message": f"Agent '{agent_id}' unregistered successfully"
        })
    else:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")


@router.get("/api/agent/list")
async def list_agents(session_id: Optional[str] = Cookie(None)) -> List[AgentInfo]:
    """List all registered agents."""
    if not check_auth(session_id):
        raise HTTPException(status_code=401, detail="Not authenticated")

    agents = agent_registry.get_all_agents()
    return agents


@router.get("/api/agent/info/{agent_id}")
async def get_agent_info(agent_id: str, session_id: Optional[str] = Cookie(None)):
    """Get information about a specific agent."""
    if not check_auth(session_id):
        raise HTTPException(status_code=401, detail="Not authenticated")

    agent = agent_registry.get_agent(agent_id)
    if agent:
        return JSONResponse({
            "success": True,
            "agent": agent.model_dump(mode='json')
        })
    else:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")


@router.post("/api/agent/heartbeat")
async def agent_heartbeat(heartbeat: AgentHeartbeat, x_api_key: Optional[str] = Header(None)):
    """Receive heartbeat from an agent."""
    agent_registry.update_heartbeat(heartbeat)
    return JSONResponse({"success": True, "message": "Heartbeat received"})


# ==================== VM Management Routes ====================

@router.post("/api/vm/create")
async def create_vm(req: VMCreateRequest, session_id: Optional[str] = Cookie(None)):
    """Create a new multipass VM (local or remote)."""
    if not check_auth(session_id):
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Get the appropriate executor
    factory = get_executor_factory()
    executor = factory.get_executor(req.agent_id)

    # Create VM using executor
    result = await executor.create_vm(
        name=req.name,
        cpus=req.cpus,
        memory=req.memory,
        disk=req.disk,
        image=req.image
    )

    if result["success"]:
        # Wait a moment for VM to initialize
        await asyncio.sleep(2)

        # Get location info
        location = executor.get_location_info()

        return JSONResponse({
            "success": True,
            "message": result.get("message", f"VM '{req.name}' created successfully"),
            "vm_name": req.name,
            "agent_id": location["agent_id"],
            "agent_hostname": location["agent_hostname"]
        })
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to create VM"))


@router.get("/api/vm/list")
async def list_vms(session_id: Optional[str] = Cookie(None)):
    """List all multipass VMs (from local and all agents)."""
    if not check_auth(session_id):
        raise HTTPException(status_code=401, detail="Not authenticated")

    all_vms = []
    factory = get_executor_factory()

    # Get local VMs
    try:
        local_executor = factory.get_executor(None)
        result = await local_executor.list_vms()
        if result["success"]:
            for vm in result["data"].get("list", []):
                all_vms.append({
                    "name": vm.get("name"),
                    "state": vm.get("state"),
                    "ipv4": vm.get("ipv4", []),
                    "release": vm.get("release", ""),
                    "agent_id": None,
                    "agent_hostname": "local"
                })
    except Exception as e:
        # Log error but continue to check agents
        pass

    # Get VMs from all online agents
    agents = agent_registry.get_online_agents()
    for agent in agents:
        try:
            agent_executor = factory.get_executor(agent.agent_id)
            result = await agent_executor.list_vms()
            if result["success"]:
                for vm in result["data"].get("list", []):
                    all_vms.append({
                        "name": vm.get("name"),
                        "state": vm.get("state"),
                        "ipv4": vm.get("ipv4", []),
                        "release": vm.get("release", ""),
                        "agent_id": agent.agent_id,
                        "agent_hostname": agent.hostname
                    })
        except Exception as e:
            # Log error but continue with other agents
            pass

    return JSONResponse({"success": True, "vms": all_vms})


@router.get("/api/vm/info/{vm_name}")
async def get_vm_info(vm_name: str, session_id: Optional[str] = Cookie(None)):
    """Get detailed info about a specific VM."""
    if not check_auth(session_id):
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = run_multipass_command(["info", vm_name, "--format", "json"])

    if result["success"]:
        try:
            import json
            data = json.loads(result["output"])
            if vm_name in data.get("info", {}):
                return JSONResponse({"success": True, "info": data["info"][vm_name]})
            else:
                raise HTTPException(status_code=404, detail=f"VM '{vm_name}' not found")
        except json.JSONDecodeError:
            raise HTTPException(status_code=500, detail="Failed to parse multipass output")
    else:
        raise HTTPException(status_code=500, detail=result["error"])


@router.post("/api/vm/start")
async def start_vm(req: VMActionRequest, session_id: Optional[str] = Cookie(None)):
    """Start a stopped VM."""
    if not check_auth(session_id):
        raise HTTPException(status_code=401, detail="Not authenticated")

    factory = get_executor_factory()
    executor = factory.get_executor(req.agent_id)

    result = await executor.start_vm(req.name)

    if result["success"]:
        await asyncio.sleep(2)
        return JSONResponse({
            "success": True,
            "message": result.get("message", f"VM '{req.name}' started")
        })
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to start VM"))


@router.post("/api/vm/stop")
async def stop_vm(req: VMActionRequest, session_id: Optional[str] = Cookie(None)):
    """Stop a running VM."""
    if not check_auth(session_id):
        raise HTTPException(status_code=401, detail="Not authenticated")

    factory = get_executor_factory()
    executor = factory.get_executor(req.agent_id)

    result = await executor.stop_vm(req.name)

    if result["success"]:
        return JSONResponse({
            "success": True,
            "message": result.get("message", f"VM '{req.name}' stopped")
        })
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to stop VM"))


@router.post("/api/vm/delete")
async def delete_vm(req: VMActionRequest, session_id: Optional[str] = Cookie(None)):
    """Delete a VM."""
    if not check_auth(session_id):
        raise HTTPException(status_code=401, detail="Not authenticated")

    factory = get_executor_factory()
    executor = factory.get_executor(req.agent_id)

    result = await executor.delete_vm(req.name)

    if result["success"]:
        return JSONResponse({
            "success": True,
            "message": result.get("message", f"VM '{req.name}' deleted")
        })
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to delete VM"))
