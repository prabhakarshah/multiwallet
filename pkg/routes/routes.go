package routes

import (
	"crypto/rand"
	"encoding/base64"
	"fmt"
	"log"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/prashah/batwa/pkg/agents"
	"github.com/prashah/batwa/pkg/auth"
	"github.com/prashah/batwa/pkg/executor"
	"github.com/prashah/batwa/pkg/models"
)

// generateSessionID generates a random session ID
func generateSessionID() (string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return base64.URLEncoding.EncodeToString(b), nil
}

// SetupRoutes sets up all the routes for the application
func SetupRoutes(app *fiber.App) {
	// Authentication Routes
	app.Post("/api/auth/login", Login)
	app.Post("/api/auth/logout", Logout)
	app.Get("/api/auth/check", CheckAuth)

	// Agent Management Routes
	app.Post("/api/agent/register", RegisterAgent)
	app.Delete("/api/agent/unregister/:agent_id", UnregisterAgent)
	app.Get("/api/agent/list", ListAgents)
	app.Get("/api/agent/info/:agent_id", GetAgentInfo)
	app.Post("/api/agent/heartbeat", AgentHeartbeat)

	// VM Management Routes
	app.Post("/api/vm/create", CreateVM)
	app.Get("/api/vm/list", ListVMs)
	app.Get("/api/vm/info/:vm_name", GetVMInfo)
	app.Post("/api/vm/start", StartVM)
	app.Post("/api/vm/stop", StopVM)
	app.Post("/api/vm/delete", DeleteVM)
}

// ==================== Authentication Routes ====================

// Login handles user login
func Login(c *fiber.Ctx) error {
	var req models.LoginRequest
	if err := c.BodyParser(&req); err != nil {
		return c.Status(400).JSON(fiber.Map{"error": "Invalid request"})
	}

	password, exists := auth.Users[req.Username]
	if !exists || password != req.Password {
		return c.Status(401).JSON(fiber.Map{"detail": "Invalid credentials"})
	}

	// Create session
	sessionID, err := generateSessionID()
	if err != nil {
		return c.Status(500).JSON(fiber.Map{"error": "Failed to create session"})
	}

	auth.SetSession(sessionID, &models.Session{Username: req.Username})

	// Set cookie
	c.Cookie(&fiber.Cookie{
		Name:     "session_id",
		Value:    sessionID,
		HTTPOnly: true,
		SameSite: "Lax",
		MaxAge:   86400, // 24 hours
	})

	return c.JSON(fiber.Map{
		"success": true,
		"message": "Login successful",
	})
}

// Logout handles user logout
func Logout(c *fiber.Ctx) error {
	sessionID := c.Cookies("session_id")
	if sessionID != "" {
		auth.DeleteSession(sessionID)
	}

	c.ClearCookie("session_id")
	return c.JSON(fiber.Map{
		"success": true,
		"message": "Logged out",
	})
}

// CheckAuth checks if user is authenticated
func CheckAuth(c *fiber.Ctx) error {
	sessionID := c.Cookies("session_id")
	if auth.CheckAuth(sessionID) {
		session, _ := auth.GetSession(sessionID)
		return c.JSON(fiber.Map{
			"authenticated": true,
			"username":      session.Username,
		})
	}

	return c.JSON(fiber.Map{
		"authenticated": false,
	})
}

// ==================== Agent Management Routes ====================

// RegisterAgent registers a new agent
func RegisterAgent(c *fiber.Ctx) error {
	var req models.AgentRegisterRequest
	if err := c.BodyParser(&req); err != nil {
		return c.Status(400).JSON(fiber.Map{"error": "Invalid request"})
	}

	agentInfo := agents.GlobalRegistry.RegisterAgent(req)

	return c.JSON(fiber.Map{
		"success": true,
		"message": fmt.Sprintf("Agent '%s' registered successfully", req.AgentID),
		"agent":   agentInfo,
	})
}

// UnregisterAgent unregisters an agent
func UnregisterAgent(c *fiber.Ctx) error {
	sessionID := c.Cookies("session_id")
	if !auth.CheckAuth(sessionID) {
		return c.Status(401).JSON(fiber.Map{"detail": "Not authenticated"})
	}

	agentID := c.Params("agent_id")
	success := agents.GlobalRegistry.UnregisterAgent(agentID)

	if success {
		return c.JSON(fiber.Map{
			"success": true,
			"message": fmt.Sprintf("Agent '%s' unregistered successfully", agentID),
		})
	}

	return c.Status(404).JSON(fiber.Map{"detail": fmt.Sprintf("Agent '%s' not found", agentID)})
}

// ListAgents lists all registered agents
func ListAgents(c *fiber.Ctx) error {
	sessionID := c.Cookies("session_id")
	if !auth.CheckAuth(sessionID) {
		return c.Status(401).JSON(fiber.Map{"detail": "Not authenticated"})
	}

	agentsList := agents.GlobalRegistry.GetAllAgents()
	return c.JSON(agentsList)
}

