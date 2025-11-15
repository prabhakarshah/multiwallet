package multipass

import (
	"encoding/json"
	"os/exec"
	"strings"
)

// CommandResult represents the result of a multipass command
type CommandResult struct {
	Success bool   `json:"success"`
	Output  string `json:"output"`
	Error   string `json:"error"`
}

// RunMultipassCommand runs a multipass command and returns the result
func RunMultipassCommand(args []string) CommandResult {
	cmdArgs := append([]string{}, args...)
	cmd := exec.Command("multipass", cmdArgs...)

	output, err := cmd.CombinedOutput()
	outputStr := string(output)

	if err != nil {
		// Check if it's just because multipass isn't found
		if strings.Contains(err.Error(), "executable file not found") {
			return CommandResult{
				Success: false,
				Output:  "",
				Error:   "multipass command not found. Is multipass installed?",
			}
		}
		return CommandResult{
			Success: false,
			Output:  outputStr,
			Error:   err.Error(),
		}
	}

	return CommandResult{
		Success: true,
		Output:  outputStr,
		Error:   "",
	}
}

// VMListResponse represents the JSON response from multipass list
type VMListResponse struct {
	List []VMInfo `json:"list"`
}

// VMInfo represents information about a VM
type VMInfo struct {
	Name    string   `json:"name"`
	State   string   `json:"state"`
	IPv4    []string `json:"ipv4,omitempty"`
	Release string   `json:"release,omitempty"`
}

// GetVMIP gets the IP address of a multipass VM
func GetVMIP(vmName string) *string {
	result := RunMultipassCommand([]string{"info", vmName, "--format", "json"})
	if !result.Success {
		return nil
	}

	var info map[string]interface{}
	if err := json.Unmarshal([]byte(result.Output), &info); err != nil {
		return nil
	}

	infoMap, ok := info["info"].(map[string]interface{})
	if !ok {
		return nil
	}

	vmInfo, ok := infoMap[vmName].(map[string]interface{})
	if !ok {
		return nil
	}

	ipv4List, ok := vmInfo["ipv4"].([]interface{})
	if !ok || len(ipv4List) == 0 {
		return nil
	}

	ip, ok := ipv4List[0].(string)
	if !ok {
		return nil
	}

	return &ip
}
