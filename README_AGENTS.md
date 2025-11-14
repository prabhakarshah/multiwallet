# Batwa - Distributed Multipass VM Manager

## Overview

Batwa now supports remote agents, allowing you to manage multipass VMs across multiple machines from a single web interface. This enables distributed VM management across different hosts, regions, or environments.

## Features

### Core Features
- **Web-based VM Management**: Create, start, stop, and delete VMs through an intuitive web interface
- **Real-time Terminal Access**: Connect to VM shells via WebSocket with full terminal emulation
- **Session Management**: Simple authentication system for secure access

### Remote Agent Features (NEW)
- **Distributed Architecture**: Deploy agents on multiple machines to extend VM management
- **Centralized Control**: Manage all VMs (local and remote) from a single master interface
- **Automatic Discovery**: Agents automatically register with the master server
- **Health Monitoring**: Real-time agent status monitoring with heartbeat mechanism
- **Transparent Proxying**: Terminal sessions to remote VMs are seamlessly proxied through the master
- **Flexible Deployment**: Run agents on any machine with multipass and network connectivity

## Quick Start

### Master Server

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the Master Server:**
   ```bash
   python main.py
   ```

3. **Access the Web Interface:**
   Open `http://localhost:8000` in your browser
   Default credentials: `admin` / `admin`

### Remote Agent

1. **On the remote machine, install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start an agent:**
   ```bash
   # Using the helper script
   export AGENT_ID="my-remote-agent"
   export MASTER_URL="http://master-server-ip:8000"
   export API_KEY="optional-secret-key"
   ./start_agent.sh

   # Or directly with Python
   python -m agent.agent_main \
     --agent-id "my-remote-agent" \
     --master-url "http://master-server-ip:8000" \
     --api-key "optional-secret-key" \
     --port 8001
   ```

3. **Verify Agent Registration:**
   The agent should appear in the master server logs and be available for VM creation.

## Architecture

```
Master Server (Your Laptop/Main Server)
├── Web Interface (Port 8000)
├── API Server
├── Agent Registry
├── WebSocket Proxy
└── Local Multipass (optional)

Remote Agents (Other Machines)
├── Agent API Server (Port 8001)
├── Multipass Management
└── Local VMs
```

### Communication Flow

1. **Agent Registration**: Agent connects to master and registers itself
2. **Heartbeat**: Agent sends periodic heartbeats to maintain online status
3. **VM Operations**: Master routes VM commands to appropriate agent via HTTP/REST
4. **Terminal Sessions**: WebSocket connections are proxied from master to agent

## Project Structure

```
batwa/
├── main.py                    # Master server entry point
├── app/
│   ├── auth.py                # Authentication
│   ├── models.py              # Data models (VM, Agent, etc.)
│   ├── routes.py              # API endpoints
│   ├── multipass.py           # Local multipass wrapper
│   ├── websocket.py           # WebSocket handling with remote support
│   ├── agents.py              # Agent registry and management
│   ├── communication.py       # Master-agent communication protocol
│   └── remote_executor.py    # Abstract VM executor (local/remote)
├── agent/
│   ├── agent_main.py          # Agent server entry point
│   ├── agent_executor.py      # Agent-side multipass operations
│   └── __init__.py
├── static/                    # Frontend assets (CSS, JS)
├── templates/                 # HTML templates
├── docs/
│   ├── AGENT_SETUP.md         # Detailed agent setup guide
│   └── API.md                 # API documentation
├── start_agent.sh             # Helper script to start agents
├── agent.env.example          # Example environment configuration
└── requirements.txt           # Python dependencies
```

## Usage Examples

### Creating VMs on Different Agents

1. **Local VM:**
   - Create VM through web interface
   - Leave agent selection as "local" or blank

2. **Remote VM:**
   - Select the target agent from the dropdown (when implemented)
   - Or use API directly:
     ```bash
     curl -X POST http://localhost:8000/api/vm/create \
       -H "Content-Type: application/json" \
       -d '{
         "name": "remote-vm-1",
         "cpus": 2,
         "memory": "2G",
         "disk": "10G",
         "image": "22.04",
         "agent_id": "my-remote-agent"
       }'
     ```

### Connecting to Remote VMs

1. Click "Connect" button on any VM (local or remote)
2. The master automatically:
   - Detects the VM's location (local vs. remote)
   - Establishes appropriate connection (direct PTY or agent proxy)
   - Opens terminal session in the browser

