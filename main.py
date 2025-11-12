# server.py
import asyncio
import json
import subprocess
import secrets
from typing import List, Dict, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Cookie, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
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

# Simple session storage (in production, use Redis or a database)
sessions = {}

# Simple user storage (in production, use a database with hashed passwords)
users = {
    "admin": "admin123"  # username: password
}

# Pydantic models for API requests
class LoginRequest(BaseModel):
    username: str
    password: str

class VMCreateRequest(BaseModel):
    name: str
    cpus: Optional[int] = 1
    memory: Optional[str] = "1G"
    disk: Optional[str] = "5G"
    image: Optional[str] = "22.04"  # Ubuntu version

class VMActionRequest(BaseModel):
    name: str

# Helper function to check authentication
def check_auth(session_id: Optional[str]) -> bool:
    if not session_id:
        return False
    return session_id in sessions

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

# Authentication endpoints
@app.post("/api/auth/login")
async def login(req: LoginRequest):
    """Login endpoint"""
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

@app.post("/api/auth/logout")
async def logout(session_id: Optional[str] = Cookie(None)):
    """Logout endpoint"""
    if session_id and session_id in sessions:
        del sessions[session_id]

    response = JSONResponse({"success": True, "message": "Logged out"})
    response.delete_cookie("session_id")
    return response

@app.get("/api/auth/check")
async def check_auth_endpoint(session_id: Optional[str] = Cookie(None)):
    """Check if user is authenticated"""
    if check_auth(session_id):
        return JSONResponse({"authenticated": True, "username": sessions[session_id]["username"]})
    else:
        return JSONResponse({"authenticated": False})

# Multipass VM management endpoints
@app.post("/api/vm/create")
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

@app.get("/api/vm/list")
async def list_vms(session_id: Optional[str] = Cookie(None)):
    """List all multipass VMs."""
    if not check_auth(session_id):
        raise HTTPException(status_code=401, detail="Not authenticated")
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
async def get_vm_info(vm_name: str, session_id: Optional[str] = Cookie(None)):
    """Get detailed info about a specific VM."""
    if not check_auth(session_id):
        raise HTTPException(status_code=401, detail="Not authenticated")
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
async def start_vm(req: VMActionRequest, session_id: Optional[str] = Cookie(None)):
    """Start a stopped VM."""
    if not check_auth(session_id):
        raise HTTPException(status_code=401, detail="Not authenticated")
    result = run_multipass_command(["start", req.name])

    if result["success"]:
        await asyncio.sleep(2)
        ip = get_vm_ip(req.name)
        return JSONResponse({"success": True, "message": f"VM '{req.name}' started", "ip": ip})
    else:
        raise HTTPException(status_code=500, detail=result["error"])

@app.post("/api/vm/stop")
async def stop_vm(req: VMActionRequest, session_id: Optional[str] = Cookie(None)):
    """Stop a running VM."""
    if not check_auth(session_id):
        raise HTTPException(status_code=401, detail="Not authenticated")
    result = run_multipass_command(["stop", req.name])

    if result["success"]:
        return JSONResponse({"success": True, "message": f"VM '{req.name}' stopped"})
    else:
        raise HTTPException(status_code=500, detail=result["error"])

@app.post("/api/vm/delete")
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

