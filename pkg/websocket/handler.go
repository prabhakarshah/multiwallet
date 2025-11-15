package websocket

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os"
	"os/exec"
	"syscall"
	"unsafe"

	"github.com/creack/pty"
	"github.com/gofiber/websocket/v2"
	gorillaws "github.com/gorilla/websocket"
	"github.com/prashah/batwa/pkg/agents"
)

// ResizeMessage represents a terminal resize message
type ResizeMessage struct {
	Type string `json:"type"`
	Cols uint16 `json:"cols"`
	Rows uint16 `json:"rows"`
}

// HandleTerminalConnection handles WebSocket connection for terminal access to a VM
func HandleTerminalConnection(c *websocket.Conn) {
	vmName := c.Query("vm_name")
	agentID := c.Query("agent_id")

	log.Printf("[WebSocket] Connection request for VM: %s on agent: %s", vmName, agentID)

	if vmName == "" {
		log.Println("[WebSocket] Error: No VM name provided")
		c.WriteMessage(websocket.TextMessage, []byte("Error: VM name is required\r\n"))
		c.Close()
		return
	}

	// Route to appropriate handler based on agent_id
	if agentID != "" {
		handleRemoteTerminal(c, vmName, agentID)
	} else {
		handleLocalTerminal(c, vmName)
	}
}

// handleRemoteTerminal handles terminal connection to a remote VM via agent
func handleRemoteTerminal(c *websocket.Conn, vmName, agentID string) {
	agent := agents.GlobalRegistry.GetAgent(agentID)
	if agent == nil {
		c.WriteMessage(websocket.TextMessage, []byte(fmt.Sprintf("Error: Agent '%s' not found\r\n", agentID)))
		c.Close()
		return
	}

	if agent.Status != "online" {
		c.WriteMessage(websocket.TextMessage, []byte(fmt.Sprintf("Error: Agent '%s' is offline\r\n", agentID)))
		c.Close()
		return
	}

	// Build websocket URL for agent
	agentWSURL := agent.APIURL
	if len(agentWSURL) > 7 && agentWSURL[:7] == "http://" {
		agentWSURL = "ws://" + agentWSURL[7:]
	} else if len(agentWSURL) > 8 && agentWSURL[:8] == "https://" {
		agentWSURL = "wss://" + agentWSURL[8:]
	}
	agentWSURL = fmt.Sprintf("%s/ws?vm_name=%s", agentWSURL, vmName)

	// Add API key header if needed
	headers := make(map[string][]string)
	apiKey := agents.GlobalRegistry.GetAgentAPIKey(agentID)
	if apiKey != nil {
		headers["X-API-Key"] = []string{*apiKey}
	}

	log.Printf("[WebSocket] Connecting to remote agent websocket: %s", agentWSURL)

	// Connect to remote agent's websocket
	dialer := gorillaws.Dialer{}
	remoteWS, _, err := dialer.Dial(agentWSURL, headers)
	if err != nil {
		log.Printf("[WebSocket] Error connecting to remote agent: %v", err)
		c.WriteMessage(websocket.TextMessage, []byte(fmt.Sprintf("\r\n[Connection Error] %s\r\n", err)))
		c.Close()
		return
	}
	defer remoteWS.Close()

	// Create bidirectional proxy
	done := make(chan bool, 2)

	// Forward from client to remote agent
	go func() {
		defer func() { done <- true }()
		for {
			msgType, msg, err := c.ReadMessage()
			if err != nil {
				log.Printf("Forward to remote ended: %v", err)
				return
			}
			if err := remoteWS.WriteMessage(msgType, msg); err != nil {
				log.Printf("Error writing to remote: %v", err)
				return
			}
		}
	}()

	// Forward from remote agent to client
	go func() {
		defer func() { done <- true }()
		for {
			msgType, msg, err := remoteWS.ReadMessage()
			if err != nil {
				log.Printf("Forward from remote ended: %v", err)
				return
			}
			if err := c.WriteMessage(msgType, msg); err != nil {
				log.Printf("Error writing to client: %v", err)
				return
			}
		}
	}()

	// Wait for either direction to close
	<-done
	c.Close()
	remoteWS.Close()
}

// handleLocalTerminal handles terminal connection to a local VM
func handleLocalTerminal(c *websocket.Conn, vmName string) {
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
