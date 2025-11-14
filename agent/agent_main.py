"""Agent server for remote multipass management.

This server runs on remote machines and exposes a REST API for the master
server to manage multipass VMs remotely.

Usage:
    python -m agent.agent_main --agent-id AGENT_ID --api-key API_KEY [--port PORT]
"""
import asyncio
import argparse
import logging
import socket
import os
import pty
import select
import subprocess
import struct
import fcntl
import termios
from datetime import datetime
from typing import Optional
import httpx
from fastapi import FastAPI, HTTPException, Header, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json

# Import models from parent app
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from app.models import (
    RemoteCommandRequest,
    RemoteCommandResponse,
    VMCreateRequest,
    VMActionRequest,
    AgentHeartbeat,
    AgentRegisterRequest
)
from agent.agent_executor import AgentExecutor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global configuration
CONFIG = {
    "agent_id": None,
    "api_key": None,
    "master_url": None,
    "heartbeat_interval": 30,  # seconds
    "port": 8001
}

# Initialize FastAPI app
app = FastAPI(title="Batwa Agent", description="Remote Multipass Agent")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize executor
executor = AgentExecutor()

# Heartbeat task
heartbeat_task: Optional[asyncio.Task] = None


async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Verify API key from request header."""
    if CONFIG["api_key"] is None:
        # No API key configured, allow all requests
        return True

    if x_api_key is None or x_api_key != CONFIG["api_key"]:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return True


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "agent_id": CONFIG["agent_id"],
        "timestamp": datetime.now().isoformat()
    }


@app.post("/api/execute")
async def execute_command(
    request: RemoteCommandRequest,
    _: bool = Depends(verify_api_key)
) -> RemoteCommandResponse:
    """Execute a remote command.

    This is a generic command execution endpoint that can be used
    for custom operations beyond the standard VM management.
    """
    try:
        result = executor.run_multipass_command(request.args)
        return RemoteCommandResponse(
            success=result["success"],
            stdout=result["output"],
            stderr=result["error"],
            return_code=0 if result["success"] else 1
        )
    except Exception as e:
        logger.error(f"Error executing command: {e}")
        return RemoteCommandResponse(
            success=False,
            return_code=-1,
            error=str(e)
        )


@app.get("/api/vm/list")
async def list_vms(_: bool = Depends(verify_api_key)):
    """List all VMs on this agent."""
    try:
        result = executor.list_vms()
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result
    except Exception as e:
        logger.error(f"Error listing VMs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/vm/info/{vm_name}")
async def get_vm_info(vm_name: str, _: bool = Depends(verify_api_key)):
    """Get information about a specific VM."""
    try:
        result = executor.get_vm_info(vm_name)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except Exception as e:
        logger.error(f"Error getting VM info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/vm/create")
async def create_vm(
    request: VMCreateRequest,
    _: bool = Depends(verify_api_key)
):
    """Create a new VM on this agent."""
    try:
        result = executor.create_vm(
            name=request.name,
            cpus=request.cpus,
            memory=request.memory,
            disk=request.disk,
            image=request.image
        )
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])
        return result
    except Exception as e:
        logger.error(f"Error creating VM: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/vm/start")
async def start_vm(
    request: VMActionRequest,
    _: bool = Depends(verify_api_key)
):
    """Start a VM on this agent."""
    try:
        result = executor.start_vm(request.name)
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])
        return result
    except Exception as e:
        logger.error(f"Error starting VM: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/vm/stop")
async def stop_vm(
    request: VMActionRequest,
    _: bool = Depends(verify_api_key)
):
    """Stop a VM on this agent."""
    try:
        result = executor.stop_vm(request.name)
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])
        return result
    except Exception as e:
        logger.error(f"Error stopping VM: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/vm/delete")
async def delete_vm(
    request: VMActionRequest,
    _: bool = Depends(verify_api_key)
):
    """Delete a VM on this agent."""
    try:
        result = executor.delete_vm(request.name)
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])
        return result
    except Exception as e:
        logger.error(f"Error deleting VM: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws")
async def websocket_terminal(websocket: WebSocket):
    """WebSocket endpoint for terminal connections to VMs."""
    await websocket.accept()

    # Get VM name from query params
    params = websocket.query_params
    vm_name = params.get("vm_name")

    logger.info(f"[WebSocket] Connection request for VM: {vm_name}")

    if not vm_name:
        logger.error("[WebSocket] Error: No VM name provided")
        await websocket.send_text("Error: VM name is required\r\n")
        await websocket.close()
        return

    master_fd = None
    proc = None
    read_task = None

    try:
        logger.info(f"[WebSocket] Creating PTY for {vm_name}")
        # Create a pseudo-terminal
        master_fd, slave_fd = pty.openpty()

        # Start multipass shell with PTY
        logger.info(f"[WebSocket] Starting multipass shell for {vm_name}")
        proc = subprocess.Popen(
            ["multipass", "shell", vm_name],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            preexec_fn=os.setsid,
            close_fds=True
        )

        logger.info(f"[WebSocket] Process started with PID: {proc.pid}")

        # Close slave fd in parent process
        os.close(slave_fd)

        # Make master_fd non-blocking
        flag = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flag | os.O_NONBLOCK)

        logger.info(f"[WebSocket] PTY configured, starting read loop")

        async def read_and_forward():
            """Read from PTY and forward to websocket."""
            loop = asyncio.get_event_loop()
            while True:
                try:
                    # Wait for data to be available
                    await loop.run_in_executor(
                        None,
                        lambda: select.select([master_fd], [], [], 0.1)
                    )

                    # Read available data
                    try:
                        data = os.read(master_fd, 4096)
                        if data:
                            await websocket.send_bytes(data)
                        else:
                            break
                    except OSError:
                        # No data available yet
                        await asyncio.sleep(0.01)
                except Exception:
                    break

        # Start reading task
        read_task = asyncio.create_task(read_and_forward())

        # Handle incoming websocket messages
        while True:
            msg = await websocket.receive_text()

            # Check if it's a resize command
            try:
                obj = json.loads(msg)
                if obj.get("type") == "resize":
                    cols = int(obj["cols"])
                    rows = int(obj["rows"])
                    # Set terminal size
                    winsize = struct.pack("HHHH", rows, cols, 0, 0)
                    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
                    continue
            except Exception:
                pass

            # Send keystrokes to the shell
            try:
                os.write(master_fd, msg.encode())
            except OSError:
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"[WebSocket] Error: {e}")
        try:
            error_msg = f"\r\n[Connection Error] {str(e)}\r\n"
            error_msg += f"Make sure the VM '{vm_name}' is running.\r\n"
            await websocket.send_text(error_msg)
        except Exception:
            pass
    finally:
        # Cleanup
        if read_task:
            read_task.cancel()
        if master_fd:
            try:
                os.close(master_fd)
            except Exception:
                pass
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


async def send_heartbeat():
    """Send heartbeat to master server."""
    if CONFIG["master_url"] is None:
        logger.warning("Master URL not configured, skipping heartbeat")
        return

    try:
        # Get VM count
        vm_list = executor.list_vms()
        vm_count = 0
        if "list" in vm_list:
            vm_count = len(vm_list["list"])

        heartbeat = AgentHeartbeat(
            agent_id=CONFIG["agent_id"],
            timestamp=datetime.now(),
            status="online",
            vm_count=vm_count
        )

        async with httpx.AsyncClient() as client:
            headers = {}
            if CONFIG["api_key"]:
                headers["X-API-Key"] = CONFIG["api_key"]

            response = await client.post(
                f"{CONFIG['master_url']}/api/agent/heartbeat",
                json=heartbeat.model_dump(mode='json'),
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            logger.debug("Heartbeat sent successfully")

    except Exception as e:
        logger.error(f"Error sending heartbeat: {e}")


async def heartbeat_loop():
    """Periodic heartbeat loop."""
    while True:
        try:
            await asyncio.sleep(CONFIG["heartbeat_interval"])
            await send_heartbeat()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in heartbeat loop: {e}")


async def register_with_master():
    """Register this agent with the master server."""
    if CONFIG["master_url"] is None:
        logger.warning("Master URL not configured, skipping registration")
        return

    try:
        hostname = socket.gethostname()
        port = CONFIG["port"]
        # Try to determine the actual IP address
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        except Exception:
            local_ip = "127.0.0.1"
        finally:
            s.close()

        api_url = f"http://{local_ip}:{port}"

        registration = AgentRegisterRequest(
            agent_id=CONFIG["agent_id"],
            hostname=hostname,
            api_url=api_url,
            api_key=CONFIG["api_key"]
        )

        async with httpx.AsyncClient() as client:
            headers = {}
            if CONFIG["api_key"]:
                headers["X-API-Key"] = CONFIG["api_key"]

            response = await client.post(
                f"{CONFIG['master_url']}/api/agent/register",
                json=registration.model_dump(),
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"Successfully registered with master at {CONFIG['master_url']}")

    except Exception as e:
        logger.error(f"Error registering with master: {e}")


@app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    global heartbeat_task

    logger.info(f"Starting agent: {CONFIG['agent_id']}")
    logger.info(f"API key configured: {CONFIG['api_key'] is not None}")
    logger.info(f"Master URL: {CONFIG['master_url']}")

    # Register with master if configured
    if CONFIG["master_url"]:
        await register_with_master()

        # Start heartbeat loop
        heartbeat_task = asyncio.create_task(heartbeat_loop())
        logger.info("Started heartbeat task")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    global heartbeat_task

    logger.info("Shutting down agent")

    # Cancel heartbeat task
    if heartbeat_task and not heartbeat_task.done():
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass


def main():
    """Main entry point for agent server."""
    parser = argparse.ArgumentParser(description="Batwa Agent Server")
    parser.add_argument(
        "--agent-id",
        required=True,
        help="Unique identifier for this agent"
    )
    parser.add_argument(
        "--api-key",
        help="API key for authentication (optional)"
    )
    parser.add_argument(
        "--master-url",
        help="URL of the master server (e.g., http://master:8000)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port to listen on (default: 8001)"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=int,
        default=30,
        help="Heartbeat interval in seconds (default: 30)"
    )

    args = parser.parse_args()

    # Update global config
    CONFIG["agent_id"] = args.agent_id
    CONFIG["api_key"] = args.api_key
    CONFIG["master_url"] = args.master_url.rstrip('/') if args.master_url else None
    CONFIG["port"] = args.port
    CONFIG["heartbeat_interval"] = args.heartbeat_interval

    # Start server
    logger.info(f"Starting agent server on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
