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

from fastapi import WebSocket, WebSocketDisconnect


async def handle_terminal_connection(ws: WebSocket):
    """Handle WebSocket connection for terminal access to a VM."""
    await ws.accept()

    # Get VM name from query params
    params = ws.query_params
    vm_name = params.get("vm_name")

    print(f"[WebSocket] Connection request for VM: {vm_name}")

    if not vm_name:
        print("[WebSocket] Error: No VM name provided")
        await ws.send_text("Error: VM name is required\r\n")
        await ws.close()
        return

    master_fd = None
    proc = None
    read_task = None

    try:
        print(f"[WebSocket] Creating PTY for {vm_name}")
        # Create a pseudo-terminal
        master_fd, slave_fd = pty.openpty()

        # Start multipass shell with PTY
        print(f"[WebSocket] Starting multipass shell for {vm_name}")
        proc = subprocess.Popen(
            ["multipass", "shell", vm_name],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            preexec_fn=os.setsid,
            close_fds=True
        )

        print(f"[WebSocket] Process started with PID: {proc.pid}")

        # Close slave fd in parent process
        os.close(slave_fd)

        # Make master_fd non-blocking
        flag = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flag | os.O_NONBLOCK)

        print(f"[WebSocket] PTY configured, starting read loop")

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
