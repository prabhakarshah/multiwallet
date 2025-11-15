"""WebSocket handler for terminal connections."""
import asyncio
import json
import os
import pty
import select
import subprocess
import struct
import fcntl
import termios
import logging
import httpx

from fastapi import WebSocket, WebSocketDisconnect
from app.agents import agent_registry

logger = logging.getLogger(__name__)


async def handle_terminal_connection(ws: WebSocket):
    """Handle WebSocket connection for terminal access to a VM."""
    await ws.accept()

    # Get VM name and agent_id from query params
    params = ws.query_params
    vm_name = params.get("vm_name")
    agent_id = params.get("agent_id")

    logger.info(f"[WebSocket] Connection request for VM: {vm_name} on agent: {agent_id or 'local'}")

    if not vm_name:
        logger.error("[WebSocket] Error: No VM name provided")
        await ws.send_text("Error: VM name is required\r\n")
        await ws.close()
        return

    # Route to appropriate handler based on agent_id
    if agent_id:
        await handle_remote_terminal(ws, vm_name, agent_id)
    else:
        await handle_local_terminal(ws, vm_name)


async def handle_remote_terminal(ws: WebSocket, vm_name: str, agent_id: str):
    """Handle terminal connection to a remote VM via agent."""
    agent = agent_registry.get_agent(agent_id)
    if not agent:
        await ws.send_text(f"Error: Agent '{agent_id}' not found\r\n")
        await ws.close()
        return

    if agent.status != "online":
        await ws.send_text(f"Error: Agent '{agent_id}' is offline\r\n")
        await ws.close()
        return

    # Build websocket URL for agent
    agent_ws_url = agent.api_url.replace("http://", "ws://").replace("https://", "wss://")
    agent_ws_url = f"{agent_ws_url}/ws?vm_name={vm_name}"

    # Add API key header if needed
    headers = {}
    api_key = agent_registry.get_agent_api_key(agent_id)
    if api_key:
        headers["X-API-Key"] = api_key

    remote_ws = None
    try:
        logger.info(f"[WebSocket] Connecting to remote agent websocket: {agent_ws_url}")

        # Connect to remote agent's websocket
        async with httpx.AsyncClient() as client:
            # Use websockets library for cleaner websocket client handling
            import websockets

            remote_ws = await websockets.connect(
                agent_ws_url,
                additional_headers=headers if headers else None
            )

            # Create bidirectional proxy
            async def forward_to_remote():
                """Forward messages from client to remote agent."""
                try:
                    while True:
                        msg = await ws.receive_text()
                        await remote_ws.send(msg)
                except Exception as e:
                    logger.debug(f"Forward to remote ended: {e}")

            async def forward_from_remote():
                """Forward messages from remote agent to client."""
                try:
                    async for msg in remote_ws:
                        if isinstance(msg, bytes):
                            await ws.send_bytes(msg)
                        else:
                            await ws.send_text(msg)
                except Exception as e:
                    logger.debug(f"Forward from remote ended: {e}")

            # Run both forward tasks concurrently
            await asyncio.gather(
                forward_to_remote(),
                forward_from_remote(),
                return_exceptions=True
            )

    except Exception as e:
        logger.error(f"[WebSocket] Error connecting to remote agent: {e}")
        try:
            await ws.send_text(f"\r\n[Connection Error] {str(e)}\r\n")
        except:
            pass
    finally:
        if remote_ws:
            try:
                await remote_ws.close()
            except:
                pass
        try:
            await ws.close()
        except:
            pass


async def handle_local_terminal(ws: WebSocket, vm_name: str):
    """Handle terminal connection to a local VM."""
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
                            await ws.send_bytes(data)
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
            msg = await ws.receive_text()

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
        try:
            error_msg = f"\r\n[Connection Error] {str(e)}\r\n"
            error_msg += f"Make sure the VM '{vm_name}' is running.\r\n"
            await ws.send_text(error_msg)
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
