# Batwa - Multipass VM Manager (Go Version)

A distributed Multipass VM manager with a web interface, written in Go. This is a complete conversion from the original Python/FastAPI implementation to Go using Fiber.

## Features

- Web-based UI for managing Multipass VMs
- Support for local and remote VM management via agents
- Real-time terminal access to VMs via WebSocket
- Agent heartbeat monitoring
- Session-based authentication

## Architecture

- **Main Server**: Manages the web interface, API, and coordinates with remote agents
- **Agent**: Runs on remote machines to enable remote VM management

## Prerequisites

- Go 1.21 or higher
- Multipass installed on the host machine(s)

## Installation

1. Clone the repository
2. Install dependencies:
```bash
make deps
```

## Building

### Build everything:
```bash
make build
```

### Build only the server:
```bash
make build-server
```

### Build only the agent:
```bash
make build-agent
```

## Running

### Main Server

```bash
# Using make
make run

# Or directly
go run main.go

# Or using the binary
./bin/batwa-server
```

The server will start on port 8000 by default. You can override this with the `PORT` environment variable:

```bash
PORT=9000 ./bin/batwa-server
```

### Agent

```bash
# Using make
make run-agent

# Or directly
go run cmd/agent/main.go --agent-id=agent1 --master-url=http://localhost:8000

# Or using the binary
./bin/batwa-agent --agent-id=agent1 --master-url=http://localhost:8000 --port=8001
```

#### Agent Options:
- `--agent-id`: Unique identifier for the agent (required)
- `--master-url`: URL of the master server (e.g., http://master:8000)
- `--api-key`: API key for authentication (optional)
- `--port`: Port to listen on (default: 8001)
- `--host`: Host to bind to (default: 0.0.0.0)
- `--heartbeat-interval`: Heartbeat interval in seconds (default: 30)

## Project Structure

```
.
├── main.go                 # Main server entry point
├── cmd/
│   └── agent/
│       └── main.go         # Agent server entry point
├── pkg/
│   ├── models/             # Data models
│   ├── auth/               # Authentication
│   ├── multipass/          # Multipass command execution
│   ├── agents/             # Agent registry
│   ├── communication/      # Agent communication
│   ├── executor/           # VM executor abstraction
│   ├── websocket/          # WebSocket handler
│   └── routes/             # HTTP routes
├── static/                 # Static files (CSS, JS)
├── templates/              # HTML templates
└── Makefile               # Build and run commands
```

## API Endpoints

### Authentication
- `POST /api/auth/login` - Login
- `POST /api/auth/logout` - Logout
- `GET /api/auth/check` - Check authentication status

### Agent Management
- `POST /api/agent/register` - Register a new agent
- `DELETE /api/agent/unregister/:agent_id` - Unregister an agent
- `GET /api/agent/list` - List all agents
- `GET /api/agent/info/:agent_id` - Get agent info
- `POST /api/agent/heartbeat` - Receive agent heartbeat

### VM Management
- `POST /api/vm/create` - Create a new VM
- `GET /api/vm/list` - List all VMs
- `GET /api/vm/info/:vm_name` - Get VM info
- `POST /api/vm/start` - Start a VM
- `POST /api/vm/stop` - Stop a VM
- `POST /api/vm/delete` - Delete a VM

### WebSocket
- `GET /ws?vm_name=<name>&agent_id=<id>` - Terminal access to a VM

## Default Credentials

- Username: `admin`
- Password: `admin123`

**Note**: Change these in production by modifying `pkg/auth/auth.go`.

## Differences from Python Version

The Go implementation is functionally equivalent to the Python version but with some Go-specific improvements:

- Better concurrency handling using goroutines
- More efficient memory usage
- Faster startup time
- Single binary deployment (no virtual environment needed)
- Native cross-compilation support

## License

MIT
