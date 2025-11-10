# server.py
import asyncio
import json
import subprocess
from typing import List, Dict, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for API requests
class VMCreateRequest(BaseModel):
    name: str
    cpus: Optional[int] = 1
    memory: Optional[str] = "1G"
    disk: Optional[str] = "5G"
    image: Optional[str] = "22.04"  # Ubuntu version

class VMActionRequest(BaseModel):
    name: str

# Multipass helper functions
def run_multipass_command(args: List[str]) -> Dict:
    """Run a multipass command and return the result."""
    try:
        result = subprocess.run(
            ["multipass"] + args,
            capture_output=True,
            text=True,
            check=True
        )
        return {"success": True, "output": result.stdout, "error": ""}
    except subprocess.CalledProcessError as e:
        return {"success": False, "output": e.stdout, "error": e.stderr}
    except FileNotFoundError:
        return {"success": False, "output": "", "error": "multipass command not found. Is multipass installed?"}

def get_vm_ip(vm_name: str) -> Optional[str]:
    """Get the IP address of a multipass VM."""
    result = run_multipass_command(["info", vm_name, "--format", "json"])
    if result["success"]:
        try:
            info = json.loads(result["output"])
            if vm_name in info["info"]:
                ipv4_list = info["info"][vm_name].get("ipv4", [])
                if ipv4_list:
                    return ipv4_list[0]
        except (json.JSONDecodeError, KeyError):
            pass
    return None

# Multipass VM management endpoints
@app.post("/api/vm/create")
async def create_vm(req: VMCreateRequest):
    """Create a new multipass VM."""
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

@app.get("/api/vm/list")
async def list_vms():
    """List all multipass VMs."""
    result = run_multipass_command(["list", "--format", "json"])

    if result["success"]:
        try:
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

@app.get("/api/vm/info/{vm_name}")
async def get_vm_info(vm_name: str):
    """Get detailed info about a specific VM."""
    result = run_multipass_command(["info", vm_name, "--format", "json"])

    if result["success"]:
        try:
            data = json.loads(result["output"])
            if vm_name in data.get("info", {}):
                return JSONResponse({"success": True, "info": data["info"][vm_name]})
            else:
                raise HTTPException(status_code=404, detail=f"VM '{vm_name}' not found")
        except json.JSONDecodeError:
            raise HTTPException(status_code=500, detail="Failed to parse multipass output")
    else:
        raise HTTPException(status_code=500, detail=result["error"])

@app.post("/api/vm/start")
async def start_vm(req: VMActionRequest):
    """Start a stopped VM."""
    result = run_multipass_command(["start", req.name])

    if result["success"]:
        await asyncio.sleep(2)
        ip = get_vm_ip(req.name)
        return JSONResponse({"success": True, "message": f"VM '{req.name}' started", "ip": ip})
    else:
        raise HTTPException(status_code=500, detail=result["error"])

@app.post("/api/vm/stop")
async def stop_vm(req: VMActionRequest):
    """Stop a running VM."""
    result = run_multipass_command(["stop", req.name])

    if result["success"]:
        return JSONResponse({"success": True, "message": f"VM '{req.name}' stopped"})
    else:
        raise HTTPException(status_code=500, detail=result["error"])

@app.post("/api/vm/delete")
async def delete_vm(req: VMActionRequest):
    """Delete a VM."""
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

