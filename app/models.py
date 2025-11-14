"""Pydantic models for API requests and responses."""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from datetime import datetime


class LoginRequest(BaseModel):
    """Login request model."""
    username: str
    password: str


class VMCreateRequest(BaseModel):
    """VM creation request model."""
    name: str
    cpus: Optional[int] = 1
    memory: Optional[str] = "1G"
    disk: Optional[str] = "5G"
    image: Optional[str] = "22.04"  # Ubuntu version
    agent_id: Optional[str] = None  # Target agent ID (None = local)


class VMActionRequest(BaseModel):
    """VM action request model (start, stop, delete)."""
    name: str
    agent_id: Optional[str] = None  # Target agent ID (None = local)


# Agent-related models
class AgentRegisterRequest(BaseModel):
    """Agent registration request model."""
    agent_id: str
    hostname: str
    api_url: str  # Base URL for agent API (http://agent-host:port)
    api_key: Optional[str] = None  # Authentication key for agent
    tags: Optional[Dict[str, str]] = {}  # Custom tags for agent


class AgentInfo(BaseModel):
    """Agent information model."""
    agent_id: str
    hostname: str
    api_url: str
    status: str  # online, offline, error
    last_seen: Optional[datetime] = None
    tags: Optional[Dict[str, str]] = {}
    vm_count: Optional[int] = 0


class AgentHeartbeat(BaseModel):
    """Agent heartbeat model."""
    agent_id: str
    timestamp: datetime
    status: str
    vm_count: int


class RemoteCommandRequest(BaseModel):
    """Remote command execution request."""
    command: str
    args: List[str]
    timeout: Optional[int] = 30  # seconds


class RemoteCommandResponse(BaseModel):
    """Remote command execution response."""
    success: bool
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    return_code: int
    error: Optional[str] = None


class VMInfoExtended(BaseModel):
    """Extended VM info with agent information."""
    name: str
    state: str
    ipv4: Optional[str] = None
    release: Optional[str] = None
    agent_id: Optional[str] = None  # Agent hosting this VM
    agent_hostname: Optional[str] = None