# Main application page
@app.get("/")
async def index(session_id: Optional[str] = Cookie(None)):
    # Check authentication
    if not check_auth(session_id):
        return RedirectResponse(url="/login")

    return HTMLResponse("""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Multipass VM Manager</title>
    <style>
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body { font-family: system-ui, -apple-system, sans-serif; background: #1a1a1a; color: #e0e0e0; overflow: hidden; }

      /* Menu bar */
      .menubar { background: #2a2a2a; border-bottom: 1px solid #444; padding: 0 15px; display: flex; align-items: center; justify-content: space-between; height: 40px; }
      .menu { display: flex; gap: 5px; }
      .menu-item { padding: 8px 12px; cursor: pointer; font-size: 13px; border-radius: 4px; }
      .menu-item:hover { background: #3a3a3a; }
      .user-info { font-size: 12px; color: #888; display: flex; align-items: center; gap: 10px; }
      .logout-btn { padding: 5px 10px; background: #e74c3c; border: none; color: white; border-radius: 3px; cursor: pointer; font-size: 11px; }
      .logout-btn:hover { background: #c0392b; }

      .container { display: flex; height: calc(100vh - 40px); }
      .sidebar { width: 300px; background: #252525; border-right: 1px solid #333; display: flex; flex-direction: column; }
      .main { flex: 1; display: flex; flex-direction: column; background: #1a1a1a; }

      /* Sidebar */
      .sidebar-header { padding: 15px; border-bottom: 1px solid #333; }
      .sidebar-header h2 { font-size: 16px; margin-bottom: 5px; }
      .vm-list { flex: 1; overflow-y: auto; padding: 10px; }
      .vm-item { background: #2a2a2a; padding: 10px; margin-bottom: 8px; border-radius: 4px; border: 1px solid #333; cursor: pointer; }
      .vm-item:hover { border-color: #4a9eff; background: #2d2d2d; }
      .vm-item.selected { border-color: #4a9eff; background: #2d3847; }
      .vm-name { font-weight: 600; font-size: 13px; margin-bottom: 4px; }
      .vm-state { font-size: 10px; padding: 2px 6px; border-radius: 3px; text-transform: uppercase; display: inline-block; margin-bottom: 4px; }
      .vm-state.running { background: #27ae60; color: white; }
      .vm-state.stopped { background: #95a5a6; color: white; }
      .vm-ip { font-size: 11px; color: #888; }
      .vm-actions { margin-top: 8px; display: flex; gap: 4px; }

      /* Tabs */
      .tabs { display: flex; background: #2a2a2a; border-bottom: 1px solid #333; overflow-x: auto; }
      .tab { padding: 10px 15px; cursor: pointer; border-right: 1px solid #333; font-size: 12px; display: flex; align-items: center; gap: 8px; white-space: nowrap; }
      .tab:hover { background: #333; }
      .tab.active { background: #1a1a1a; border-bottom: 2px solid #4a9eff; }
      .tab-close { cursor: pointer; color: #888; }
      .tab-close:hover { color: #e74c3c; }

      /* Terminal area */
      .terminal-container { flex: 1; position: relative; }
      .terminal-pane { position: absolute; top: 0; left: 0; right: 0; bottom: 0; display: none; padding: 10px; }
      .terminal-pane.active { display: block; }
      .welcome { padding: 40px; text-align: center; color: #666; }

      /* Buttons */
      .btn { padding: 6px 10px; background: #4a9eff; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 11px; }
      .btn:hover { background: #3a8eef; }
      .btn-sm { padding: 4px 8px; font-size: 10px; }
      .btn-danger { background: #e74c3c; }
      .btn-danger:hover { background: #c0392b; }
      .btn-success { background: #27ae60; }
      .btn-success:hover { background: #229954; }
      .btn-warning { background: #f39c12; }
      .btn-warning:hover { background: #d68910; }

      /* Modal */
      .modal { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); z-index: 1000; align-items: center; justify-content: center; }
      .modal.active { display: flex; }
      .modal-content { background: #2a2a2a; padding: 25px; border-radius: 8px; width: 90%; max-width: 500px; border: 1px solid #444; }
      .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
      .modal-header h2 { font-size: 18px; }
      .modal-close { cursor: pointer; font-size: 24px; color: #888; }
      .modal-close:hover { color: #e0e0e0; }
      .form-group { margin-bottom: 15px; }
      .form-group label { display: block; font-size: 12px; margin-bottom: 5px; color: #aaa; }
      .form-group input, .form-group select { width: 100%; padding: 8px; background: #333; border: 1px solid #444; color: #e0e0e0; border-radius: 4px; font-size: 13px; }
      .form-group input:focus { outline: none; border-color: #4a9eff; }
      .loading { color: #4a9eff; font-size: 12px; margin-top: 10px; }
    </style>
  </head>
  <body>
    <!-- Menu Bar -->
    <div class="menubar">
      <div class="menu">
        <div class="menu-item" onclick="showCreateVMModal()">+ New VM</div>
      </div>
      <div class="user-info">
        <span id="username">Loading...</span>
        <button class="logout-btn" onclick="logout()">Logout</button>
      </div>
    </div>

    <!-- Main Container -->
    <div class="container">
      <!-- Sidebar with VM List -->
      <div class="sidebar">
        <div class="sidebar-header">
          <h2>Virtual Machines</h2>
          <p style="font-size: 11px; color: #888;">Click VM to select, Connect to open terminal</p>
        </div>
        <div class="vm-list" id="vmList">
          <div class="loading">Loading VMs...</div>
        </div>
      </div>

      <!-- Main Area with Tabs -->
      <div class="main">
        <div class="tabs" id="tabs">
          <!-- Tabs will be added dynamically -->
        </div>
        <div class="terminal-container" id="terminalContainer">
          <div class="welcome">
            <h2>Welcome to Multipass VM Manager</h2>
            <p style="margin-top: 10px;">Select a VM and click "Connect" to open a terminal session</p>
          </div>
          <!-- Terminal panes will be added dynamically -->
        </div>
      </div>
    </div>

    <!-- Create VM Modal -->
    <div class="modal" id="createVMModal">
      <div class="modal-content">
        <div class="modal-header">
          <h2>Create New VM</h2>
          <span class="modal-close" onclick="hideCreateVMModal()">&times;</span>
        </div>
        <form id="createForm">
          <div class="form-group">
            <label>Name *</label>
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
    </div>

    <script type="module">
      import { Terminal } from 'https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/+esm';
      import { FitAddon } from 'https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0/+esm';

      // Import CSS
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = 'https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/css/xterm.css';
      document.head.appendChild(link);

      // Global state
      let terminals = {};
      let selectedVM = null;
      let activeTab = null;

      // Get username
      async function loadUser() {
        try {
          const res = await fetch('/api/auth/check');
          const data = await res.json();
          if (data.authenticated) {
            document.getElementById('username').textContent = data.username;
          }
        } catch (err) {
          console.error('Error loading user:', err);
        }
      }

      // Logout
      window.logout = async function() {
        try {
          await fetch('/api/auth/logout', { method: 'POST' });
          window.location.href = '/login';
        } catch (err) {
          console.error('Logout error:', err);
        }
      }

      // Load VMs
      async function loadVMs() {
        try {
          const res = await fetch('/api/vm/list');
          const data = await res.json();
          const vmList = document.getElementById('vmList');

          if (data.vms.length === 0) {
            vmList.innerHTML = '<div style="color:#888;font-size:12px;text-align:center;padding:20px;">No VMs found.<br/>Create one using + New VM</div>';
            return;
          }

          vmList.innerHTML = data.vms.map(vm => {
            const ip = vm.ipv4.length > 0 ? vm.ipv4[0] : 'No IP';
            const isRunning = vm.state === 'Running';
            const isSelected = selectedVM === vm.name;

            return `
              <div class="vm-item ${isSelected ? 'selected' : ''}" onclick="selectVM('${vm.name}')">
                <div class="vm-name">${vm.name}</div>
                <span class="vm-state ${vm.state.toLowerCase()}">${vm.state}</span>
                <div class="vm-ip">${ip}</div>
                <div class="vm-actions" onclick="event.stopPropagation()">
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
          document.getElementById('vmList').innerHTML = '<div style="color:#e74c3c;font-size:12px;padding:15px;">Error: ' + err.message + '</div>';
        }
      }

      // Select VM
      window.selectVM = function(vmName) {
        selectedVM = vmName;
        loadVMs();
      }

      // Connect to VM (create new tab/terminal)
      window.connectToVM = function(vmName) {
        // Check if already open
        if (terminals[vmName]) {
          switchTab(vmName);
          return;
        }

        // Create tab
        const tabsEl = document.getElementById('tabs');
        const tab = document.createElement('div');
        tab.className = 'tab';
        tab.id = `tab-${vmName}`;
        tab.innerHTML = `
          <span onclick="switchTab('${vmName}')">${vmName}</span>
          <span class="tab-close" onclick="closeTab('${vmName}', event)">×</span>
        `;
        tabsEl.appendChild(tab);

        // Create terminal pane
        const container = document.getElementById('terminalContainer');
        const pane = document.createElement('div');
        pane.className = 'terminal-pane';
        pane.id = `terminal-${vmName}`;
        container.appendChild(pane);

        // Create terminal
        const term = new Terminal({cursorBlink: true, fontFamily: 'monospace', fontSize: 14});
        const fit = new FitAddon();
        term.loadAddon(fit);
        term.open(pane);
        fit.fit();

        // Connect WebSocket
        const ws = new WebSocket(`ws://${location.host}/ws?vm_name=${vmName}`);
        ws.binaryType = "arraybuffer";

        ws.onopen = () => {
          console.log('Connected to', vmName);
          const sendResize = () => {
            ws.send(JSON.stringify({type: "resize", cols: term.cols, rows: term.rows}));
          };
          sendResize();
          window.addEventListener('resize', () => { fit.fit(); sendResize(); });
        };

        ws.onmessage = (e) => {
          if (e.data instanceof ArrayBuffer) term.write(new Uint8Array(e.data));
          else term.write(e.data);
        };

        ws.onerror = () => console.error('WebSocket error for', vmName);
        ws.onclose = () => console.log('Disconnected from', vmName);

        term.onData(data => {
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(data);
          }
        });

        // Store terminal data
        terminals[vmName] = { term, fit, ws, pane, tab };

        // Switch to new tab
        switchTab(vmName);
      }

      // Switch tab
      window.switchTab = function(vmName) {
        // Hide all panes and deactivate tabs
        Object.values(terminals).forEach(t => {
          t.pane.classList.remove('active');
          t.tab.classList.remove('active');
        });

        // Show selected pane and activate tab
        if (terminals[vmName]) {
          terminals[vmName].pane.classList.add('active');
          terminals[vmName].tab.classList.add('active');
          terminals[vmName].fit.fit();
          activeTab = vmName;
        }
      }

      // Close tab
      window.closeTab = function(vmName, event) {
        event.stopPropagation();
        if (!confirm(`Close connection to ${vmName}?`)) return;

        if (terminals[vmName]) {
          terminals[vmName].ws.close();
          terminals[vmName].pane.remove();
          terminals[vmName].tab.remove();
          delete terminals[vmName];

          // Switch to another tab if available
          const remaining = Object.keys(terminals);
          if (remaining.length > 0) {
            switchTab(remaining[0]);
          } else {
            activeTab = null;
          }
        }
      }

      // VM Actions
      window.startVM = async function(name) {
        try {
          await fetch('/api/vm/start', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name})
          });
          setTimeout(loadVMs, 2000);
        } catch (err) {
          alert('Error: ' + err.message);
        }
      }

      window.stopVM = async function(name) {
        if (!confirm(`Stop VM "${name}"?`)) return;
        try {
          await fetch('/api/vm/stop', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name})
          });
          loadVMs();
        } catch (err) {
          alert('Error: ' + err.message);
        }
      }

      window.deleteVM = async function(name) {
        if (!confirm(`Delete VM "${name}"? This cannot be undone.`)) return;
        try {
          await fetch('/api/vm/delete', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name})
          });
          // Close tab if open
          if (terminals[name]) {
            closeTab(name, { stopPropagation: () => {} });
          }
          loadVMs();
        } catch (err) {
          alert('Error: ' + err.message);
        }
      }

      // Modal functions
      window.showCreateVMModal = function() {
        document.getElementById('createVMModal').classList.add('active');
      }

      window.hideCreateVMModal = function() {
        document.getElementById('createVMModal').classList.remove('active');
      }

      // Create VM form
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
            status.innerHTML = '<div style="color:#27ae60;font-size:12px;margin-top:10px;">VM created successfully!</div>';
            e.target.reset();
            setTimeout(() => {
              hideCreateVMModal();
              status.innerHTML = '';
              loadVMs();
            }, 2000);
          } else {
            status.innerHTML = '<div style="color:#e74c3c;font-size:12px;margin-top:10px;">Error: ' + data.detail + '</div>';
          }
        } catch (err) {
          status.innerHTML = '<div style="color:#e74c3c;font-size:12px;margin-top:10px;">Error: ' + err.message + '</div>';
        } finally {
          btn.disabled = false;
        }
      });

      // Initialize
      loadUser();
      loadVMs();
      setInterval(loadVMs, 10000);
    </script>
  </body>
</html>
""")

