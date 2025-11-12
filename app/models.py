"""Pydantic models for API requests and responses."""
from typing import Optional
from pydantic import BaseModel


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


class VMActionRequest(BaseModel):
    """VM action request model (start, stop, delete)."""
    name: str
