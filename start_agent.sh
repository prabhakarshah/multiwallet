#!/bin/bash

# Batwa Agent Startup Script
# This script starts a Batwa agent with configurable parameters

# Configuration
AGENT_ID="${AGENT_ID:-agent-$(hostname)}"
API_KEY="${API_KEY:-}"
MASTER_URL="${MASTER_URL:-http://localhost:8000}"
AGENT_PORT="${AGENT_PORT:-8001}"
AGENT_HOST="${AGENT_HOST:-0.0.0.0}"
HEARTBEAT_INTERVAL="${HEARTBEAT_INTERVAL:-30}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}  Batwa Agent Startup${NC}"
echo -e "${GREEN}=====================================${NC}"
echo ""
echo -e "${YELLOW}Configuration:${NC}"
echo "  Agent ID: ${AGENT_ID}"
echo "  Master URL: ${MASTER_URL}"
echo "  Agent Port: ${AGENT_PORT}"
echo "  Agent Host: ${AGENT_HOST}"
echo "  Heartbeat Interval: ${HEARTBEAT_INTERVAL}s"
echo "  API Key: ${API_KEY:+configured}"
echo ""

# Check if multipass is installed
if ! command -v multipass &> /dev/null; then
    echo -e "${RED}Error: multipass is not installed${NC}"
    echo "Please install multipass: https://multipass.run/"
    exit 1
fi

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is not installed${NC}"
    exit 1
fi

# Build command
CMD="python3 -m agent.agent_main"
CMD="$CMD --agent-id \"$AGENT_ID\""
CMD="$CMD --master-url \"$MASTER_URL\""
CMD="$CMD --port $AGENT_PORT"
CMD="$CMD --host $AGENT_HOST"
CMD="$CMD --heartbeat-interval $HEARTBEAT_INTERVAL"

if [ -n "$API_KEY" ]; then
    CMD="$CMD --api-key \"$API_KEY\""
fi

echo -e "${GREEN}Starting agent...${NC}"
echo ""

# Start the agent
eval $CMD
