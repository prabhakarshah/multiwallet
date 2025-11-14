"""Abstract executor for local and remote VM operations."""
from abc import ABC, abstractmethod
from typing import Dict, Optional, List
import json
import logging
from app.multipass import run_multipass_command, get_vm_ip
from app.communication import AgentCommunicator

logger = logging.getLogger(__name__)


class VMExecutor(ABC):
    """Abstract base class for VM executors."""

    @abstractmethod
    async def list_vms(self) -> Dict:
        """List all VMs."""
        pass

    @abstractmethod
    async def get_vm_info(self, vm_name: str) -> Dict:
        """Get information about a specific VM."""
        pass

    @abstractmethod
    async def create_vm(
        self,
        name: str,
        cpus: int,
        memory: str,
        disk: str,
        image: str
    ) -> Dict:
        """Create a new VM."""
        pass

    @abstractmethod
    async def start_vm(self, vm_name: str) -> Dict:
        """Start a VM."""
        pass

    @abstractmethod
    async def stop_vm(self, vm_name: str) -> Dict:
        """Stop a VM."""
        pass

    @abstractmethod
    async def delete_vm(self, vm_name: str) -> Dict:
        """Delete a VM."""
        pass

    @abstractmethod
    def get_location_info(self) -> Dict:
        """Get information about where VMs are located."""
        pass


class LocalVMExecutor(VMExecutor):
    """Executor for local multipass operations."""

    async def list_vms(self) -> Dict:
        """List all local VMs."""
        result = run_multipass_command(["list", "--format", "json"])
        if result["success"]:
            try:
                data = json.loads(result["output"])
                return {"success": True, "data": data}
            except json.JSONDecodeError as e:
                return {"success": False, "error": f"Failed to parse JSON: {str(e)}"}
        return {"success": False, "error": result["error"]}

    async def get_vm_info(self, vm_name: str) -> Dict:
        """Get information about a local VM."""
        result = run_multipass_command(["info", vm_name, "--format", "json"])
        if result["success"]:
            try:
                data = json.loads(result["output"])
                return {"success": True, "data": data}
            except json.JSONDecodeError as e:
                return {"success": False, "error": f"Failed to parse JSON: {str(e)}"}
        return {"success": False, "error": result["error"]}

    async def create_vm(
        self,
        name: str,
        cpus: int,
        memory: str,
        disk: str,
        image: str
    ) -> Dict:
        """Create a new local VM."""
        args = [
            "launch",
            image,
            "--name", name,
            "--cpus", str(cpus),
            "--memory", memory,
            "--disk", disk
        ]
        result = run_multipass_command(args)
        return {
            "success": result["success"],
            "message": result["output"] if result["success"] else result["error"]
        }

    async def start_vm(self, vm_name: str) -> Dict:
        """Start a local VM."""
        result = run_multipass_command(["start", vm_name])
        return {
            "success": result["success"],
            "message": result["output"] if result["success"] else result["error"]
        }

    async def stop_vm(self, vm_name: str) -> Dict:
        """Stop a local VM."""
        result = run_multipass_command(["stop", vm_name])
        return {
            "success": result["success"],
            "message": result["output"] if result["success"] else result["error"]
        }

    async def delete_vm(self, vm_name: str) -> Dict:
        """Delete a local VM."""
        # First delete, then purge
        result = run_multipass_command(["delete", vm_name])
        if result["success"]:
            purge_result = run_multipass_command(["purge"])
            return {
                "success": purge_result["success"],
                "message": "VM deleted and purged" if purge_result["success"] else purge_result["error"]
            }
        return {
            "success": False,
            "message": result["error"]
        }

    def get_location_info(self) -> Dict:
        """Get location information for local executor."""
        return {
            "type": "local",
            "agent_id": None,
            "agent_hostname": None
        }


class RemoteVMExecutor(VMExecutor):
    """Executor for remote multipass operations via agents."""

    def __init__(self, agent_id: str, communicator: AgentCommunicator):
        """Initialize remote executor.

        Args:
            agent_id: ID of the target agent
            communicator: Agent communicator instance
        """
        self.agent_id = agent_id
        self.communicator = communicator

    async def list_vms(self) -> Dict:
        """List all VMs on the remote agent."""
        result = await self.communicator.get_vm_list(self.agent_id)
        if "error" in result:
            return {"success": False, "error": result["error"]}
        return {"success": True, "data": result}

    async def get_vm_info(self, vm_name: str) -> Dict:
        """Get information about a VM on the remote agent."""
        result = await self.communicator.get_vm_info(self.agent_id, vm_name)
        if "error" in result:
            return {"success": False, "error": result["error"]}
        return {"success": True, "data": result}

    async def create_vm(
        self,
        name: str,
        cpus: int,
        memory: str,
        disk: str,
        image: str
    ) -> Dict:
        """Create a new VM on the remote agent."""
        result = await self.communicator.create_vm(
            self.agent_id, name, cpus, memory, disk, image
        )
        if "error" in result:
            return {"success": False, "message": result["error"]}
        return result

    async def start_vm(self, vm_name: str) -> Dict:
        """Start a VM on the remote agent."""
        result = await self.communicator.vm_action(self.agent_id, vm_name, "start")
        if "error" in result:
            return {"success": False, "message": result["error"]}
        return result

    async def stop_vm(self, vm_name: str) -> Dict:
        """Stop a VM on the remote agent."""
        result = await self.communicator.vm_action(self.agent_id, vm_name, "stop")
        if "error" in result:
            return {"success": False, "message": result["error"]}
        return result

    async def delete_vm(self, vm_name: str) -> Dict:
        """Delete a VM on the remote agent."""
        result = await self.communicator.vm_action(self.agent_id, vm_name, "delete")
        if "error" in result:
            return {"success": False, "message": result["error"]}
        return result

    def get_location_info(self) -> Dict:
        """Get location information for remote executor."""
        from app.agents import agent_registry
        agent = agent_registry.get_agent(self.agent_id)
        return {
            "type": "remote",
            "agent_id": self.agent_id,
            "agent_hostname": agent.hostname if agent else "unknown"
        }


class ExecutorFactory:
    """Factory for creating appropriate VM executors."""

    def __init__(self, communicator: AgentCommunicator):
        """Initialize the executor factory.

        Args:
            communicator: Agent communicator instance
        """
        self.communicator = communicator

    def get_executor(self, agent_id: Optional[str] = None) -> VMExecutor:
        """Get an appropriate executor based on agent_id.

        Args:
            agent_id: Target agent ID. If None, returns local executor.

        Returns:
            VMExecutor instance
        """
        if agent_id is None:
            logger.debug("Creating local VM executor")
            return LocalVMExecutor()
        else:
            logger.debug(f"Creating remote VM executor for agent: {agent_id}")
            return RemoteVMExecutor(agent_id, self.communicator)


# Global executor factory (will be properly initialized in app startup)
executor_factory: Optional[ExecutorFactory] = None


def get_executor_factory() -> ExecutorFactory:
    """Get the global executor factory instance."""
    global executor_factory
    if executor_factory is None:
        from app.communication import communicator
        executor_factory = ExecutorFactory(communicator)
    return executor_factory
