"""Agent registry and management."""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from app.models import AgentInfo, AgentRegisterRequest, AgentHeartbeat
import logging

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Registry for managing remote agents."""

    def __init__(self):
        """Initialize the agent registry."""
        self._agents: Dict[str, AgentInfo] = {}
        self._api_keys: Dict[str, str] = {}  # agent_id -> api_key
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._heartbeat_interval = 30  # seconds
        self._offline_threshold = 60  # seconds

    def register_agent(self, request: AgentRegisterRequest) -> AgentInfo:
        """Register a new agent or update existing one."""
        agent_info = AgentInfo(
            agent_id=request.agent_id,
            hostname=request.hostname,
            api_url=request.api_url.rstrip('/'),
            status="online",
            last_seen=datetime.now(),
            tags=request.tags or {},
            vm_count=0
        )

        self._agents[request.agent_id] = agent_info

        # Store API key if provided
        if request.api_key:
            self._api_keys[request.agent_id] = request.api_key

        logger.info(f"Registered agent: {request.agent_id} ({request.hostname})")
        return agent_info

    def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent."""
        if agent_id in self._agents:
            del self._agents[agent_id]
            if agent_id in self._api_keys:
                del self._api_keys[agent_id]
            logger.info(f"Unregistered agent: {agent_id}")
            return True
        return False

    def get_agent(self, agent_id: str) -> Optional[AgentInfo]:
        """Get agent information by ID."""
        return self._agents.get(agent_id)

    def get_all_agents(self) -> List[AgentInfo]:
        """Get all registered agents."""
        return list(self._agents.values())

    def get_online_agents(self) -> List[AgentInfo]:
        """Get all online agents."""
        return [agent for agent in self._agents.values() if agent.status == "online"]

    def get_agent_api_key(self, agent_id: str) -> Optional[str]:
        """Get API key for an agent."""
        return self._api_keys.get(agent_id)

    def update_heartbeat(self, heartbeat: AgentHeartbeat):
        """Update agent heartbeat."""
        agent = self._agents.get(heartbeat.agent_id)
        if agent:
            agent.last_seen = heartbeat.timestamp
            agent.status = heartbeat.status
            agent.vm_count = heartbeat.vm_count
            logger.debug(f"Heartbeat updated for agent: {heartbeat.agent_id}")

    def update_vm_count(self, agent_id: str, count: int):
        """Update VM count for an agent."""
        agent = self._agents.get(agent_id)
        if agent:
            agent.vm_count = count

    def check_agent_status(self):
        """Check and update status of all agents based on last_seen."""
        now = datetime.now()
        threshold = timedelta(seconds=self._offline_threshold)

        for agent in self._agents.values():
            if agent.last_seen:
                time_since_last_seen = now - agent.last_seen
                if time_since_last_seen > threshold:
                    if agent.status != "offline":
                        agent.status = "offline"
                        logger.warning(f"Agent {agent.agent_id} is now offline")
                else:
                    if agent.status == "offline":
                        agent.status = "online"
                        logger.info(f"Agent {agent.agent_id} is back online")

    async def start_heartbeat_monitor(self):
        """Start the heartbeat monitoring task."""
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            logger.info("Started agent heartbeat monitor")

    async def stop_heartbeat_monitor(self):
        """Stop the heartbeat monitoring task."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            logger.info("Stopped agent heartbeat monitor")

    async def _heartbeat_loop(self):
        """Periodic heartbeat monitoring loop."""
        while True:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                self.check_agent_status()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")


# Global agent registry instance
agent_registry = AgentRegistry()