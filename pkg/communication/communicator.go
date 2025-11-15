package communication

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"time"

	"github.com/prashah/batwa/pkg/agents"
	"github.com/prashah/batwa/pkg/models"
)

// AgentCommunicator handles communication with remote agents
type AgentCommunicator struct {
	timeout time.Duration
	client  *http.Client
}

// NewAgentCommunicator creates a new agent communicator
func NewAgentCommunicator(timeout time.Duration) *AgentCommunicator {
	return &AgentCommunicator{
		timeout: timeout,
		client: &http.Client{
			Timeout: timeout,
		},
	}
}

// getHeaders gets headers for agent requests
func (c *AgentCommunicator) getHeaders(agentID string) map[string]string {
	headers := map[string]string{
		"Content-Type": "application/json",
	}

	apiKey := agents.GlobalRegistry.GetAgentAPIKey(agentID)
	if apiKey != nil {
		headers["X-API-Key"] = *apiKey
	}

	return headers
}

// ExecuteCommand executes a command on a remote agent
func (c *AgentCommunicator) ExecuteCommand(agentID, command string, args []string, timeout *int) models.RemoteCommandResponse {
	agent := agents.GlobalRegistry.GetAgent(agentID)
	if agent == nil {
		errMsg := fmt.Sprintf("Agent not found: %s", agentID)
		return models.RemoteCommandResponse{
			Success:    false,
			ReturnCode: -1,
			Error:      &errMsg,
		}
	}

	if agent.Status != "online" {
		errMsg := fmt.Sprintf("Agent is offline: %s", agentID)
		return models.RemoteCommandResponse{
			Success:    false,
			ReturnCode: -1,
			Error:      &errMsg,
		}
	}

	cmdTimeout := int(c.timeout.Seconds())
	if timeout != nil {
		cmdTimeout = *timeout
	}

	request := models.RemoteCommandRequest{
		Command: command,
		Args:    args,
		Timeout: cmdTimeout,
	}

	url := fmt.Sprintf("%s/api/execute", agent.APIURL)
	headers := c.getHeaders(agentID)

	body, err := json.Marshal(request)
	if err != nil {
		errMsg := fmt.Sprintf("Failed to marshal request: %s", err)
		return models.RemoteCommandResponse{
			Success:    false,
			ReturnCode: -1,
			Error:      &errMsg,
		}
	}

	req, err := http.NewRequest("POST", url, bytes.NewBuffer(body))
	if err != nil {
		errMsg := fmt.Sprintf("Failed to create request: %s", err)
		return models.RemoteCommandResponse{
			Success:    false,
			ReturnCode: -1,
			Error:      &errMsg,
		}
	}

	for k, v := range headers {
		req.Header.Set(k, v)
	}

	resp, err := c.client.Do(req)
	if err != nil {
		errMsg := fmt.Sprintf("Request error: %s", err)
		return models.RemoteCommandResponse{
			Success:    false,
			ReturnCode: -1,
			Error:      &errMsg,
		}
	}
	defer resp.Body.Close()

	var result models.RemoteCommandResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		errMsg := fmt.Sprintf("Failed to decode response: %s", err)
		return models.RemoteCommandResponse{
			Success:    false,
			ReturnCode: -1,
			Error:      &errMsg,
		}
	}

	log.Printf("Command executed on agent %s: %s %v", agentID, command, args)
	return result
}

// GetVMList gets list of VMs from a remote agent
func (c *AgentCommunicator) GetVMList(agentID string) (map[string]interface{}, error) {
	agent := agents.GlobalRegistry.GetAgent(agentID)
	if agent == nil {
		return nil, fmt.Errorf("agent not found: %s", agentID)
	}

	url := fmt.Sprintf("%s/api/vm/list", agent.APIURL)
	log.Printf("Fetching VM list from agent %s at %s", agentID, url)
	headers := c.getHeaders(agentID)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		log.Printf("Failed to create request for agent %s: %v", agentID, err)
		return nil, err
	}

	for k, v := range headers {
		req.Header.Set(k, v)
	}

	resp, err := c.client.Do(req)
	if err != nil {
		log.Printf("Failed to connect to agent %s: %v", agentID, err)
		return nil, err
	}
	defer resp.Body.Close()

	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		log.Printf("Failed to decode response from agent %s: %v", agentID, err)
		return nil, err
	}

	log.Printf("Successfully fetched VM list from agent %s", agentID)
	return result, nil
}

// GetVMInfo gets VM info from a remote agent
func (c *AgentCommunicator) GetVMInfo(agentID, vmName string) (map[string]interface{}, error) {
	agent := agents.GlobalRegistry.GetAgent(agentID)
	if agent == nil {
		return nil, fmt.Errorf("agent not found: %s", agentID)
	}

	url := fmt.Sprintf("%s/api/vm/info/%s", agent.APIURL, vmName)
	headers := c.getHeaders(agentID)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}

	for k, v := range headers {
		req.Header.Set(k, v)
	}

	resp, err := c.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}

	return result, nil
}

// CreateVM creates a VM on a remote agent
func (c *AgentCommunicator) CreateVM(agentID, name string, cpus int, memory, disk, image string) (map[string]interface{}, error) {
	agent := agents.GlobalRegistry.GetAgent(agentID)
	if agent == nil {
		return nil, fmt.Errorf("agent not found: %s", agentID)
	}

	url := fmt.Sprintf("%s/api/vm/create", agent.APIURL)
	headers := c.getHeaders(agentID)

	payload := models.VMCreateRequest{
		Name:   name,
		CPUs:   cpus,
		Memory: memory,
		Disk:   disk,
		Image:  image,
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}

	req, err := http.NewRequest("POST", url, bytes.NewBuffer(body))
	if err != nil {
		return nil, err
	}

	for k, v := range headers {
		req.Header.Set(k, v)
	}

	resp, err := c.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}

	return result, nil
}

// VMAction performs an action on a VM (start/stop/delete)
func (c *AgentCommunicator) VMAction(agentID, vmName, action string) (map[string]interface{}, error) {
	agent := agents.GlobalRegistry.GetAgent(agentID)
	if agent == nil {
		return nil, fmt.Errorf("agent not found: %s", agentID)
	}

	url := fmt.Sprintf("%s/api/vm/%s", agent.APIURL, action)
	headers := c.getHeaders(agentID)

	payload := models.VMActionRequest{
		Name: vmName,
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}

	req, err := http.NewRequest("POST", url, bytes.NewBuffer(body))
	if err != nil {
		return nil, err
	}

	for k, v := range headers {
		req.Header.Set(k, v)
	}

	resp, err := c.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}

	return result, nil
}

// HealthCheck checks health of a remote agent
func (c *AgentCommunicator) HealthCheck(agentID string) bool {
	agent := agents.GlobalRegistry.GetAgent(agentID)
	if agent == nil {
		return false
	}

	url := fmt.Sprintf("%s/health", agent.APIURL)
	headers := c.getHeaders(agentID)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return false
	}

	for k, v := range headers {
		req.Header.Set(k, v)
	}

	// Use a shorter timeout for health checks
	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		log.Printf("Health check failed for agent %s: %v", agentID, err)
		return false
	}
	defer resp.Body.Close()
	io.Copy(io.Discard, resp.Body)

	return resp.StatusCode == 200
}

// Global communicator instance
var GlobalCommunicator = NewAgentCommunicator(30 * time.Second)
