package executor

import (
	"encoding/json"
	"fmt"
	"log"

	"github.com/prashah/batwa/pkg/agents"
	"github.com/prashah/batwa/pkg/communication"
	"github.com/prashah/batwa/pkg/multipass"
)

// VMExecutor is the interface for VM executors
type VMExecutor interface {
	ListVMs() (map[string]interface{}, error)
	GetVMInfo(vmName string) (map[string]interface{}, error)
	CreateVM(name string, cpus int, memory, disk, image string) (map[string]interface{}, error)
	StartVM(vmName string) (map[string]interface{}, error)
	StopVM(vmName string) (map[string]interface{}, error)
	DeleteVM(vmName string) (map[string]interface{}, error)
	GetLocationInfo() map[string]interface{}
}

// LocalVMExecutor executes VM operations locally
type LocalVMExecutor struct{}

// NewLocalVMExecutor creates a new local VM executor
func NewLocalVMExecutor() *LocalVMExecutor {
	return &LocalVMExecutor{}
}

// ListVMs lists all local VMs
func (e *LocalVMExecutor) ListVMs() (map[string]interface{}, error) {
	result := multipass.RunMultipassCommand([]string{"list", "--format", "json"})
	if !result.Success {
		return map[string]interface{}{
			"success": false,
			"error":   result.Error,
		}, fmt.Errorf(result.Error)
	}

	var data map[string]interface{}
	if err := json.Unmarshal([]byte(result.Output), &data); err != nil {
		return map[string]interface{}{
			"success": false,
			"error":   fmt.Sprintf("Failed to parse JSON: %s", err),
		}, err
	}

	return map[string]interface{}{
		"success": true,
		"data":    data,
	}, nil
}

// GetVMInfo gets information about a local VM
func (e *LocalVMExecutor) GetVMInfo(vmName string) (map[string]interface{}, error) {
	result := multipass.RunMultipassCommand([]string{"info", vmName, "--format", "json"})
	if !result.Success {
		return map[string]interface{}{
			"success": false,
			"error":   result.Error,
		}, fmt.Errorf(result.Error)
	}

	var data map[string]interface{}
	if err := json.Unmarshal([]byte(result.Output), &data); err != nil {
		return map[string]interface{}{
			"success": false,
			"error":   fmt.Sprintf("Failed to parse JSON: %s", err),
		}, err
	}

	return map[string]interface{}{
		"success": true,
		"data":    data,
	}, nil
}

// CreateVM creates a new local VM
func (e *LocalVMExecutor) CreateVM(name string, cpus int, memory, disk, image string) (map[string]interface{}, error) {
	args := []string{
		"launch",
		image,
		"--name", name,
		"--cpus", fmt.Sprintf("%d", cpus),
		"--memory", memory,
		"--disk", disk,
	}

	result := multipass.RunMultipassCommand(args)
	message := result.Output
	if !result.Success {
		message = result.Error
	}

	return map[string]interface{}{
		"success": result.Success,
		"message": message,
	}, nil
}

// StartVM starts a local VM
func (e *LocalVMExecutor) StartVM(vmName string) (map[string]interface{}, error) {
	result := multipass.RunMultipassCommand([]string{"start", vmName})
	message := result.Output
	if !result.Success {
		message = result.Error
	}

	return map[string]interface{}{
		"success": result.Success,
		"message": message,
	}, nil
}

// StopVM stops a local VM
func (e *LocalVMExecutor) StopVM(vmName string) (map[string]interface{}, error) {
	result := multipass.RunMultipassCommand([]string{"stop", vmName})
	message := result.Output
	if !result.Success {
		message = result.Error
	}

	return map[string]interface{}{
		"success": result.Success,
		"message": message,
	}, nil
}

// DeleteVM deletes a local VM
func (e *LocalVMExecutor) DeleteVM(vmName string) (map[string]interface{}, error) {
	result := multipass.RunMultipassCommand([]string{"delete", vmName})
	if !result.Success {
		return map[string]interface{}{
			"success": false,
			"message": result.Error,
		}, nil
	}

	purgeResult := multipass.RunMultipassCommand([]string{"purge"})
	message := "VM deleted and purged"
	if !purgeResult.Success {
		message = purgeResult.Error
	}

	return map[string]interface{}{
		"success": purgeResult.Success,
		"message": message,
	}, nil
}

