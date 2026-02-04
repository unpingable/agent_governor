#!/usr/bin/env bash
#
# Start the Governor WebUI stack
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Starting Governor WebUI stack...${NC}"

# Start the stack
docker-compose up -d

# Wait for Ollama to be ready
echo -e "${YELLOW}Waiting for Ollama to start...${NC}"
until curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 1
done

# Check if any models are installed
MODELS=$(curl -s http://localhost:11434/api/tags | grep -o '"name":"[^"]*"' | wc -l)

if [ "$MODELS" -eq 0 ]; then
    echo -e "${YELLOW}No models found. Pulling deepseek-coder:6.7b...${NC}"
    docker exec -it governor-ollama ollama pull deepseek-coder:6.7b
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Governor WebUI is ready!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "  Fiction:   http://localhost:8001"
echo "  Code:      http://localhost:8002"
echo "  Ollama:    http://localhost:11434"
echo ""
echo "  Stop with: docker-compose down"
echo ""

# Open browser (macOS/Linux)
if command -v open &> /dev/null; then
    open http://localhost:8001
elif command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:8001
fi