# basic page to test quickly
@app.get("/")
def index():
    return HTMLResponse("""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Multipass VM Manager</title>
    <link href="https://unpkg.com/xterm@5.5.0/css/xterm.css" rel="stylesheet" />
    <style>
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body { font-family: system-ui, -apple-system, sans-serif; background: #1a1a1a; color: #e0e0e0; }

      .container { display: flex; height: 100vh; }
      .sidebar { width: 350px; background: #252525; border-right: 1px solid #333; display: flex; flex-direction: column; overflow: hidden; }
      .main { flex: 1; display: flex; flex-direction: column; }

      .header { padding: 20px; border-bottom: 1px solid #333; }
      .header h1 { font-size: 20px; margin-bottom: 5px; }
      .header p { font-size: 12px; color: #888; }

      .section { padding: 15px; border-bottom: 1px solid #333; }
      .section h2 { font-size: 14px; margin-bottom: 10px; color: #aaa; text-transform: uppercase; }

      .form-group { margin-bottom: 10px; }
      .form-group label { display: block; font-size: 12px; margin-bottom: 4px; color: #aaa; }
      .form-group input, .form-group select { width: 100%; padding: 8px; background: #333; border: 1px solid #444; color: #e0e0e0; border-radius: 4px; font-size: 13px; }
      .form-group input:focus { outline: none; border-color: #4a9eff; }

      .btn { padding: 8px 12px; background: #4a9eff; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; font-weight: 500; }
      .btn:hover { background: #3a8eef; }
      .btn:disabled { background: #555; cursor: not-allowed; }
      .btn-sm { padding: 5px 8px; font-size: 11px; }
      .btn-danger { background: #e74c3c; }
      .btn-danger:hover { background: #c0392b; }
      .btn-success { background: #27ae60; }
      .btn-success:hover { background: #229954; }
      .btn-warning { background: #f39c12; }
      .btn-warning:hover { background: #d68910; }

      .vm-list { flex: 1; overflow-y: auto; padding: 15px; }
      .vm-item { background: #2a2a2a; padding: 12px; margin-bottom: 10px; border-radius: 6px; border: 1px solid #333; }
      .vm-item-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
      .vm-name { font-weight: 600; font-size: 14px; }
      .vm-state { font-size: 11px; padding: 3px 8px; border-radius: 3px; text-transform: uppercase; }
      .vm-state.running { background: #27ae60; color: white; }
      .vm-state.stopped { background: #95a5a6; color: white; }
      .vm-info { font-size: 12px; color: #888; margin-bottom: 8px; }
      .vm-actions { display: flex; gap: 5px; flex-wrap: wrap; }

      #term { flex: 1; display: none; padding: 10px; }
      #term.active { display: block; }

      .status { padding: 10px 15px; background: #2a2a2a; border-bottom: 1px solid #333; font-size: 12px; color: #888; }
      .status.connected { color: #27ae60; }
      .status.error { color: #e74c3c; }

      .loading { color: #4a9eff; font-size: 12px; margin-top: 5px; }
    </style>
  </head>
  <body>
    <div class="container">
      <div class="sidebar">
        <div class="header">
          <h1>Multipass VMs</h1>
          <p>Manage and connect to VMs</p>
        </div>

        <div class="section">
          <h2>Create New VM</h2>
          <form id="createForm">
            <div class="form-group">
              <label>Name</label>
              <input type="text" id="vmName" placeholder="my-vm" required />
            </div>
            <div class="form-group">
              <label>Ubuntu Version</label>
              <select id="vmImage">
                <option value="22.04">Ubuntu 22.04 LTS</option>
                <option value="24.04">Ubuntu 24.04 LTS</option>
                <option value="20.04">Ubuntu 20.04 LTS</option>
              </select>
            </div>
            <div class="form-group">
              <label>CPUs</label>
              <input type="number" id="vmCpus" value="2" min="1" max="8" />
            </div>
            <div class="form-group">
              <label>Memory</label>
              <input type="text" id="vmMemory" value="2G" placeholder="2G" />
            </div>
            <div class="form-group">
              <label>Disk</label>
              <input type="text" id="vmDisk" value="10G" placeholder="10G" />
            </div>
            <button type="submit" class="btn" style="width:100%">Create VM</button>
          </form>
          <div id="createStatus"></div>
        </div>

        <div class="vm-list" id="vmList">
          <div class="loading">Loading VMs...</div>
        </div>
      </div>

      <div class="main">
        <div id="status" class="status">Not connected</div>
        <div id="term"></div>
      </div>
    </div>

    <script type="module">
      import { Terminal } from 'https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/+esm';
      import { FitAddon } from 'https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0/+esm';

      // Import CSS
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = 'https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/css/xterm.css';
      document.head.appendChild(link);

      let ws = null;
      let term = null;
      let fit = null;

      // Initialize terminal
      window.initTerminal = function(vmName) {
        console.log('Connecting to VM:', vmName);

        if (ws) {
          ws.close();
        }

        const termEl = document.getElementById('term');
        termEl.innerHTML = '';
        termEl.classList.add('active');

        term = new Terminal({cursorBlink: true, fontFamily: 'monospace', fontSize: 14});
        fit = new FitAddon();
        term.loadAddon(fit);
        term.open(termEl);
        fit.fit();

        updateStatus('Connecting to ' + vmName + '...', false);

        const wsUrl = `ws://${location.host}/ws?vm_name=${vmName}`;
        console.log('WebSocket URL:', wsUrl);

        ws = new WebSocket(wsUrl);
        ws.binaryType = "arraybuffer";

        ws.onopen = () => {
          console.log('WebSocket connected');
          updateStatus('Connected to ' + vmName, true);
          const sendResize = () => {
            const cols = term.cols, rows = term.rows;
            console.log('Sending resize:', cols, 'x', rows);
            ws.send(JSON.stringify({type: "resize", cols, rows}));
          };
          sendResize();
          window.addEventListener('resize', () => { fit.fit(); sendResize(); });
        };

        ws.onmessage = (e) => {
          console.log('Received data:', e.data.byteLength || e.data.length, 'bytes');
          if (e.data instanceof ArrayBuffer) term.write(new Uint8Array(e.data));
          else term.write(e.data);
        };

        ws.onerror = (e) => {
          console.error('WebSocket error:', e);
          updateStatus('Connection error', false, true);
        };

        ws.onclose = (e) => {
          console.log('WebSocket closed:', e.code, e.reason);
          updateStatus('Disconnected', false);
        };

        term.onData(data => {
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(data);
          }
        });
      }

      function updateStatus(msg, connected, error = false) {
        const status = document.getElementById('status');
        status.textContent = msg;
        status.className = 'status';
        if (connected) status.classList.add('connected');
        if (error) status.classList.add('error');
      }

      window.updateStatus = updateStatus;

      // Load VMs
      window.loadVMs = async function() {
        try {
          const res = await fetch('/api/vm/list');
          const data = await res.json();

          const vmList = document.getElementById('vmList');

          if (data.vms.length === 0) {
            vmList.innerHTML = '<div style="color:#888;font-size:12px;text-align:center;padding:20px;">No VMs found. Create one above.</div>';
            return;
          }

          vmList.innerHTML = data.vms.map(vm => {
            const ip = vm.ipv4.length > 0 ? vm.ipv4[0] : 'No IP';
            const isRunning = vm.state === 'Running';

            return `
              <div class="vm-item">
                <div class="vm-item-header">
                  <span class="vm-name">${vm.name}</span>
                  <span class="vm-state ${vm.state.toLowerCase()}">${vm.state}</span>
                </div>
                <div class="vm-info">
                  IP: ${ip}<br/>
                  Release: ${vm.release || 'N/A'}
                </div>
                <div class="vm-actions">
                  ${isRunning ?
                    `<button class="btn btn-sm btn-success" onclick="connectToVM('${vm.name}')">Connect</button>
                     <button class="btn btn-sm btn-warning" onclick="stopVM('${vm.name}')">Stop</button>` :
                    `<button class="btn btn-sm" onclick="startVM('${vm.name}')">Start</button>`
                  }
                  <button class="btn btn-sm btn-danger" onclick="deleteVM('${vm.name}')">Delete</button>
                </div>
              </div>
            `;
          }).join('');
        } catch (err) {
          document.getElementById('vmList').innerHTML = '<div style="color:#e74c3c;font-size:12px;padding:15px;">Error loading VMs: ' + err.message + '</div>';
        }
      }

      // Create VM
      document.getElementById('createForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = e.target.querySelector('button');
        const status = document.getElementById('createStatus');

        btn.disabled = true;
        status.innerHTML = '<div class="loading">Creating VM...</div>';

        try {
          const res = await fetch('/api/vm/create', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              name: document.getElementById('vmName').value,
              image: document.getElementById('vmImage').value,
              cpus: parseInt(document.getElementById('vmCpus').value),
              memory: document.getElementById('vmMemory').value,
              disk: document.getElementById('vmDisk').value
            })
          });

          const data = await res.json();

          if (res.ok) {
            status.innerHTML = '<div style="color:#27ae60;font-size:12px;margin-top:5px;">VM created successfully!</div>';
            e.target.reset();
            setTimeout(() => { status.innerHTML = ''; window.loadVMs(); }, 2000);
          } else {
            status.innerHTML = '<div style="color:#e74c3c;font-size:12px;margin-top:5px;">Error: ' + data.detail + '</div>';
          }
        } catch (err) {
          status.innerHTML = '<div style="color:#e74c3c;font-size:12px;margin-top:5px;">Error: ' + err.message + '</div>';
        } finally {
          btn.disabled = false;
        }
      });

      // VM Actions
      window.startVM = async function(name) {
        try {
          const res = await fetch('/api/vm/start', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name})
          });
          if (res.ok) {
            setTimeout(window.loadVMs, 2000);
          }
        } catch (err) {
          alert('Error starting VM: ' + err.message);
        }
      }

      window.stopVM = async function(name) {
        try {
          const res = await fetch('/api/vm/stop', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name})
          });
          if (res.ok) {
            window.loadVMs();
          }
        } catch (err) {
          alert('Error stopping VM: ' + err.message);
        }
      }

      window.deleteVM = async function(name) {
        if (!confirm(`Delete VM "${name}"? This cannot be undone.`)) return;

        try {
          const res = await fetch('/api/vm/delete', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name})
          });
          if (res.ok) {
            window.loadVMs();
          }
        } catch (err) {
          alert('Error deleting VM: ' + err.message);
        }
      }

      window.connectToVM = function(vmName) {
        window.initTerminal(vmName);
      }

      // Load VMs on page load
      window.loadVMs();

      // Refresh VM list every 10 seconds
      setInterval(window.loadVMs, 10000);
    </script>
  </body>
</html>""")

@app.websocket("/ws")
async def ws_shell(ws: WebSocket):
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

    import os
    import pty
    import select
    import termios
    import struct
    import fcntl

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
            """Read from PTY and forward to websocket"""
            loop = asyncio.get_event_loop()
            while True:
                try:
                    # Wait for data to be available
                    await loop.run_in_executor(None, lambda: select.select([master_fd], [], [], 0.1))

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
                except Exception as e:
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
