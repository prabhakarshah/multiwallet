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
      const agent_id = vm.agent_id || null;
      const agent_hostname = vm.agent_hostname || 'local';
      const agent_display = agent_hostname !== 'local' ? `@ ${agent_hostname}` : '';

      return `
        <div class="vm-item ${isSelected ? 'selected' : ''}" onclick="selectVM('${vm.name}')">
          <div class="vm-name">${vm.name} <span style="color:#888;font-size:11px;">${agent_display}</span></div>
          <span class="vm-state ${vm.state.toLowerCase()}">${vm.state}</span>
          <div class="vm-ip">${ip}</div>
          <div class="vm-actions" onclick="event.stopPropagation()">
            ${isRunning ?
              `<button class="btn btn-sm btn-success" onclick="connectToVM('${vm.name}', '${agent_id}')">Connect</button>
               <button class="btn btn-sm btn-warning" onclick="stopVM('${vm.name}', '${agent_id}')">Stop</button>` :
              `<button class="btn btn-sm" onclick="startVM('${vm.name}', '${agent_id}')">Start</button>`
            }
            <button class="btn btn-sm btn-danger" onclick="deleteVM('${vm.name}', '${agent_id}')">Delete</button>
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
window.connectToVM = function(vmName, agentId) {
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

  // Connect WebSocket with agent_id if provided
  let wsUrl = `ws://${location.host}/ws?vm_name=${vmName}`;
  if (agentId && agentId !== 'null') {
    wsUrl += `&agent_id=${agentId}`;
  }
  const ws = new WebSocket(wsUrl);
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
window.startVM = async function(name, agentId) {
  try {
    const payload = { name };
    if (agentId && agentId !== 'null') {
      payload.agent_id = agentId;
    }
    await fetch('/api/vm/start', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    setTimeout(loadVMs, 2000);
  } catch (err) {
    alert('Error: ' + err.message);
  }
}

window.stopVM = async function(name, agentId) {
  if (!confirm(`Stop VM "${name}"?`)) return;
  try {
    const payload = { name };
    if (agentId && agentId !== 'null') {
      payload.agent_id = agentId;
    }
    await fetch('/api/vm/stop', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    loadVMs();
  } catch (err) {
    alert('Error: ' + err.message);
  }
}

window.deleteVM = async function(name, agentId) {
  if (!confirm(`Delete VM "${name}"? This cannot be undone.`)) return;
  try {
    const payload = { name };
    if (agentId && agentId !== 'null') {
      payload.agent_id = agentId;
    }
    await fetch('/api/vm/delete', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
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