# Login page
@app.get("/login")
async def login_page():
    return HTMLResponse("""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Login - Multipass VM Manager</title>
    <style>
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body {
        font-family: system-ui, -apple-system, sans-serif;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        display: flex;
        align-items: center;
        justify-content: center;
        height: 100vh;
        color: #fff;
      }
      .login-container {
        background: rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(10px);
        padding: 40px;
        border-radius: 12px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        width: 90%;
        max-width: 400px;
        border: 1px solid rgba(255, 255, 255, 0.2);
      }
      h1 { font-size: 28px; margin-bottom: 10px; text-align: center; }
      .subtitle { text-align: center; margin-bottom: 30px; font-size: 14px; opacity: 0.9; }
      .form-group { margin-bottom: 20px; }
      .form-group label { display: block; font-size: 13px; margin-bottom: 8px; opacity: 0.9; }
      .form-group input {
        width: 100%;
        padding: 12px;
        background: rgba(255, 255, 255, 0.9);
        border: 1px solid rgba(255, 255, 255, 0.3);
        border-radius: 6px;
        font-size: 14px;
        color: #333;
      }
      .form-group input:focus {
        outline: none;
        border-color: #fff;
        background: #fff;
      }
      .btn {
        width: 100%;
        padding: 12px;
        background: #fff;
        color: #667eea;
        border: none;
        border-radius: 6px;
        font-size: 15px;
        font-weight: 600;
        cursor: pointer;
        transition: transform 0.2s;
      }
      .btn:hover { transform: translateY(-2px); }
      .btn:disabled { opacity: 0.6; cursor: not-allowed; }
      .error {
        background: rgba(231, 76, 60, 0.2);
        border: 1px solid rgba(231, 76, 60, 0.5);
        padding: 10px;
        border-radius: 6px;
        margin-top: 15px;
        font-size: 13px;
        text-align: center;
      }
      .info {
        margin-top: 20px;
        text-align: center;
        font-size: 12px;
        opacity: 0.8;
        padding: 15px;
        background: rgba(255, 255, 255, 0.1);
        border-radius: 6px;
      }
    </style>
  </head>
  <body>
    <div class="login-container">
      <h1>Multipass VM Manager</h1>
      <div class="subtitle">Sign in to continue</div>
      <form id="loginForm">
        <div class="form-group">
          <label>Username</label>
          <input type="text" id="username" autocomplete="username" required autofocus />
        </div>
        <div class="form-group">
          <label>Password</label>
          <input type="password" id="password" autocomplete="current-password" required />
        </div>
        <button type="submit" class="btn">Sign In</button>
      </form>
      <div id="error"></div>
      <div class="info">
        Default credentials:<br/>
        Username: <strong>admin</strong><br/>
        Password: <strong>admin123</strong>
      </div>
    </div>

    <script>
      document.getElementById('loginForm').addEventListener('submit', async (e) => {
        e.preventDefault();

        const btn = e.target.querySelector('button');
        const errorEl = document.getElementById('error');

        btn.disabled = true;
        btn.textContent = 'Signing in...';
        errorEl.innerHTML = '';

        try {
          const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              username: document.getElementById('username').value,
              password: document.getElementById('password').value
            })
          });

          if (res.ok) {
            window.location.href = '/';
          } else {
            const data = await res.json();
            errorEl.innerHTML = `<div class="error">${data.detail || 'Login failed'}</div>`;
          }
        } catch (err) {
          errorEl.innerHTML = `<div class="error">Error: ${err.message}</div>`;
        } finally {
          btn.disabled = false;
          btn.textContent = 'Sign In';
        }
      });
    </script>
  </body>
</html>
""")

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
