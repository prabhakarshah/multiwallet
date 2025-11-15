package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"os/exec"
	"syscall"
	"time"
	"unsafe"

	"github.com/creack/pty"
	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/cors"
	"github.com/gofiber/fiber/v2/middleware/logger"
	"github.com/gofiber/websocket/v2"
	"github.com/prashah/batwa/pkg/models"
	"github.com/prashah/batwa/pkg/multipass"
)

// Config holds the agent configuration
var Config struct {
	AgentID           string
	APIKey            string
	MasterURL         string
	HeartbeatInterval int
	Port              int
}

// AgentExecutor executes multipass commands on the agent machine
type AgentExecutor struct{}

// ListVMs lists all VMs on this agent
func (e *AgentExecutor) ListVMs() map[string]interface{} {
	result := multipass.RunMultipassCommand([]string{"list", "--format", "json"})
	if !result.Success {
		return map[string]interface{}{"error": result.Error}
	}

	var data map[string]interface{}
	if err := json.Unmarshal([]byte(result.Output), &data); err != nil {
		return map[string]interface{}{"error": fmt.Sprintf("Failed to parse JSON: %s", err)}
	}

	return data
}

// GetVMInfo gets information about a specific VM
func (e *AgentExecutor) GetVMInfo(vmName string) map[string]interface{} {
	result := multipass.RunMultipassCommand([]string{"info", vmName, "--format", "json"})
	if !result.Success {
		return map[string]interface{}{"error": result.Error}
	}

	var data map[string]interface{}
	if err := json.Unmarshal([]byte(result.Output), &data); err != nil {
		return map[string]interface{}{"error": fmt.Sprintf("Failed to parse JSON: %s", err)}
	}

	return data
}

// CreateVM creates a new VM
func (e *AgentExecutor) CreateVM(req models.VMCreateRequest) map[string]interface{} {
	args := []string{
		"launch",
		req.Image,
		"--name", req.Name,
		"--cpus", fmt.Sprintf("%d", req.CPUs),
		"--memory", req.Memory,
		"--disk", req.Disk,
	}

	result := multipass.RunMultipassCommand(args)
	message := result.Output
	if !result.Success {
		message = result.Error
	}

	return map[string]interface{}{
		"success": result.Success,
		"message": message,
	}
}

// StartVM starts a VM
func (e *AgentExecutor) StartVM(vmName string) map[string]interface{} {
	result := multipass.RunMultipassCommand([]string{"start", vmName})
	message := result.Output
	if !result.Success {
		message = result.Error
	}

	return map[string]interface{}{
		"success": result.Success,
		"message": message,
	}
}

// StopVM stops a VM
func (e *AgentExecutor) StopVM(vmName string) map[string]interface{} {
	result := multipass.RunMultipassCommand([]string{"stop", vmName})
	message := result.Output
	if !result.Success {
		message = result.Error
	}

	return map[string]interface{}{
		"success": result.Success,
		"message": message,
	}
}

// DeleteVM deletes a VM
func (e *AgentExecutor) DeleteVM(vmName string) map[string]interface{} {
	result := multipass.RunMultipassCommand([]string{"delete", vmName})
	if !result.Success {
		return map[string]interface{}{
			"success": false,
			"message": result.Error,
		}
	}

	purgeResult := multipass.RunMultipassCommand([]string{"purge"})
	message := "VM deleted and purged"
	if !purgeResult.Success {
		message = purgeResult.Error
	}

	return map[string]interface{}{
		"success": purgeResult.Success,
		"message": message,
	}
}

var executor = &AgentExecutor{}

// verifyAPIKey middleware to verify API key
func verifyAPIKey(c *fiber.Ctx) error {
	if Config.APIKey == "" {
		return c.Next()
	}

	apiKey := c.Get("X-API-Key")
	if apiKey == "" || apiKey != Config.APIKey {
		return c.Status(403).JSON(fiber.Map{"detail": "Invalid or missing API key"})
	}

	return c.Next()
}

