# Multipass VM Manager

A web-based interface for managing Multipass virtual machines with real-time terminal access.

## Project Structure

```
batwa/
├── main.py                 # Application entry point
├── requirements.txt        # Python dependencies
├── app/                    # Application modules
│   ├── __init__.py
│   ├── auth.py            # Authentication logic
│   ├── models.py          # Pydantic data models
│   ├── multipass.py       # Multipass VM utilities
│   ├── routes.py          # API route handlers
│   └── websocket.py       # WebSocket terminal handler
├── templates/             # HTML templates
│   ├── index.html         # Main dashboard
│   └── login.html         # Login page
└── static/                # Static assets
    ├── css/
    │   ├── style.css      # Main dashboard styles
    │   └── login.css      # Login page styles
    └── js/
        ├── app.js         # Main application logic
        └── login.js       # Login page logic
```

## Architecture

### Backend (Python/FastAPI)

- **main.py**: Entry point that configures the FastAPI application, mounts static files, and includes routes
- **app/auth.py**: Session management and authentication utilities
- **app/models.py**: Pydantic models for request/response validation
- **app/multipass.py**: Wrapper functions for multipass CLI commands
- **app/routes.py**: API endpoints for authentication and VM management
- **app/websocket.py**: WebSocket handler for real-time terminal connections

### Frontend

- **templates/**: HTML templates served by FastAPI
- **static/css/**: Separated CSS for better maintainability
- **static/js/**: Client-side JavaScript with modular structure

## Features

- User authentication with session management
- Create, start, stop, and delete VMs
- Real-time terminal access via WebSocket
- Multi-tab interface for managing multiple VM connections
- Responsive UI with dark theme

## Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Ensure Multipass is installed on your system

3. Run the application:
   ```bash
   python main.py
   ```

4. Access the application at `http://localhost:8000`

## Default Credentials

- Username: `admin`
- Password: `admin123`

**Note**: In production, replace the simple in-memory authentication with a proper database and hashed passwords.

## API Endpoints

### Authentication
- `POST /api/auth/login` - User login
- `POST /api/auth/logout` - User logout
- `GET /api/auth/check` - Check authentication status

### VM Management
- `POST /api/vm/create` - Create a new VM
- `GET /api/vm/list` - List all VMs
- `GET /api/vm/info/{vm_name}` - Get VM details
- `POST /api/vm/start` - Start a VM
- `POST /api/vm/stop` - Stop a VM
- `POST /api/vm/delete` - Delete a VM

### WebSocket
- `WS /ws?vm_name={name}` - Terminal connection to VM

## Security Considerations

For production deployment:
1. Replace in-memory session storage with Redis or a database
2. Implement proper password hashing (bcrypt, argon2)
3. Configure CORS properly (restrict origins)
4. Use HTTPS
5. Implement rate limiting
6. Add CSRF protection
7. Validate and sanitize all inputs
