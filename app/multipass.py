"""Multipass VM management utilities."""
import json
import subprocess
from typing import List, Dict, Optional


def run_multipass_command(args: List[str]) -> Dict:
    """Run a multipass command and return the result."""
    try:
        result = subprocess.run(
            ["multipass"] + args,
            capture_output=True,
            text=True,
            check=True
        )
        return {"success": True, "output": result.stdout, "error": ""}
    except subprocess.CalledProcessError as e:
        return {"success": False, "output": e.stdout, "error": e.stderr}
    except FileNotFoundError:
        return {
            "success": False,
            "output": "",
            "error": "multipass command not found. Is multipass installed?"
        }


def get_vm_ip(vm_name: str) -> Optional[str]:
    """Get the IP address of a multipass VM."""
    result = run_multipass_command(["info", vm_name, "--format", "json"])
    if result["success"]:
        try:
            info = json.loads(result["output"])
            if vm_name in info["info"]:
                ipv4_list = info["info"][vm_name].get("ipv4", [])
                if ipv4_list:
                    return ipv4_list[0]
        except (json.JSONDecodeError, KeyError):
            pass
    return None