// ResizeMessage represents a terminal resize message
type ResizeMessage struct {
	Type string `json:"type"`
	Cols uint16 `json:"cols"`
	Rows uint16 `json:"rows"`
}

func main() {
	// Parse command-line flags
	agentID := flag.String("agent-id", "", "Unique identifier for this agent (required)")
	apiKey := flag.String("api-key", "", "API key for authentication (optional)")
	masterURL := flag.String("master-url", "", "URL of the master server (e.g., http://master:8000)")
	port := flag.Int("port", 8001, "Port to listen on")
	host := flag.String("host", "0.0.0.0", "Host to bind to")
	heartbeatInterval := flag.Int("heartbeat-interval", 30, "Heartbeat interval in seconds")

	flag.Parse()

	if *agentID == "" {
		log.Fatal("--agent-id is required")
	}

	// Update config
	Config.AgentID = *agentID
	Config.APIKey = *apiKey
	Config.MasterURL = *masterURL
	Config.Port = *port
	Config.HeartbeatInterval = *heartbeatInterval

	// Create Fiber app
	app := fiber.New(fiber.Config{
		AppName: "Batwa Agent",
	})

	// Add CORS middleware
	app.Use(cors.New(cors.Config{
		AllowOrigins:     "*",
		AllowCredentials: true,
		AllowMethods:     "GET,POST,PUT,DELETE,OPTIONS",
		AllowHeaders:     "*",
	}))

	// Add logger middleware
	app.Use(logger.New())

	// Health check endpoint
	app.Get("/health", func(c *fiber.Ctx) error {
		return c.JSON(fiber.Map{
			"status":    "ok",
			"agent_id":  Config.AgentID,
			"timestamp": time.Now().Format(time.RFC3339),
		})
	})

	// Execute command endpoint
	app.Post("/api/execute", verifyAPIKey, func(c *fiber.Ctx) error {
		var req models.RemoteCommandRequest
		if err := c.BodyParser(&req); err != nil {
			return c.Status(400).JSON(fiber.Map{"error": "Invalid request"})
		}

		result := multipass.RunMultipassCommand(req.Args)
		stdout := result.Output
		stderr := result.Error
		returnCode := 0
		if !result.Success {
			returnCode = 1
		}

		return c.JSON(models.RemoteCommandResponse{
			Success:    result.Success,
			Stdout:     &stdout,
			Stderr:     &stderr,
			ReturnCode: returnCode,
		})
	})

	// VM list endpoint
	app.Get("/api/vm/list", verifyAPIKey, func(c *fiber.Ctx) error {
		result := executor.ListVMs()
		if err, ok := result["error"]; ok {
			return c.Status(500).JSON(fiber.Map{"detail": err})
		}
		return c.JSON(result)
	})

	// VM info endpoint
	app.Get("/api/vm/info/:vm_name", verifyAPIKey, func(c *fiber.Ctx) error {
		vmName := c.Params("vm_name")
		result := executor.GetVMInfo(vmName)
		if err, ok := result["error"]; ok {
			return c.Status(404).JSON(fiber.Map{"detail": err})
		}
		return c.JSON(result)
	})

	// VM create endpoint
	app.Post("/api/vm/create", verifyAPIKey, func(c *fiber.Ctx) error {
		var req models.VMCreateRequest
		if err := c.BodyParser(&req); err != nil {
			return c.Status(400).JSON(fiber.Map{"error": "Invalid request"})
		}

		result := executor.CreateVM(req)
		if success, ok := result["success"].(bool); !ok || !success {
			return c.Status(500).JSON(fiber.Map{"detail": result["message"]})
		}
		return c.JSON(result)
	})

	// VM start endpoint
	app.Post("/api/vm/start", verifyAPIKey, func(c *fiber.Ctx) error {
		var req models.VMActionRequest
		if err := c.BodyParser(&req); err != nil {
			return c.Status(400).JSON(fiber.Map{"error": "Invalid request"})
		}

		result := executor.StartVM(req.Name)
		if success, ok := result["success"].(bool); !ok || !success {
			return c.Status(500).JSON(fiber.Map{"detail": result["message"]})
		}
		return c.JSON(result)
	})

	// VM stop endpoint
	app.Post("/api/vm/stop", verifyAPIKey, func(c *fiber.Ctx) error {
		var req models.VMActionRequest
		if err := c.BodyParser(&req); err != nil {
			return c.Status(400).JSON(fiber.Map{"error": "Invalid request"})
		}

		result := executor.StopVM(req.Name)
		if success, ok := result["success"].(bool); !ok || !success {
			return c.Status(500).JSON(fiber.Map{"detail": result["message"]})
		}
		return c.JSON(result)
	})

	// VM delete endpoint
	app.Post("/api/vm/delete", verifyAPIKey, func(c *fiber.Ctx) error {
		var req models.VMActionRequest
		if err := c.BodyParser(&req); err != nil {
			return c.Status(400).JSON(fiber.Map{"error": "Invalid request"})
		}

		result := executor.DeleteVM(req.Name)
		if success, ok := result["success"].(bool); !ok || !success {
			return c.Status(500).JSON(fiber.Map{"detail": result["message"]})
		}
		return c.JSON(result)
	})

	// WebSocket endpoint for terminal connections
	app.Get("/ws", websocket.New(func(c *websocket.Conn) {
		vmName := c.Query("vm_name")
		log.Printf("[WebSocket] Connection request for VM: %s", vmName)

		if vmName == "" {
			log.Println("[WebSocket] Error: No VM name provided")
			c.WriteMessage(websocket.TextMessage, []byte("Error: VM name is required\r\n"))
			c.Close()
			return
		}

		log.Printf("[WebSocket] Creating PTY for %s", vmName)

		// Start multipass shell with PTY
		cmd := exec.Command("multipass", "shell", vmName)
		ptmx, err := pty.Start(cmd)
		if err != nil {
			log.Printf("[WebSocket] Error creating PTY: %v", err)
			c.WriteMessage(websocket.TextMessage, []byte(fmt.Sprintf("\r\n[Connection Error] %s\r\nMake sure the VM '%s' is running.\r\n", err, vmName)))
			c.Close()
			return
		}
		defer ptmx.Close()

		log.Printf("[WebSocket] Process started with PID: %d", cmd.Process.Pid)

		done := make(chan bool, 2)

		// Read from PTY and forward to websocket
		go func() {
			defer func() { done <- true }()
			buf := make([]byte, 4096)
			for {
				n, err := ptmx.Read(buf)
				if err != nil {
					if err != io.EOF {
						log.Printf("PTY read error: %v", err)
					}
					return
				}
				if n > 0 {
					if err := c.WriteMessage(websocket.BinaryMessage, buf[:n]); err != nil {
						log.Printf("WebSocket write error: %v", err)
						return
					}
				}
			}
		}()

		// Read from websocket and forward to PTY
		go func() {
			defer func() { done <- true }()
			for {
				msgType, msg, err := c.ReadMessage()
				if err != nil {
					log.Printf("WebSocket read error: %v", err)
					return
				}

				if msgType == websocket.TextMessage {
					// Check if it's a resize command
					var resizeMsg ResizeMessage
					if err := json.Unmarshal(msg, &resizeMsg); err == nil && resizeMsg.Type == "resize" {
						// Set terminal size
						setWinSize(ptmx, resizeMsg.Rows, resizeMsg.Cols)
						continue
					}

					// Send keystrokes to the shell
					if _, err := ptmx.Write(msg); err != nil {
						log.Printf("PTY write error: %v", err)
						return
					}
				}
			}
		}()

		// Wait for either direction to close
		<-done

		// Cleanup
		cmd.Process.Kill()
		cmd.Wait()
		c.Close()
	}))

	// Register with master if configured
	if Config.MasterURL != "" {
		go func() {
			time.Sleep(2 * time.Second) // Wait for server to start
			registerWithMaster()
			startHeartbeatLoop()
		}()
	}

	// Start server
	log.Printf("Starting agent server on %s:%d", *host, *port)
	log.Printf("Agent ID: %s", Config.AgentID)
	log.Printf("API key configured: %t", Config.APIKey != "")
	log.Printf("Master URL: %s", Config.MasterURL)

	if err := app.Listen(fmt.Sprintf("%s:%d", *host, *port)); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}

