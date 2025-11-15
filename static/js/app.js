import { Terminal } from 'https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/+esm';
import { FitAddon } from 'https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0/+esm';

// Import CSS
const link = document.createElement('link');
link.rel = 'stylesheet';
link.href = 'https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/css/xterm.css';
document.head.appendChild(link);

// Global state
let allVMs = [];
let allAgents = [];
let currentView = 'dashboard';
let currentTerminal = null;
let currentVMDetails = null;

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
  loadUser();
  loadData();
  setInterval(loadData, 10000); // Refresh every 10 seconds
});

// Load user info
async function loadUser() {
  try {
    const res = await fetch('/api/auth/check');
    const data = await res.json();
    if (data.authenticated) {
      const username = data.username;
      document.getElementById('userName').textContent = username;

      // Set avatar initial
      const initial = username.charAt(0).toUpperCase();
      document.getElementById('userAvatar').textContent = initial;
    }
  } catch (err) {
    console.error('Error loading user:', err);
  }
}

// Load all data
async function loadData() {
  await Promise.all([loadVMs(), loadAgents()]);
  updateStats();
}

// Refresh data (called by refresh button)
window.refreshData = async function() {
  await loadData();
}

// Load VMs
async function loadVMs() {
  try {
    const res = await fetch('/api/vm/list');
    const data = await res.json();
    allVMs = data.vms || [];

    // Update UI based on current view
    if (currentView === 'dashboard') {
      renderRecentVMs();
    } else if (currentView === 'vms') {
      renderAllVMs();
    }
  } catch (err) {
    console.error('Error loading VMs:', err);
  }
}

// Load agents
async function loadAgents() {
  try {
    const res = await fetch('/api/agent/list');
    if (res.ok) {
      allAgents = await res.json();

      // Update agent count badge
      const onlineCount = allAgents.filter(a => a.status === 'online').length;
      document.getElementById('agentCount').textContent = onlineCount;

      // Update agents view if active
      if (currentView === 'agents') {
        renderAgents();
      }
    }
  } catch (err) {
    console.error('Error loading agents:', err);
  }
}

// Update stats cards
function updateStats() {
  const totalVMs = allVMs.length;
  const runningVMs = allVMs.filter(vm => vm.state === 'Running').length;
  const stoppedVMs = allVMs.filter(vm => vm.state === 'Stopped').length;
  const onlineAgents = allAgents.filter(a => a.status === 'online').length;

  document.getElementById('totalVMs').textContent = totalVMs;
  document.getElementById('runningVMs').textContent = runningVMs;
  document.getElementById('stoppedVMs').textContent = stoppedVMs;
  document.getElementById('onlineAgents').textContent = onlineAgents;
  document.getElementById('vmCount').textContent = totalVMs;
}

// Show view (dashboard, vms, agents)
window.showView = function(viewName) {
  // Hide all views
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));

  // Show selected view
  document.getElementById(`${viewName}View`).classList.add('active');

  // Update nav active state
  document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
  event.target.closest('.nav-item').classList.add('active');

  // Update page title
  const titles = {
    dashboard: { title: 'Dashboard', subtitle: 'Overview of your virtual machines' },
    vms: { title: 'Virtual Machines', subtitle: 'Manage all your VMs' },
    agents: { title: 'Agents', subtitle: 'Connected remote agents' }
  };

  document.getElementById('pageTitle').textContent = titles[viewName].title;
  document.getElementById('pageSubtitle').textContent = titles[viewName].subtitle;

  currentView = viewName;

  // Render appropriate content
  if (viewName === 'dashboard') {
    renderRecentVMs();
  } else if (viewName === 'vms') {
    renderAllVMs();
  } else if (viewName === 'agents') {
    renderAgents();
  }
}

// Render recent VMs (for dashboard)
function renderRecentVMs() {
  const grid = document.getElementById('recentVMsGrid');
  const recentVMs = allVMs.slice(0, 6); // Show first 6

  if (recentVMs.length === 0) {
    grid.innerHTML = `
      <div class="loading">
        No VMs found. <a href="#" onclick="showCreateVMModal(); return false;" style="color: var(--primary);">Create one now</a>
      </div>
    `;
    return;
  }

  grid.innerHTML = recentVMs.map(vm => createVMCard(vm)).join('');
}

