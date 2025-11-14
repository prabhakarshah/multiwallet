# Batwa API Documentation

## Overview

Batwa provides a REST API for managing multipass VMs both locally and on remote agents.

Base URL: `http://your-server:8000`

## Authentication

Most endpoints require authentication via session cookies. Login first to obtain a session.

## Endpoints

### Authentication

#### POST /api/auth/login
Login and create a session.

**Request:**
```json
{
  "username": "admin",
  "password": "admin"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Login successful"
}
```

Sets a `session_id` cookie.

#### POST /api/auth/logout
Logout and destroy session.

**Response:**
```json
{
  "success": true,
  "message": "Logged out"
}
```

#### GET /api/auth/check
Check authentication status.

**Response:**
```json
{
  "authenticated": true,
  "username": "admin"
}
```

---

### Agent Management

#### POST /api/agent/register
Register a new agent (called automatically by agents on startup).

**Request:**
```json
{
  "agent_id": "office-server-1",
  "hostname": "office-server",
  "api_url": "http://192.168.1.100:8001",
  "api_key": "optional-api-key",
  "tags": {
    "region": "us-east",
    "environment": "production"
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "Agent 'office-server-1' registered successfully",
  "agent": {
    "agent_id": "office-server-1",
    "hostname": "office-server",
    "api_url": "http://192.168.1.100:8001",
    "status": "online",
    "last_seen": "2025-01-13T10:30:00",
    "tags": {"region": "us-east"},
    "vm_count": 0
  }
}
```

#### GET /api/agent/list
List all registered agents.

**Response:**
```json
[
  {
    "agent_id": "office-server-1",
    "hostname": "office-server",
    "api_url": "http://192.168.1.100:8001",
    "status": "online",
    "last_seen": "2025-01-13T10:30:00",
    "tags": {},
    "vm_count": 3
  }
]
```

#### GET /api/agent/info/{agent_id}
Get information about a specific agent.

**Response:**
```json
{
  "success": true,
  "agent": {
    "agent_id": "office-server-1",
    "hostname": "office-server",
    "api_url": "http://192.168.1.100:8001",
    "status": "online",
    "last_seen": "2025-01-13T10:30:00",
    "tags": {},
    "vm_count": 3
  }
}
```

#### DELETE /api/agent/unregister/{agent_id}
Unregister an agent.

**Response:**
```json
{
  "success": true,
  "message": "Agent 'office-server-1' unregistered successfully"
}
```

#### POST /api/agent/heartbeat
Receive heartbeat from an agent (called automatically by agents).

**Request:**
```json
{
  "agent_id": "office-server-1",
  "timestamp": "2025-01-13T10:30:00",
  "status": "online",
  "vm_count": 3
}
```

**Response:**
```json
{
  "success": true,
  "message": "Heartbeat received"
}
```

---

### VM Management

All VM endpoints now support an optional `agent_id` field to target remote agents.

#### POST /api/vm/create
Create a new VM.

**Request:**
```json
{
  "name": "my-vm",
  "cpus": 2,
  "memory": "2G",
  "disk": "10G",
  "image": "22.04",
  "agent_id": "office-server-1"  // Optional: omit for local VM
}
```

**Response:**
```json
{
  "success": true,
  "message": "VM 'my-vm' created successfully",
  "vm_name": "my-vm",
  "agent_id": "office-server-1",
  "agent_hostname": "office-server"
}
```

#### GET /api/vm/list
List all VMs (from local and all registered agents).

**Response:**
```json
{
  "success": true,
  "vms": [
    {
      "name": "local-vm",
      "state": "Running",
      "ipv4": ["192.168.64.2"],
      "release": "22.04 LTS",
      "agent_id": null,
      "agent_hostname": "local"
    },
    {
      "name": "remote-vm",
      "state": "Running",
      "ipv4": ["192.168.64.3"],
      "release": "22.04 LTS",
      "agent_id": "office-server-1",
      "agent_hostname": "office-server"
    }
  ]
}
```

#### GET /api/vm/info/{vm_name}
Get detailed information about a specific VM.

**Response:**
```json
{
  "success": true,
  "info": {
    "state": "Running",
    "image_release": "22.04 LTS",
    "memory": "2G",
    "cpus": 2,
    "disk_size": "10G",
    "ipv4": ["192.168.64.2"]
  }
}
```

#### POST /api/vm/start
Start a stopped VM.

**Request:**
```json
{
  "name": "my-vm",
  "agent_id": "office-server-1"  // Optional
}
```

**Response:**
```json
{
  "success": true,
  "message": "VM 'my-vm' started"
}
```

#### POST /api/vm/stop
Stop a running VM.

**Request:**
```json
{
  "name": "my-vm",
  "agent_id": "office-server-1"  // Optional
}
```

**Response:**
```json
{
  "success": true,
  "message": "VM 'my-vm' stopped"
}
```

#### POST /api/vm/delete
Delete a VM.

**Request:**
```json
{
  "name": "my-vm",
  "agent_id": "office-server-1"  // Optional
}
```

**Response:**
```json
{
  "success": true,
  "message": "VM 'my-vm' deleted"
}
```

---

### WebSocket

#### WS /ws
WebSocket endpoint for terminal connections to VMs.

**Query Parameters:**
- `vm_name` (required): Name of the VM
- `agent_id` (optional): Agent ID if VM is on remote agent
- `session_id` (optional): Session ID for authentication

**Example:**
```javascript
const ws = new WebSocket('ws://localhost:8000/ws?vm_name=my-vm&agent_id=office-server-1');
```

**Messages:**

Resize terminal:
```json
{
  "type": "resize",
  "cols": 80,
  "rows": 24
}
```

Keyboard input: Send raw text data

Terminal output: Receives binary or text data

---

## Error Responses

All endpoints may return error responses in the following format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

Common HTTP status codes:
- `200 OK` - Success
- `401 Unauthorized` - Not authenticated
- `403 Forbidden` - Invalid API key
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server error

## Rate Limiting

Currently no rate limiting is implemented. Consider adding rate limiting in production environments.

## Security

For production deployments:
1. Use HTTPS/WSS instead of HTTP/WS
2. Implement proper authentication mechanisms
3. Use API keys for agent authentication
4. Restrict network access with firewalls
5. Use VPN or private networks for agent communication
