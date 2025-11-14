"""Agent-side executor for local multipass operations."""
import json
import subprocess
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class AgentExecutor:
    """Executes multipass commands on the agent machine."""

    def run_multipass_command(self, args: List[str]) -> Dict:
        """Run a multipass command and return the result.

        Args:
            args: List of arguments for multipass command

        Returns:
            Dict with success status, output, and error
        """
        try:
            logger.debug(f"Executing multipass command: {' '.join(args)}")
            result = subprocess.run(
                ["multipass"] + args,
                capture_output=True,
                text=True,
                check=True,
                timeout=300  # 5 minute timeout
            )
            return {"success": True, "output": result.stdout, "error": ""}
        except subprocess.CalledProcessError as e:
            logger.error(f"Multipass command failed: {e.stderr}")
            return {"success": False, "output": e.stdout, "error": e.stderr}
        except subprocess.TimeoutExpired:
            logger.error("Multipass command timed out")
            return {
                "success": False,
                "output": "",
                "error": "Command timed out after 5 minutes"
            }
        except FileNotFoundError:
            logger.error("Multipass command not found")
            return {
                "success": False,
                "output": "",
                "error": "multipass command not found. Is multipass installed?"
            }

    def list_vms(self) -> Dict:
        """List all VMs on this agent.

        Returns:
            Dict with VM list data or error
        """
        result = self.run_multipass_command(["list", "--format", "json"])
        if result["success"]:
            try:
                data = json.loads(result["output"])
                return data
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse VM list JSON: {e}")
                return {"error": f"Failed to parse JSON: {str(e)}"}
        return {"error": result["error"]}

    def get_vm_info(self, vm_name: str) -> Dict:
        """Get information about a specific VM.

        Args:
            vm_name: Name of the VM

        Returns:
            Dict with VM info or error
        """
        result = self.run_multipass_command(["info", vm_name, "--format", "json"])
        if result["success"]:
            try:
                data = json.loads(result["output"])
                return data
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse VM info JSON: {e}")
                return {"error": f"Failed to parse JSON: {str(e)}"}
        return {"error": result["error"]}

    def create_vm(
        self,
        name: str,
        cpus: int,
        memory: str,
        disk: str,
        image: str
    ) -> Dict:
        """Create a new VM.

        Args:
            name: VM name
            cpus: Number of CPUs
            memory: Memory size (e.g., "1G")
            disk: Disk size (e.g., "5G")
            image: OS image version

        Returns:
            Dict with success status and message
        """
        args = [
            "launch",
            image,
            "--name", name,
            "--cpus", str(cpus),
            "--memory", memory,
            "--disk", disk
        ]
        result = self.run_multipass_command(args)
        return {
            "success": result["success"],
            "message": result["output"] if result["success"] else result["error"]
        }

    def start_vm(self, vm_name: str) -> Dict:
        """Start a VM.

        Args:
            vm_name: Name of the VM

        Returns:
            Dict with success status and message
        """
        result = self.run_multipass_command(["start", vm_name])
        return {
            "success": result["success"],
            "message": result["output"] if result["success"] else result["error"]
        }

    def stop_vm(self, vm_name: str) -> Dict:
        """Stop a VM.

        Args:
            vm_name: Name of the VM

        Returns:
            Dict with success status and message
        """
        result = self.run_multipass_command(["stop", vm_name])
        return {
            "success": result["success"],
            "message": result["output"] if result["success"] else result["error"]
        }

    def delete_vm(self, vm_name: str) -> Dict:
        """Delete a VM.

        Args:
            vm_name: Name of the VM

        Returns:
            Dict with success status and message
        """
        # First delete, then purge
        result = self.run_multipass_command(["delete", vm_name])
        if result["success"]:
            purge_result = self.run_multipass_command(["purge"])
            return {
                "success": purge_result["success"],
                "message": "VM deleted and purged" if purge_result["success"] else purge_result["error"]
            }
        return {
            "success": False,
            "message": result["error"]
        }

    def execute_shell_command(self, vm_name: str, command: str) -> Dict:
        """Execute a shell command in a VM.

        Args:
            vm_name: Name of the VM
            command: Command to execute

        Returns:
            Dict with success status, stdout, stderr, and return code
        """
        result = self.run_multipass_command(["exec", vm_name, "--", "sh", "-c", command])
        return {
            "success": result["success"],
            "stdout": result["output"],
            "stderr": result["error"],
            "return_code": 0 if result["success"] else 1
        }