// setWinSize sets the terminal window size
func setWinSize(ptmx *os.File, rows, cols uint16) {
	ws := &struct {
		Row uint16
		Col uint16
		X   uint16
		Y   uint16
	}{
		Row: rows,
		Col: cols,
	}
	syscall.Syscall(syscall.SYS_IOCTL, ptmx.Fd(), syscall.TIOCSWINSZ, uintptr(unsafe.Pointer(ws)))
}

// registerWithMaster registers this agent with the master server
func registerWithMaster() {
	if Config.MasterURL == "" {
		log.Println("Master URL not configured, skipping registration")
		return
	}

	hostname, err := os.Hostname()
	if err != nil {
		log.Printf("Failed to get hostname: %v", err)
		hostname = "unknown"
	}

	// Try to determine the actual IP address
	localIP := "127.0.0.1"
	conn, err := net.Dial("udp", "8.8.8.8:80")
	if err == nil {
		defer conn.Close()
		localAddr := conn.LocalAddr().(*net.UDPAddr)
		localIP = localAddr.IP.String()
	}

	apiURL := fmt.Sprintf("http://%s:%d", localIP, Config.Port)

	registration := models.AgentRegisterRequest{
		AgentID:  Config.AgentID,
		Hostname: hostname,
		APIURL:   apiURL,
	}

	if Config.APIKey != "" {
		registration.APIKey = &Config.APIKey
	}

	body, err := json.Marshal(registration)
	if err != nil {
		log.Printf("Failed to marshal registration: %v", err)
		return
	}

	req, err := http.NewRequest("POST", Config.MasterURL+"/api/agent/register", bytes.NewBuffer(body))
	if err != nil {
		log.Printf("Failed to create request: %v", err)
		return
	}

	req.Header.Set("Content-Type", "application/json")
	if Config.APIKey != "" {
		req.Header.Set("X-API-Key", Config.APIKey)
	}

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		log.Printf("Error registering with master: %v", err)
		return
	}
	defer resp.Body.Close()
	io.Copy(io.Discard, resp.Body)

	if resp.StatusCode == 200 {
		log.Printf("Successfully registered with master at %s", Config.MasterURL)
	} else {
		log.Printf("Failed to register with master, status code: %d", resp.StatusCode)
	}
}