### Monitoring Agents

```bash
# List all agents
curl http://localhost:8000/api/agent/list

# Get specific agent info
curl http://localhost:8000/api/agent/info/my-remote-agent
```

## Configuration

### Master Server

Edit configuration in `main.py` or use environment variables:
- `PORT`: Server port (default: 8000)
- `HOST`: Server host (default: 0.0.0.0)

### Agent

Configure via command-line arguments or environment variables (see `agent.env.example`):
- `AGENT_ID`: Unique agent identifier
- `MASTER_URL`: Master server URL
- `API_KEY`: Optional authentication key
- `AGENT_PORT`: Agent listening port (default: 8001)
- `AGENT_HOST`: Agent bind host (default: 0.0.0.0)
- `HEARTBEAT_INTERVAL`: Heartbeat frequency in seconds (default: 30)

## API Endpoints

### Agent Management
- `POST /api/agent/register` - Register new agent
- `GET /api/agent/list` - List all agents
- `GET /api/agent/info/{agent_id}` - Get agent details
- `DELETE /api/agent/unregister/{agent_id}` - Remove agent
- `POST /api/agent/heartbeat` - Agent heartbeat

### VM Management
- `POST /api/vm/create` - Create VM (supports `agent_id`)
- `GET /api/vm/list` - List all VMs (aggregated from all agents)
- `GET /api/vm/info/{vm_name}` - Get VM info
- `POST /api/vm/start` - Start VM (supports `agent_id`)
- `POST /api/vm/stop` - Stop VM (supports `agent_id`)
- `POST /api/vm/delete` - Delete VM (supports `agent_id`)

See [docs/API.md](docs/API.md) for complete API documentation.

## Deployment

### Development
- Run master and agents directly with Python
- Use `start_agent.sh` for quick agent startup

### Production

**Systemd Service (Linux):**
See [docs/AGENT_SETUP.md](docs/AGENT_SETUP.md) for systemd service configuration.

**Docker:**
```bash
# Master
docker run -p 8000:8000 batwa-master

# Agent
docker run -p 8001:8001 \
  -e AGENT_ID=docker-agent \
  -e MASTER_URL=http://master:8000 \
  batwa-agent
```

## Security Considerations

For production deployments:

1. **Change Default Credentials**: Update admin password in `app/auth.py`
2. **Use API Keys**: Set `--api-key` for agent authentication
3. **Enable HTTPS**: Use reverse proxy (nginx/traefik) with TLS
4. **Network Isolation**: Use VPN or private networks for agent communication
5. **Firewall Rules**: Restrict agent ports to known master IPs
6. **Regular Updates**: Keep dependencies updated

## Troubleshooting

### Agent Won't Connect
- Check network connectivity between agent and master
- Verify firewall rules allow traffic on agent port
- Check master URL is accessible from agent machine
- Review agent logs for connection errors

### VM Operations Timeout
- Increase timeout in `app/communication.py`
- Check network latency between master and agent
- Verify multipass is responsive on agent machine

### Terminal Connection Fails
- Ensure WebSocket connections are allowed (check proxy settings)
- Verify VM is running on the agent
- Check browser console for WebSocket errors
- Review agent logs for PTY/multipass errors

See [docs/AGENT_SETUP.md](docs/AGENT_SETUP.md) for detailed troubleshooting.

## Dependencies

### Python Packages
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `pydantic` - Data validation
- `httpx` - HTTP client for agent communication
- `websockets` - WebSocket client for remote terminal proxying
- `python-multipart` - Form data parsing

### System Requirements
- Python 3.8+
- Multipass (installed and configured on each agent)
- Network connectivity between master and agents

## Contributing

Contributions are welcome! Areas for improvement:

- [ ] Agent UI in web interface for registration/management
- [ ] Support for agent tags/labels for organization
- [ ] VM migration between agents
- [ ] Load balancing for VM creation
- [ ] Metrics and monitoring dashboard
- [ ] Multi-user authentication and authorization
- [ ] TLS/SSL support out of the box
- [ ] Agent auto-discovery via mDNS/Bonjour
- [ ] VM templates and cloning
- [ ] Backup and restore functionality

## License

[Your License Here]

## Credits

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [xterm.js](https://xtermjs.org/) - Terminal emulation in the browser
- [Multipass](https://multipass.run/) - Ubuntu VM manager

---

**Note**: This project is designed for internal/development use. Implement proper security measures before deploying to production environments.
