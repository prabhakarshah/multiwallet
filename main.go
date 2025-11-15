package main

import (
	"log"
	"os"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/cors"
	"github.com/gofiber/fiber/v2/middleware/logger"
	"github.com/gofiber/websocket/v2"
	"github.com/prashah/batwa/pkg/agents"
	"github.com/prashah/batwa/pkg/auth"
	"github.com/prashah/batwa/pkg/routes"
	wshandler "github.com/prashah/batwa/pkg/websocket"
)

func main() {
	// Create Fiber app
	app := fiber.New(fiber.Config{
		AppName: "Multipass VM Manager",
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

	// Mount static files
	app.Static("/static", "./static")

	// Setup API routes
	routes.SetupRoutes(app)

	// Page routes
	app.Get("/", func(c *fiber.Ctx) error {
		sessionID := c.Cookies("session_id")
		if !auth.CheckAuth(sessionID) {
			return c.Redirect("/login")
		}

		return c.SendFile("./templates/index.html")
	})

	app.Get("/login", func(c *fiber.Ctx) error {
		return c.SendFile("./templates/login.html")
	})

	// WebSocket route
	app.Get("/ws", websocket.New(func(c *websocket.Conn) {
		wshandler.HandleTerminalConnection(c)
	}))

	// Start heartbeat monitor
	agents.GlobalRegistry.StartHeartbeatMonitor()

	// Cleanup on exit
	defer func() {
		log.Println("Shutting down...")
		agents.GlobalRegistry.StopHeartbeatMonitor()
	}()

	// Start server
	port := os.Getenv("PORT")
	if port == "" {
		port = "8000"
	}

	log.Printf("Starting server on port %s", port)
	if err := app.Listen(":" + port); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}