// sendHeartbeat sends heartbeat to master server
func sendHeartbeat() {
	if Config.MasterURL == "" {
		return
	}

	// Get VM count
	vmList := executor.ListVMs()
	vmCount := 0
	if list, ok := vmList["list"].([]interface{}); ok {
		vmCount = len(list)
	}

	heartbeat := models.AgentHeartbeat{
		AgentID:   Config.AgentID,
		Timestamp: time.Now(),
		Status:    "online",
		VMCount:   vmCount,
	}

	body, err := json.Marshal(heartbeat)
	if err != nil {
		log.Printf("Failed to marshal heartbeat: %v", err)
		return
	}

	req, err := http.NewRequest("POST", Config.MasterURL+"/api/agent/heartbeat", bytes.NewBuffer(body))
	if err != nil {
		log.Printf("Failed to create heartbeat request: %v", err)
		return
	}

	req.Header.Set("Content-Type", "application/json")
	if Config.APIKey != "" {
		req.Header.Set("X-API-Key", Config.APIKey)
	}

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		log.Printf("Error sending heartbeat: %v", err)
		return
	}
	defer resp.Body.Close()
	io.Copy(io.Discard, resp.Body)

	log.Printf("Heartbeat sent successfully")
}

// startHeartbeatLoop starts the periodic heartbeat loop
func startHeartbeatLoop() {
	ticker := time.NewTicker(time.Duration(Config.HeartbeatInterval) * time.Second)
	go func() {
		for range ticker.C {
			sendHeartbeat()
		}
	}()
}
