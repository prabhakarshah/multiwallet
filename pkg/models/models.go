package models

import "time"

// LoginRequest represents a login request
type LoginRequest struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

// VMCreateRequest represents a VM creation request
type VMCreateRequest struct {
	Name    string  `json:"name"`
	CPUs    int     `json:"cpus"`
	Memory  string  `json:"memory"`
	Disk    string  `json:"disk"`
	Image   string  `json:"image"`
	AgentID *string `json:"agent_id,omitempty"`
}

// VMActionRequest represents a VM action request (start, stop, delete)
type VMActionRequest struct {
	Name    string  `json:"name"`
	AgentID *string `json:"agent_id,omitempty"`
}

// AgentRegisterRequest represents an agent registration request
type AgentRegisterRequest struct {
	AgentID  string            `json:"agent_id"`
	Hostname string            `json:"hostname"`
	APIURL   string            `json:"api_url"`
	APIKey   *string           `json:"api_key,omitempty"`
	Tags     map[string]string `json:"tags,omitempty"`
}

// AgentInfo represents agent information
type AgentInfo struct {
	AgentID      string            `json:"agent_id"`
	Hostname     string            `json:"hostname"`
	APIURL       string            `json:"api_url"`
	Status       string            `json:"status"`
	LastSeen     *time.Time        `json:"last_seen,omitempty"`
	Tags         map[string]string `json:"tags,omitempty"`
	VMCount      int               `json:"vm_count"`
}

// AgentHeartbeat represents an agent heartbeat
type AgentHeartbeat struct {
	AgentID   string    `json:"agent_id"`
	Timestamp time.Time `json:"timestamp"`
	Status    string    `json:"status"`
	VMCount   int       `json:"vm_count"`
}

// RemoteCommandRequest represents a remote command execution request
type RemoteCommandRequest struct {
	Command string   `json:"command"`
	Args    []string `json:"args"`
	Timeout int      `json:"timeout"`
}

// RemoteCommandResponse represents a remote command execution response
type RemoteCommandResponse struct {
	Success    bool    `json:"success"`
	Stdout     *string `json:"stdout,omitempty"`
	Stderr     *string `json:"stderr,omitempty"`
	ReturnCode int     `json:"return_code"`
	Error      *string `json:"error,omitempty"`
}

// VMInfoExtended represents extended VM info with agent information
type VMInfoExtended struct {
	Name          string   `json:"name"`
	State         string   `json:"state"`
	IPv4          []string `json:"ipv4,omitempty"`
	Release       string   `json:"release,omitempty"`
	AgentID       *string  `json:"agent_id,omitempty"`
	AgentHostname *string  `json:"agent_hostname,omitempty"`
}

// Session represents a user session
type Session struct {
	Username string `json:"username"`
}