// Render all VMs
function renderAllVMs() {
  const grid = document.getElementById('allVMsGrid');

  if (allVMs.length === 0) {
    grid.innerHTML = `
      <div class="loading">
        No VMs found. <a href="#" onclick="showCreateVMModal(); return false;" style="color: var(--primary);">Create one now</a>
      </div>
    `;
    return;
  }

  grid.innerHTML = allVMs.map(vm => createVMCard(vm)).join('');
}

// Create VM card HTML
function createVMCard(vm) {
  const ip = vm.ipv4 && vm.ipv4.length > 0 ? vm.ipv4[0] : 'No IP';
  const isRunning = vm.state === 'Running';
  const agentId = vm.agent_id || null;
  const agentHostname = vm.agent_hostname || 'local';

  return `
    <div class="vm-card">
      <div class="vm-card-header">
        <div class="vm-card-title">
          <h3>${vm.name}</h3>
          <span class="vm-status ${vm.state.toLowerCase()}">${vm.state}</span>
        </div>
        ${agentHostname !== 'local' ? `<span class="vm-agent">@${agentHostname}</span>` : ''}
      </div>
      <div class="vm-card-body">
        <div class="vm-info-row">
          <span class="label">IP Address:</span>
          <span class="value">${ip}</span>
        </div>
        <div class="vm-info-row">
          <span class="label">Location:</span>
          <span class="value">${agentHostname === 'local' ? 'Local Machine' : agentHostname}</span>
        </div>
      </div>
      <div class="vm-card-actions">
        ${isRunning ? `
          <button class="btn-sm btn-primary" onclick="connectToVM('${vm.name}', '${agentId}')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="16 18 22 12 16 6"/>
              <polyline points="8 6 2 12 8 18"/>
            </svg>
            Connect
          </button>
          <button class="btn-sm btn-secondary" onclick="stopVM('${vm.name}', '${agentId}')">Stop</button>
        ` : `
          <button class="btn-sm btn-success" onclick="startVM('${vm.name}', '${agentId}')">Start</button>
        `}
        <button class="btn-sm btn-secondary" onclick="showVMDetailsModal('${vm.name}', '${agentId}')">Details</button>
        <button class="btn-sm btn-danger" onclick="deleteVM('${vm.name}', '${agentId}')">Delete</button>
      </div>
    </div>
  `;
}