// GetAgentInfo gets information about a specific agent
func GetAgentInfo(c *fiber.Ctx) error {
	sessionID := c.Cookies("session_id")
	if !auth.CheckAuth(sessionID) {
		return c.Status(401).JSON(fiber.Map{"detail": "Not authenticated"})
	}

	agentID := c.Params("agent_id")
	agent := agents.GlobalRegistry.GetAgent(agentID)

	if agent != nil {
		return c.JSON(fiber.Map{
			"success": true,
			"agent":   agent,
		})
	}

	return c.Status(404).JSON(fiber.Map{"detail": fmt.Sprintf("Agent '%s' not found", agentID)})
}

// AgentHeartbeat receives heartbeat from an agent
func AgentHeartbeat(c *fiber.Ctx) error {
	var heartbeat models.AgentHeartbeat
	if err := c.BodyParser(&heartbeat); err != nil {
		return c.Status(400).JSON(fiber.Map{"error": "Invalid request"})
	}

	// Get client IP for auto-registration
	clientIP := c.IP()

	agents.GlobalRegistry.UpdateHeartbeatWithIP(heartbeat, clientIP)
	return c.JSON(fiber.Map{
		"success": true,
		"message": "Heartbeat received",
	})
}

// ==================== VM Management Routes ====================

// CreateVM creates a new multipass VM (local or remote)
func CreateVM(c *fiber.Ctx) error {
	sessionID := c.Cookies("session_id")
	if !auth.CheckAuth(sessionID) {
		return c.Status(401).JSON(fiber.Map{"detail": "Not authenticated"})
	}

	var req models.VMCreateRequest
	if err := c.BodyParser(&req); err != nil {
		return c.Status(400).JSON(fiber.Map{"error": "Invalid request"})
	}

	// Set defaults
	if req.CPUs == 0 {
		req.CPUs = 1
	}
	if req.Memory == "" {
		req.Memory = "1G"
	}
	if req.Disk == "" {
		req.Disk = "5G"
	}
	if req.Image == "" {
		req.Image = "22.04"
	}

	// Get the appropriate executor
	exec := executor.GlobalExecutorFactory.GetExecutor(req.AgentID)

	// Create VM using executor
	result, _ := exec.CreateVM(req.Name, req.CPUs, req.Memory, req.Disk, req.Image)

	if success, ok := result["success"].(bool); ok && success {
		// Wait a moment for VM to initialize
		time.Sleep(2 * time.Second)

		// Get location info
		location := exec.GetLocationInfo()

		return c.JSON(fiber.Map{
			"success":        true,
			"message":        result["message"],
			"vm_name":        req.Name,
			"agent_id":       location["agent_id"],
			"agent_hostname": location["agent_hostname"],
		})
	}

	message := "Failed to create VM"
	if msg, ok := result["message"].(string); ok {
		message = msg
	}
	return c.Status(500).JSON(fiber.Map{"detail": message})
}

// ListVMs lists all multipass VMs (from local and all agents)
func ListVMs(c *fiber.Ctx) error {
	sessionID := c.Cookies("session_id")
	if !auth.CheckAuth(sessionID) {
		return c.Status(401).JSON(fiber.Map{"detail": "Not authenticated"})
	}

	allVMs := []map[string]interface{}{}

	// Get local VMs
	localExecutor := executor.GlobalExecutorFactory.GetExecutor(nil)
	result, err := localExecutor.ListVMs()
	if err == nil {
		if success, ok := result["success"].(bool); ok && success {
			if data, ok := result["data"].(map[string]interface{}); ok {
				if list, ok := data["list"].([]interface{}); ok {
					for _, vm := range list {
						if vmMap, ok := vm.(map[string]interface{}); ok {
							allVMs = append(allVMs, map[string]interface{}{
								"name":           vmMap["name"],
								"state":          vmMap["state"],
								"ipv4":           vmMap["ipv4"],
								"release":        vmMap["release"],
								"agent_id":       nil,
								"agent_hostname": "local",
							})
						}
					}
				}
			}
		}
	}

	// Get VMs from all online agents
	agentsList := agents.GlobalRegistry.GetOnlineAgents()
	for _, agent := range agentsList {
		agentID := agent.AgentID
		agentExecutor := executor.GlobalExecutorFactory.GetExecutor(&agentID)
		result, err := agentExecutor.ListVMs()
		if err == nil {
			if success, ok := result["success"].(bool); ok && success {
				if data, ok := result["data"].(map[string]interface{}); ok {
					if list, ok := data["list"].([]interface{}); ok {
						for _, vm := range list {
							if vmMap, ok := vm.(map[string]interface{}); ok {
								allVMs = append(allVMs, map[string]interface{}{
									"name":           vmMap["name"],
									"state":          vmMap["state"],
									"ipv4":           vmMap["ipv4"],
									"release":        vmMap["release"],
									"agent_id":       agent.AgentID,
									"agent_hostname": agent.Hostname,
								})
							}
						}
					}
				}
			}
		}
	}

	return c.JSON(fiber.Map{
		"success": true,
		"vms":     allVMs,
	})
}

