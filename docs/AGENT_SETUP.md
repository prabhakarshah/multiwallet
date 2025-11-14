# Remote Agent Setup Guide

This guide explains how to set up remote agents to extend your Batwa VM Manager across multiple machines.

## Architecture Overview

```
┌─────────────────────────────────────────┐
│  Master Server                          │
│  - Web Interface                        │
│  - Agent Registry                       │
│  - Request Router                       │
│  - WebSocket Proxy                      │
│  Location: Main server (e.g., laptop)   │
└──────────┬──────────────────────────────┘
           │
    ┌──────┼──────┐
    │      │      │
┌───▼─┐ ┌──▼──┐ ┌─▼────┐
│Local│ │Agent│ │Agent │
│VMs  │ │ 1   │ │ 2    │
└─────┘ └─────┘ └──────┘
          │        │
       Remote   Remote
       Machine  Machine
```

## Prerequisites

### Master Server
- Python 3.8+
- FastAPI and dependencies (`pip install -r requirements.txt`)
- Access from agents (network connectivity)

### Remote Agent Machine
- Python 3.8+
- Multipass installed and configured
- Network access to master server

## Setup Steps

### 1. Install Dependencies on Agent Machine

First, clone or copy the Batwa project to your agent machine:

```bash
# On the agent machine
cd /path/to/batwa
pip install -r requirements.txt
```

### 2. Start the Agent Server

On each remote machine, start an agent server with a unique ID:

```bash
python -m agent.agent_main \
  --agent-id "office-server-1" \
  --api-key "your-secret-key-123" \
  --master-url "http://master-server-ip:8000" \
  --port 8001 \
  --host "0.0.0.0"
```

**Parameters:**
- `--agent-id`: Unique identifier for this agent (required)
- `--api-key`: Authentication key (optional, recommended for production)
- `--master-url`: URL of the master server (required for auto-registration)
- `--port`: Port to listen on (default: 8001)
- `--host`: Host to bind to (default: 0.0.0.0)
- `--heartbeat-interval`: Heartbeat interval in seconds (default: 30)

### 3. Verify Agent Registration

The agent will automatically register with the master server on startup. You can verify this by:

1. Checking the agent server logs for "Successfully registered with master"
2. Using the master server API:
   ```bash
   curl http://master-server:8000/api/agent/list
   ```

### 4. Network Configuration

Ensure the following ports are accessible:

**Agent → Master:**
- Master port (default: 8000) - for registration and heartbeat

**Master → Agent:**
- Agent port (default: 8001) - for VM management commands
- WebSocket connections for terminal sessions

**Firewall Rules Example (UFW):**
```bash
# On agent machine
sudo ufw allow 8001/tcp

# On master machine
sudo ufw allow 8000/tcp
```

## Manual Agent Registration

If you don't want auto-registration, you can manually register an agent:

```bash
curl -X POST http://master-server:8000/api/agent/register \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "office-server-1",
    "hostname": "office-server",
    "api_url": "http://192.168.1.100:8001",
    "api_key": "your-secret-key-123"
  }'
```

## Using Remote Agents

Once agents are registered:

1. **Create VMs on Remote Agents:** VMs will appear in the web interface with the agent hostname displayed
2. **Connect to Remote VMs:** Click "Connect" to open a terminal session (proxied through the master)
3. **Manage Remote VMs:** Start, stop, and delete VMs on remote agents just like local ones

## Running Agent as a Service

### systemd Service (Linux)

Create `/etc/systemd/system/batwa-agent.service`:

```ini
[Unit]
Description=Batwa Agent Service
After=network.target multipass.service

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/batwa
Environment="PATH=/usr/bin:/usr/local/bin"
ExecStart=/usr/bin/python3 -m agent.agent_main \
    --agent-id "office-server-1" \
    --api-key "your-secret-key-123" \
    --master-url "http://master-server:8000" \
    --port 8001
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable batwa-agent
sudo systemctl start batwa-agent
sudo systemctl status batwa-agent
```

### Docker Deployment

Create `docker-compose.yml` for agent:

```yaml
version: '3.8'

services:
  batwa-agent:
    build: .
    container_name: batwa-agent
    command: >
      python -m agent.agent_main
      --agent-id "docker-agent-1"
      --api-key "your-secret-key-123"
      --master-url "http://master-server:8000"
      --port 8001
    ports:
      - "8001:8001"
    volumes:
      - /var/run/multipass_socket:/var/run/multipass_socket
    restart: unless-stopped
```

## Troubleshooting

### Agent Not Appearing in Master

1. Check agent logs for connection errors
2. Verify network connectivity: `ping master-server`
3. Check firewall rules on both machines
4. Verify master URL is correct and accessible

### Agent Shows as Offline

1. Check agent process is running: `ps aux | grep agent_main`
2. Check heartbeat interval and network latency
3. Review agent logs for errors
4. Verify API key matches (if configured)

### Terminal Connection Fails

1. Ensure WebSocket connections are allowed (no proxy blocking)
2. Check that the VM is running on the agent
3. Verify multipass is working on the agent: `multipass list`
4. Check agent logs for WebSocket errors

### VM Commands Timeout

1. Increase timeout in `app/communication.py` (default: 30 seconds)
2. Check network latency between master and agent
3. Verify multipass is responsive on agent machine

## Security Considerations

1. **Use API Keys:** Always set `--api-key` in production
2. **Network Isolation:** Use VPN or private networks for agent communication
3. **Firewall:** Restrict agent ports to only accept connections from master
4. **HTTPS/WSS:** Use reverse proxy (nginx/traefik) with TLS for production
5. **Authentication:** Implement proper authentication on the master server

## Agent API Reference

Agents expose the following REST API endpoints:

- `GET /health` - Health check
- `POST /api/execute` - Execute arbitrary multipass command
- `GET /api/vm/list` - List VMs
- `GET /api/vm/info/{vm_name}` - Get VM info
- `POST /api/vm/create` - Create VM
- `POST /api/vm/start` - Start VM
- `POST /api/vm/stop` - Stop VM
- `POST /api/vm/delete` - Delete VM
- `WS /ws?vm_name={name}` - Terminal WebSocket connection

All endpoints (except `/health`) require the `X-API-Key` header if API key is configured.

## Example: Multi-Region Setup

```bash
# Region 1 - US East
python -m agent.agent_main \
  --agent-id "us-east-1" \
  --master-url "http://master:8000" \
  --port 8001

# Region 2 - EU West
python -m agent.agent_main \
  --agent-id "eu-west-1" \
  --master-url "http://master:8000" \
  --port 8001

# Region 3 - Asia Pacific
python -m agent.agent_main \
  --agent-id "ap-south-1" \
  --master-url "http://master:8000" \
  --port 8001
```

Each agent can manage its own pool of VMs, all accessible through a single master interface.