// Render agents
function renderAgents() {
  const grid = document.getElementById('agentsGrid');

  if (allAgents.length === 0) {
    grid.innerHTML = `
      <div class="loading">
        No agents connected. <a href="#" onclick="showAddAgentModal(); return false;" style="color: var(--primary);">Add one now</a>
      </div>
    `;
    return;
  }

  grid.innerHTML = allAgents.map(agent => {
    const lastSeen = agent.last_seen ? new Date(agent.last_seen).toLocaleString() : 'Never';
    const statusClass = agent.status === 'online' ? 'online' : 'offline';

    return `
      <div class="agent-card">
        <div class="agent-card-header">
          <h3>${agent.agent_id}</h3>
          <span class="agent-status ${statusClass}">${agent.status}</span>
        </div>
        <div class="agent-card-body">
          <div class="agent-info-row">
            <span class="label">Hostname:</span>
            <span class="value">${agent.hostname}</span>
          </div>
          <div class="agent-info-row">
            <span class="label">API URL:</span>
            <span class="value">${agent.api_url}</span>
          </div>
          <div class="agent-info-row">
            <span class="label">VMs:</span>
            <span class="value">${agent.vm_count || 0}</span>
          </div>
          <div class="agent-info-row">
            <span class="label">Last Seen:</span>
            <span class="value">${lastSeen}</span>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

// Search VMs
document.getElementById('searchInput').addEventListener('input', (e) => {
  const query = e.target.value.toLowerCase();

  if (!query) {
    if (currentView === 'dashboard') renderRecentVMs();
    else if (currentView === 'vms') renderAllVMs();
    return;
  }

  const filtered = allVMs.filter(vm =>
    vm.name.toLowerCase().includes(query) ||
    (vm.agent_hostname && vm.agent_hostname.toLowerCase().includes(query))
  );

  const grid = currentView === 'dashboard' ?
    document.getElementById('recentVMsGrid') :
    document.getElementById('allVMsGrid');

  if (filtered.length === 0) {
    grid.innerHTML = '<div class="loading">No VMs match your search</div>';
  } else {
    grid.innerHTML = filtered.map(vm => createVMCard(vm)).join('');
  }
});

// Modal functions - Create VM
window.showCreateVMModal = function() {
  document.getElementById('createVMModal').classList.add('active');

  // Populate agents dropdown
  const select = document.getElementById('vmAgent');
  select.innerHTML = '<option value="">Local Machine</option>' +
    allAgents
      .filter(a => a.status === 'online')
      .map(a => `<option value="${a.agent_id}">${a.agent_id} (${a.hostname})</option>`)
      .join('');
}

window.hideCreateVMModal = function() {
  document.getElementById('createVMModal').classList.remove('active');
  document.getElementById('createVMForm').reset();
  document.getElementById('createVMStatus').textContent = '';
}

// Modal functions - Add Agent
window.showAddAgentModal = function() {
  document.getElementById('addAgentModal').classList.add('active');
}

window.hideAddAgentModal = function() {
  document.getElementById('addAgentModal').classList.remove('active');
}

window.copyAgentCommand = function() {
  const command = './batwa-agent --agent-id=my-agent --master-url=http://<this-server>:8000';
  navigator.clipboard.writeText(command).then(() => {
    const btn = event.target;
    const originalText = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => {
      btn.textContent = originalText;
    }, 2000);
  }).catch(err => {
    console.error('Failed to copy:', err);
  });
}

// Modal functions - VM Details
window.showVMDetailsModal = async function(vmName, agentId) {
  document.getElementById('vmDetailsModal').classList.add('active');
  document.getElementById('vmDetailsTitle').textContent = `VM Details - ${vmName}`;
  document.getElementById('vmDetailsContent').innerHTML = '<div class="loading">Loading VM details...</div>';

  currentVMDetails = { vmName, agentId };

  try {
    let url = `/api/vm/info/${vmName}`;
    if (agentId && agentId !== 'null') {
      url += `?agent_id=${agentId}`;
    }

    const res = await fetch(url);
    const vm = await res.json();

    const ip = vm.ipv4 && vm.ipv4.length > 0 ? vm.ipv4.join(', ') : 'No IP';
    const isRunning = vm.state === 'Running';

    document.getElementById('vmDetailsContent').innerHTML = `
      <div class="vm-details-grid">
        <div class="detail-item">
          <span class="detail-label">Name</span>
          <span class="detail-value">${vm.name}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">State</span>
          <span class="detail-value"><span class="vm-status ${vm.state.toLowerCase()}">${vm.state}</span></span>
        </div>
        <div class="detail-item">
          <span class="detail-label">IP Address</span>
          <span class="detail-value">${ip}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">Image</span>
          <span class="detail-value">${vm.image || 'N/A'}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">CPUs</span>
          <span class="detail-value">${vm.cpus || 'N/A'}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">Memory</span>
          <span class="detail-value">${vm.memory || 'N/A'}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">Disk</span>
          <span class="detail-value">${vm.disk || 'N/A'}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">Location</span>
          <span class="detail-value">${vm.agent_hostname || 'Local Machine'}</span>
        </div>
      </div>
    `;

    // Update connect button state
    const connectBtn = document.getElementById('vmDetailsConnectBtn');
    if (isRunning) {
      connectBtn.style.display = 'inline-block';
      connectBtn.disabled = false;
    } else {
      connectBtn.style.display = 'none';
    }
  } catch (err) {
    document.getElementById('vmDetailsContent').innerHTML = `
      <div class="loading">Error loading VM details: ${err.message}</div>
    `;
  }
}

window.hideVMDetailsModal = function() {
  document.getElementById('vmDetailsModal').classList.remove('active');
  currentVMDetails = null;
}

window.connectFromDetails = function() {
  if (currentVMDetails) {
    hideVMDetailsModal();
    connectToVM(currentVMDetails.vmName, currentVMDetails.agentId);
  }
}

// Modal functions - Terminal
window.showTerminalModal = function(vmName, agentId) {
  document.getElementById('terminalModal').classList.add('active');
  document.getElementById('terminalTitle').textContent = `Terminal - ${vmName}`;

  // Create terminal if not exists
  if (!currentTerminal) {
    const container = document.getElementById('terminalContainer');
    container.innerHTML = ''; // Clear

    const term = new Terminal({
      cursorBlink: true,
      fontFamily: "'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', Consolas, 'Courier New', monospace",
      fontSize: 14,
      theme: {
        background: '#1A1A1A',
        foreground: '#E0E0E0',
        cursor: '#667eea'
      }
    });

    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(container);
    fit.fit();

    // Connect WebSocket
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
      window.addEventListener('resize', () => {
        fit.fit();
        sendResize();
      });
    };

    ws.onmessage = (e) => {
      if (e.data instanceof ArrayBuffer) {
        term.write(new Uint8Array(e.data));
      } else {
        term.write(e.data);
      }
    };

    ws.onerror = () => {
      console.error('WebSocket error for', vmName);
      term.write('\r\n\x1b[31mConnection error\x1b[0m\r\n');
    };

    ws.onclose = () => {
      console.log('Disconnected from', vmName);
      term.write('\r\n\x1b[33mConnection closed\x1b[0m\r\n');
    };

    term.onData(data => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(data);
      }
    });

    currentTerminal = { term, fit, ws, vmName, agentId };
  }
}

window.hideTerminalModal = function() {
  document.getElementById('terminalModal').classList.remove('active');

  // Close terminal connection
  if (currentTerminal) {
    if (currentTerminal.ws) {
      currentTerminal.ws.close();
    }
    currentTerminal = null;
    document.getElementById('terminalContainer').innerHTML = '';
  }
}

// Connect to VM (opens terminal modal)
window.connectToVM = function(vmName, agentId) {
  showTerminalModal(vmName, agentId);
}

// VM Actions
window.startVM = async function(vmName, agentId) {
  try {
    const payload = { name: vmName };
    if (agentId && agentId !== 'null') {
      payload.agent_id = agentId;
    }

    await fetch('/api/vm/start', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });

    setTimeout(loadVMs, 2000); // Wait for VM to start
  } catch (err) {
    alert('Error starting VM: ' + err.message);
  }
}

window.stopVM = async function(vmName, agentId) {
  if (!confirm(`Stop VM "${vmName}"?`)) return;

  try {
    const payload = { name: vmName };
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
    alert('Error stopping VM: ' + err.message);
  }
}

window.deleteVM = async function(vmName, agentId) {
  if (!confirm(`Delete VM "${vmName}"? This cannot be undone.`)) return;

  try {
    const payload = { name: vmName };
    if (agentId && agentId !== 'null') {
      payload.agent_id = agentId;
    }

    await fetch('/api/vm/delete', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });

    loadVMs();
  } catch (err) {
    alert('Error deleting VM: ' + err.message);
  }
}

// Create VM form submission
document.getElementById('createVMForm').addEventListener('submit', async (e) => {
  e.preventDefault();

  const status = document.getElementById('createVMStatus');
  status.textContent = 'Creating VM...';
  status.style.color = 'var(--primary)';

  try {
    const agentId = document.getElementById('vmAgent').value;
    const payload = {
      name: document.getElementById('vmName').value,
      image: document.getElementById('vmImage').value,
      cpus: parseInt(document.getElementById('vmCpus').value),
      memory: document.getElementById('vmMemory').value,
      disk: document.getElementById('vmDisk').value
    };

    if (agentId) {
      payload.agent_id = agentId;
    }

    const res = await fetch('/api/vm/create', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });

    const data = await res.json();

    if (res.ok) {
      status.textContent = 'VM created successfully!';
      status.style.color = 'var(--success)';
      setTimeout(() => {
        hideCreateVMModal();
        loadVMs();
      }, 2000);
    } else {
      status.textContent = 'Error: ' + (data.detail || 'Failed to create VM');
      status.style.color = 'var(--danger)';
    }
  } catch (err) {
    status.textContent = 'Error: ' + err.message;
    status.style.color = 'var(--danger)';
  }
});

// Logout
window.logout = async function() {
  try {
    await fetch('/api/auth/logout', { method: 'POST' });
    window.location.href = '/login';
  } catch (err) {
    console.error('Logout error:', err);
  }
}
