.PHONY: build build-server build-agent run run-agent clean test

# Build both server and agent
build: build-server build-agent

# Build the main server
build-server:
	@echo "Building main server..."
	go build -o bin/batwa-server main.go

# Build the agent
build-agent:
	@echo "Building agent..."
	go build -o bin/batwa-agent cmd/agent/main.go

# Run the main server
run:
	@echo "Running main server..."
	go run main.go

# Run the agent (example)
run-agent:
	@echo "Running agent..."
	go run cmd/agent/main.go --agent-id=agent1 --master-url=http://localhost:8000

# Clean build artifacts
clean:
	@echo "Cleaning..."
	rm -rf bin/

# Run tests
test:
	go test ./...

# Install dependencies
deps:
	go mod tidy
	go mod download
