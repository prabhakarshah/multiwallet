"""API routes for the application."""
import asyncio
import secrets
from typing import Optional

from fastapi import APIRouter, HTTPException, Cookie
from fastapi.responses import JSONResponse

from app.models import LoginRequest, VMCreateRequest, VMActionRequest
from app.auth import sessions, users, check_auth
from app.multipass import run_multipass_command, get_vm_ip


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


# ==================== VM Management Routes ====================

@router.post("/api/vm/create")
async def create_vm(req: VMCreateRequest, session_id: Optional[str] = Cookie(None)):
    """Create a new multipass VM."""
    if not check_auth(session_id):
        raise HTTPException(status_code=401, detail="Not authenticated")

    args = [
        "launch",
        req.image,
        "--name", req.name,
        "--cpus", str(req.cpus),
        "--memory", req.memory,
        "--disk", req.disk
    ]

    result = run_multipass_command(args)

    if result["success"]:
        # Wait a moment for VM to get IP
        await asyncio.sleep(2)

        ip = get_vm_ip(req.name)
        return JSONResponse({
            "success": True,
            "message": f"VM '{req.name}' created successfully",
            "vm_name": req.name,
            "ip": ip
        })
    else:
        raise HTTPException(status_code=500, detail=result["error"])


@router.get("/api/vm/list")
async def list_vms(session_id: Optional[str] = Cookie(None)):
    """List all multipass VMs."""
    if not check_auth(session_id):
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = run_multipass_command(["list", "--format", "json"])

    if result["success"]:
        try:
            import json
            data = json.loads(result["output"])
            vms = []
            for vm in data.get("list", []):
                vms.append({
                    "name": vm.get("name"),
                    "state": vm.get("state"),
                    "ipv4": vm.get("ipv4", []),
                    "release": vm.get("release", "")
                })
            return JSONResponse({"success": True, "vms": vms})
        except json.JSONDecodeError:
            raise HTTPException(status_code=500, detail="Failed to parse multipass output")
    else:
        raise HTTPException(status_code=500, detail=result["error"])


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

    result = run_multipass_command(["start", req.name])

    if result["success"]:
        await asyncio.sleep(2)
        ip = get_vm_ip(req.name)
        return JSONResponse({
            "success": True,
            "message": f"VM '{req.name}' started",
            "ip": ip
        })
    else:
        raise HTTPException(status_code=500, detail=result["error"])


@router.post("/api/vm/stop")
async def stop_vm(req: VMActionRequest, session_id: Optional[str] = Cookie(None)):
    """Stop a running VM."""
    if not check_auth(session_id):
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = run_multipass_command(["stop", req.name])

    if result["success"]:
        return JSONResponse({"success": True, "message": f"VM '{req.name}' stopped"})
    else:
        raise HTTPException(status_code=500, detail=result["error"])


@router.post("/api/vm/delete")
async def delete_vm(req: VMActionRequest, session_id: Optional[str] = Cookie(None)):
    """Delete a VM."""
    if not check_auth(session_id):
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Stop the VM first
    run_multipass_command(["stop", req.name])
    # Delete it
    result = run_multipass_command(["delete", req.name])

    if result["success"]:
        # Purge to completely remove
        run_multipass_command(["purge"])
        return JSONResponse({"success": True, "message": f"VM '{req.name}' deleted"})
    else:
        raise HTTPException(status_code=500, detail=result["error"])