// GetVMInfo gets detailed info about a specific VM
func GetVMInfo(c *fiber.Ctx) error {
	sessionID := c.Cookies("session_id")
	if !auth.CheckAuth(sessionID) {
		return c.Status(401).JSON(fiber.Map{"detail": "Not authenticated"})
	}

	vmName := c.Params("vm_name")
	agentID := c.Query("agent_id")

	// Create executor based on agent_id
	var vmExecutor executor.VMExecutor
	if agentID != "" {
		log.Printf("Getting VM info for %s from agent %s", vmName, agentID)
		vmExecutor = executor.GlobalExecutorFactory.GetExecutor(&agentID)
	} else {
		log.Printf("Getting local VM info for %s", vmName)
		vmExecutor = executor.GlobalExecutorFactory.GetExecutor(nil)
	}

	result, err := vmExecutor.GetVMInfo(vmName)
	if err != nil {
		log.Printf("Error getting VM info for %s: %v", vmName, err)
		return c.Status(500).JSON(fiber.Map{"detail": err.Error()})
	}

	if success, ok := result["success"].(bool); ok && success {
		if data, ok := result["data"].(map[string]interface{}); ok {
			if info, ok := data["info"].(map[string]interface{}); ok {
				if vmInfo, ok := info[vmName]; ok {
					return c.JSON(vmInfo)
				}
			}
		}
	}

	// If the structure doesn't match, return the result as is
	return c.JSON(result)
}

// StartVM starts a stopped VM
func StartVM(c *fiber.Ctx) error {
	sessionID := c.Cookies("session_id")
	if !auth.CheckAuth(sessionID) {
		return c.Status(401).JSON(fiber.Map{"detail": "Not authenticated"})
	}

	var req models.VMActionRequest
	if err := c.BodyParser(&req); err != nil {
		return c.Status(400).JSON(fiber.Map{"error": "Invalid request"})
	}

	exec := executor.GlobalExecutorFactory.GetExecutor(req.AgentID)
	result, _ := exec.StartVM(req.Name)

	if success, ok := result["success"].(bool); ok && success {
		time.Sleep(2 * time.Second)
		message := fmt.Sprintf("VM '%s' started", req.Name)
		if msg, ok := result["message"].(string); ok && msg != "" {
			message = msg
		}
		return c.JSON(fiber.Map{
			"success": true,
			"message": message,
		})
	}

	message := "Failed to start VM"
	if msg, ok := result["message"].(string); ok {
		message = msg
	}
	return c.Status(500).JSON(fiber.Map{"detail": message})
}

// StopVM stops a running VM
func StopVM(c *fiber.Ctx) error {
	sessionID := c.Cookies("session_id")
	if !auth.CheckAuth(sessionID) {
		return c.Status(401).JSON(fiber.Map{"detail": "Not authenticated"})
	}

	var req models.VMActionRequest
	if err := c.BodyParser(&req); err != nil {
		return c.Status(400).JSON(fiber.Map{"error": "Invalid request"})
	}

	exec := executor.GlobalExecutorFactory.GetExecutor(req.AgentID)
	result, _ := exec.StopVM(req.Name)

	if success, ok := result["success"].(bool); ok && success {
		message := fmt.Sprintf("VM '%s' stopped", req.Name)
		if msg, ok := result["message"].(string); ok && msg != "" {
			message = msg
		}
		return c.JSON(fiber.Map{
			"success": true,
			"message": message,
		})
	}

	message := "Failed to stop VM"
	if msg, ok := result["message"].(string); ok {
		message = msg
	}
	return c.Status(500).JSON(fiber.Map{"detail": message})
}

// DeleteVM deletes a VM
func DeleteVM(c *fiber.Ctx) error {
	sessionID := c.Cookies("session_id")
	if !auth.CheckAuth(sessionID) {
		return c.Status(401).JSON(fiber.Map{"detail": "Not authenticated"})
	}

	var req models.VMActionRequest
	if err := c.BodyParser(&req); err != nil {
		return c.Status(400).JSON(fiber.Map{"error": "Invalid request"})
	}

	exec := executor.GlobalExecutorFactory.GetExecutor(req.AgentID)
	result, _ := exec.DeleteVM(req.Name)

	if success, ok := result["success"].(bool); ok && success {
		message := fmt.Sprintf("VM '%s' deleted", req.Name)
		if msg, ok := result["message"].(string); ok && msg != "" {
			message = msg
		}
		return c.JSON(fiber.Map{
			"success": true,
			"message": message,
		})
	}

	message := "Failed to delete VM"
	if msg, ok := result["message"].(string); ok {
		message = msg
	}
	return c.Status(500).JSON(fiber.Map{"detail": message})
}
