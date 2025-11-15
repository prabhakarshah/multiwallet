package agents

import (
	"context"
	"log"
	"strings"
	"sync"
	"time"

	"github.com/prashah/batwa/pkg/models"
)

// AgentRegistry manages remote agents
type AgentRegistry struct {
	agents            map[string]*models.AgentInfo
	apiKeys           map[string]string
	mutex             sync.RWMutex
	heartbeatInterval time.Duration
	offlineThreshold  time.Duration
	cancelFunc        context.CancelFunc
	ctx               context.Context
}

// NewAgentRegistry creates a new agent registry
func NewAgentRegistry() *AgentRegistry {
	return &AgentRegistry{
		agents:            make(map[string]*models.AgentInfo),
		apiKeys:           make(map[string]string),
		heartbeatInterval: 30 * time.Second,
		offlineThreshold:  60 * time.Second,
	}
}

// RegisterAgent registers a new agent or updates an existing one
func (r *AgentRegistry) RegisterAgent(req models.AgentRegisterRequest) *models.AgentInfo {
	r.mutex.Lock()
	defer r.mutex.Unlock()

	now := time.Now()
	agentInfo := &models.AgentInfo{
		AgentID:  req.AgentID,
		Hostname: req.Hostname,
		APIURL:   strings.TrimSuffix(req.APIURL, "/"),
		Status:   "online",
		LastSeen: &now,
		Tags:     req.Tags,
		VMCount:  0,
	}

	r.agents[req.AgentID] = agentInfo

	if req.APIKey != nil {
		r.apiKeys[req.AgentID] = *req.APIKey
	}

	log.Printf("Registered agent: %s (%s)", req.AgentID, req.Hostname)
	return agentInfo
}

// UnregisterAgent unregisters an agent
func (r *AgentRegistry) UnregisterAgent(agentID string) bool {
	r.mutex.Lock()
	defer r.mutex.Unlock()

	if _, exists := r.agents[agentID]; exists {
		delete(r.agents, agentID)
		delete(r.apiKeys, agentID)
		log.Printf("Unregistered agent: %s", agentID)
		return true
	}
	return false
}

// GetAgent gets agent information by ID
func (r *AgentRegistry) GetAgent(agentID string) *models.AgentInfo {
	r.mutex.RLock()
	defer r.mutex.RUnlock()
	return r.agents[agentID]
}

// GetAllAgents gets all registered agents
func (r *AgentRegistry) GetAllAgents() []*models.AgentInfo {
	r.mutex.RLock()
	defer r.mutex.RUnlock()

	agents := make([]*models.AgentInfo, 0, len(r.agents))
	for _, agent := range r.agents {
		agents = append(agents, agent)
	}
	return agents
}

// GetOnlineAgents gets all online agents
func (r *AgentRegistry) GetOnlineAgents() []*models.AgentInfo {
	r.mutex.RLock()
	defer r.mutex.RUnlock()

	agents := make([]*models.AgentInfo, 0)
	for _, agent := range r.agents {
		if agent.Status == "online" {
			agents = append(agents, agent)
		}
	}
	return agents
}

// GetAgentAPIKey gets API key for an agent
func (r *AgentRegistry) GetAgentAPIKey(agentID string) *string {
	r.mutex.RLock()
	defer r.mutex.RUnlock()

	if key, exists := r.apiKeys[agentID]; exists {
		return &key
	}
	return nil
}

// UpdateHeartbeat updates agent heartbeat
func (r *AgentRegistry) UpdateHeartbeat(heartbeat models.AgentHeartbeat) {
	r.mutex.Lock()
	defer r.mutex.Unlock()

	if agent, exists := r.agents[heartbeat.AgentID]; exists {
		agent.LastSeen = &heartbeat.Timestamp
		agent.Status = heartbeat.Status
		agent.VMCount = heartbeat.VMCount
		log.Printf("Heartbeat updated for agent: %s", heartbeat.AgentID)
	}
}

// UpdateVMCount updates VM count for an agent
func (r *AgentRegistry) UpdateVMCount(agentID string, count int) {
	r.mutex.Lock()
	defer r.mutex.Unlock()

	if agent, exists := r.agents[agentID]; exists {
		agent.VMCount = count
	}
}

// CheckAgentStatus checks and updates status of all agents based on last_seen
func (r *AgentRegistry) CheckAgentStatus() {
	r.mutex.Lock()
	defer r.mutex.Unlock()

	now := time.Now()
	for _, agent := range r.agents {
		if agent.LastSeen != nil {
			timeSinceLastSeen := now.Sub(*agent.LastSeen)
			if timeSinceLastSeen > r.offlineThreshold {
				if agent.Status != "offline" {
					agent.Status = "offline"
					log.Printf("Agent %s is now offline", agent.AgentID)
				}
			} else {
				if agent.Status == "offline" {
					agent.Status = "online"
					log.Printf("Agent %s is back online", agent.AgentID)
				}
			}
		}
	}
}

// StartHeartbeatMonitor starts the heartbeat monitoring task
func (r *AgentRegistry) StartHeartbeatMonitor() {
	ctx, cancel := context.WithCancel(context.Background())
	r.ctx = ctx
	r.cancelFunc = cancel

	go r.heartbeatLoop()
	log.Println("Started agent heartbeat monitor")
}

// StopHeartbeatMonitor stops the heartbeat monitoring task
func (r *AgentRegistry) StopHeartbeatMonitor() {
	if r.cancelFunc != nil {
		r.cancelFunc()
		log.Println("Stopped agent heartbeat monitor")
	}
}

// heartbeatLoop is the periodic heartbeat monitoring loop
func (r *AgentRegistry) heartbeatLoop() {
	ticker := time.NewTicker(r.heartbeatInterval)
	defer ticker.Stop()

	for {
		select {
		case <-r.ctx.Done():
			return
		case <-ticker.C:
			r.CheckAgentStatus()
		}
	}
}

// Global agent registry instance
var GlobalRegistry = NewAgentRegistry()