// GetLocationInfo gets location information for local executor
func (e *LocalVMExecutor) GetLocationInfo() map[string]interface{} {
	return map[string]interface{}{
		"type":           "local",
		"agent_id":       nil,
		"agent_hostname": nil,
	}
}

// RemoteVMExecutor executes VM operations on remote agents
type RemoteVMExecutor struct {
	agentID       string
	communicator  *communication.AgentCommunicator
}

// NewRemoteVMExecutor creates a new remote VM executor
func NewRemoteVMExecutor(agentID string, communicator *communication.AgentCommunicator) *RemoteVMExecutor {
	return &RemoteVMExecutor{
		agentID:      agentID,
		communicator: communicator,
	}
}

// ListVMs lists all VMs on the remote agent
func (e *RemoteVMExecutor) ListVMs() (map[string]interface{}, error) {
	result, err := e.communicator.GetVMList(e.agentID)
	if err != nil {
		return map[string]interface{}{
			"success": false,
			"error":   err.Error(),
		}, err
	}

	return map[string]interface{}{
		"success": true,
		"data":    result,
	}, nil
}

// GetVMInfo gets information about a VM on the remote agent
func (e *RemoteVMExecutor) GetVMInfo(vmName string) (map[string]interface{}, error) {
	result, err := e.communicator.GetVMInfo(e.agentID, vmName)
	if err != nil {
		return map[string]interface{}{
			"success": false,
			"error":   err.Error(),
		}, err
	}

	return map[string]interface{}{
		"success": true,
		"data":    result,
	}, nil
}

// CreateVM creates a new VM on the remote agent
func (e *RemoteVMExecutor) CreateVM(name string, cpus int, memory, disk, image string) (map[string]interface{}, error) {
	result, err := e.communicator.CreateVM(e.agentID, name, cpus, memory, disk, image)
	if err != nil {
		return map[string]interface{}{
			"success": false,
			"message": err.Error(),
		}, err
	}

	return result, nil
}

// StartVM starts a VM on the remote agent
func (e *RemoteVMExecutor) StartVM(vmName string) (map[string]interface{}, error) {
	result, err := e.communicator.VMAction(e.agentID, vmName, "start")
	if err != nil {
		return map[string]interface{}{
			"success": false,
			"message": err.Error(),
		}, err
	}

	return result, nil
}

// StopVM stops a VM on the remote agent
func (e *RemoteVMExecutor) StopVM(vmName string) (map[string]interface{}, error) {
	result, err := e.communicator.VMAction(e.agentID, vmName, "stop")
	if err != nil {
		return map[string]interface{}{
			"success": false,
			"message": err.Error(),
		}, err
	}

	return result, nil
}

// DeleteVM deletes a VM on the remote agent
func (e *RemoteVMExecutor) DeleteVM(vmName string) (map[string]interface{}, error) {
	result, err := e.communicator.VMAction(e.agentID, vmName, "delete")
	if err != nil {
		return map[string]interface{}{
			"success": false,
			"message": err.Error(),
		}, err
	}

	return result, nil
}

// GetLocationInfo gets location information for remote executor
func (e *RemoteVMExecutor) GetLocationInfo() map[string]interface{} {
	agent := agents.GlobalRegistry.GetAgent(e.agentID)
	hostname := "unknown"
	if agent != nil {
		hostname = agent.Hostname
	}

	return map[string]interface{}{
		"type":           "remote",
		"agent_id":       e.agentID,
		"agent_hostname": hostname,
	}
}

// ExecutorFactory creates appropriate VM executors
type ExecutorFactory struct {
	communicator *communication.AgentCommunicator
}

// NewExecutorFactory creates a new executor factory
func NewExecutorFactory(communicator *communication.AgentCommunicator) *ExecutorFactory {
	return &ExecutorFactory{
		communicator: communicator,
	}
}

// GetExecutor gets an appropriate executor based on agent_id
func (f *ExecutorFactory) GetExecutor(agentID *string) VMExecutor {
	if agentID == nil {
		log.Println("Creating local VM executor")
		return NewLocalVMExecutor()
	}

	log.Printf("Creating remote VM executor for agent: %s", *agentID)
	return NewRemoteVMExecutor(*agentID, f.communicator)
}

// GlobalExecutorFactory is the global executor factory instance
var GlobalExecutorFactory = NewExecutorFactory(communication.GlobalCommunicator)
