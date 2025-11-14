"""Communication protocol for master-agent interaction."""
import httpx
import logging
from typing import Optional, Dict, Any
from app.models import RemoteCommandRequest, RemoteCommandResponse
from app.agents import agent_registry

logger = logging.getLogger(__name__)


class AgentCommunicator:
    """Handles communication with remote agents."""

    def __init__(self, timeout: int = 30):
        """Initialize the communicator.

        Args:
            timeout: Default timeout for requests in seconds
        """
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()

    def _get_headers(self, agent_id: str) -> Dict[str, str]:
        """Get headers for agent requests."""
        headers = {"Content-Type": "application/json"}
        api_key = agent_registry.get_agent_api_key(agent_id)
        if api_key:
            headers["X-API-Key"] = api_key
        return headers

    async def execute_command(
        self,
        agent_id: str,
        command: str,
        args: list,
        timeout: Optional[int] = None
    ) -> RemoteCommandResponse:
        """Execute a command on a remote agent.

        Args:
            agent_id: Target agent ID
            command: Command to execute
            args: Command arguments
            timeout: Optional timeout override

        Returns:
            RemoteCommandResponse with execution results
        """
        agent = agent_registry.get_agent(agent_id)
        if not agent:
            return RemoteCommandResponse(
                success=False,
                return_code=-1,
                error=f"Agent not found: {agent_id}"
            )

        if agent.status != "online":
            return RemoteCommandResponse(
                success=False,
                return_code=-1,
                error=f"Agent is offline: {agent_id}"
            )

        request = RemoteCommandRequest(
            command=command,
            args=args,
            timeout=timeout or self._timeout
        )

        url = f"{agent.api_url}/api/execute"
        headers = self._get_headers(agent_id)

        try:
            if not self._client:
                self._client = httpx.AsyncClient(timeout=self._timeout)

            response = await self._client.post(
                url,
                json=request.model_dump(),
                headers=headers
            )
            response.raise_for_status()

            result = RemoteCommandResponse(**response.json())
            logger.info(f"Command executed on agent {agent_id}: {command} {' '.join(args)}")
            return result

        except httpx.TimeoutException:
            logger.error(f"Timeout executing command on agent {agent_id}")
            return RemoteCommandResponse(
                success=False,
                return_code=-1,
                error=f"Request timeout to agent {agent_id}"
            )
        except httpx.HTTPError as e:
            logger.error(f"HTTP error communicating with agent {agent_id}: {e}")
            return RemoteCommandResponse(
                success=False,
                return_code=-1,
                error=f"HTTP error: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Error executing command on agent {agent_id}: {e}")
            return RemoteCommandResponse(
                success=False,
                return_code=-1,
                error=f"Unexpected error: {str(e)}"
            )

    async def get_vm_list(self, agent_id: str) -> Dict[str, Any]:
        """Get list of VMs from a remote agent.

        Args:
            agent_id: Target agent ID

        Returns:
            Dict with VM list or error
        """
        agent = agent_registry.get_agent(agent_id)
        if not agent:
            return {"error": f"Agent not found: {agent_id}"}

        url = f"{agent.api_url}/api/vm/list"
        headers = self._get_headers(agent_id)

        try:
            if not self._client:
                self._client = httpx.AsyncClient(timeout=self._timeout)

            response = await self._client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Error getting VM list from agent {agent_id}: {e}")
            return {"error": str(e)}

    async def get_vm_info(self, agent_id: str, vm_name: str) -> Dict[str, Any]:
        """Get VM info from a remote agent.

        Args:
            agent_id: Target agent ID
            vm_name: VM name

        Returns:
            Dict with VM info or error
        """
        agent = agent_registry.get_agent(agent_id)
        if not agent:
            return {"error": f"Agent not found: {agent_id}"}

        url = f"{agent.api_url}/api/vm/info/{vm_name}"
        headers = self._get_headers(agent_id)

        try:
            if not self._client:
                self._client = httpx.AsyncClient(timeout=self._timeout)

            response = await self._client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Error getting VM info from agent {agent_id}: {e}")
            return {"error": str(e)}

    async def create_vm(
        self,
        agent_id: str,
        name: str,
        cpus: int,
        memory: str,
        disk: str,
        image: str
    ) -> Dict[str, Any]:
        """Create a VM on a remote agent.

        Args:
            agent_id: Target agent ID
            name: VM name
            cpus: Number of CPUs
            memory: Memory size
            disk: Disk size
            image: OS image

        Returns:
            Dict with result or error
        """
        agent = agent_registry.get_agent(agent_id)
        if not agent:
            return {"error": f"Agent not found: {agent_id}"}

        url = f"{agent.api_url}/api/vm/create"
        headers = self._get_headers(agent_id)
        payload = {
            "name": name,
            "cpus": cpus,
            "memory": memory,
            "disk": disk,
            "image": image
        }

        try:
            if not self._client:
                self._client = httpx.AsyncClient(timeout=self._timeout)

            response = await self._client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Error creating VM on agent {agent_id}: {e}")
            return {"error": str(e)}

    async def vm_action(
        self,
        agent_id: str,
        vm_name: str,
        action: str
    ) -> Dict[str, Any]:
        """Perform an action on a VM (start/stop/delete).

        Args:
            agent_id: Target agent ID
            vm_name: VM name
            action: Action to perform (start, stop, delete)

        Returns:
            Dict with result or error
        """
        agent = agent_registry.get_agent(agent_id)
        if not agent:
            return {"error": f"Agent not found: {agent_id}"}

        url = f"{agent.api_url}/api/vm/{action}"
        headers = self._get_headers(agent_id)
        payload = {"name": vm_name}

        try:
            if not self._client:
                self._client = httpx.AsyncClient(timeout=self._timeout)

            response = await self._client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Error performing {action} on VM {vm_name} on agent {agent_id}: {e}")
            return {"error": str(e)}

    async def health_check(self, agent_id: str) -> bool:
        """Check health of a remote agent.

        Args:
            agent_id: Target agent ID

        Returns:
            True if agent is healthy, False otherwise
        """
        agent = agent_registry.get_agent(agent_id)
        if not agent:
            return False

        url = f"{agent.api_url}/health"
        headers = self._get_headers(agent_id)

        try:
            if not self._client:
                self._client = httpx.AsyncClient(timeout=5)

            response = await self._client.get(url, headers=headers)
            return response.status_code == 200

        except Exception as e:
            logger.debug(f"Health check failed for agent {agent_id}: {e}")
            return False


# Global communicator instance (will be properly initialized in app startup)
communicator = AgentCommunicator()