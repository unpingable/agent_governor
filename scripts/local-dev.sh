#!/usr/bin/env bash
#
# Local Development Setup for Agent Governor
# Sets up Ollama and recommended models for local LLM development
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
echo_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Default model to pull
DEFAULT_MODEL="deepseek-coder:6.7b"

show_help() {
    cat << EOF
Agent Governor - Local Development Setup

Usage: $0 [OPTIONS]

Options:
    -m, --model MODEL    Model to pull (default: $DEFAULT_MODEL)
    -a, --all            Pull all recommended models
    -s, --skip-pull      Skip model pulling (just check setup)
    -h, --help           Show this help

Recommended models:
    deepseek-coder:6.7b   Fast, good for most coding tasks (default)
    codellama:7b          Alternative, good Python support
    deepseek-coder:33b    Larger, better quality (needs more RAM/GPU)

Examples:
    $0                    # Install Ollama + default model
    $0 --all              # Install Ollama + all recommended models
    $0 -m codellama:7b    # Install Ollama + specific model
EOF
}

# Parse arguments
MODEL="$DEFAULT_MODEL"
PULL_ALL=false
SKIP_PULL=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -m|--model)
            MODEL="$2"
            shift 2
            ;;
        -a|--all)
            PULL_ALL=true
            shift
            ;;
        -s|--skip-pull)
            SKIP_PULL=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Check OS
check_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "linux"
    else
        echo "unknown"
    fi
}

OS=$(check_os)
echo_info "Detected OS: $OS"

# Check if Ollama is installed
check_ollama() {
    if command -v ollama &> /dev/null; then
        echo_info "Ollama is installed: $(ollama --version 2>/dev/null || echo 'version unknown')"
        return 0
    else
        return 1
    fi
}

# Install Ollama
install_ollama() {
    echo_info "Installing Ollama..."

    if [[ "$OS" == "macos" ]]; then
        if command -v brew &> /dev/null; then
            brew install ollama
        else
            echo_error "Homebrew not found. Install from: https://ollama.com/download"
            exit 1
        fi
    elif [[ "$OS" == "linux" ]]; then
        curl -fsSL https://ollama.com/install.sh | sh
    else
        echo_error "Unsupported OS. Install manually from: https://ollama.com/download"
        exit 1
    fi
}

# Check if Ollama server is running
check_ollama_server() {
    if curl -s http://localhost:11434/api/tags &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# Start Ollama server
start_ollama_server() {
    echo_info "Starting Ollama server..."

    # Check if already running
    if check_ollama_server; then
        echo_info "Ollama server already running"
        return 0
    fi

    # Start in background
    ollama serve &> /tmp/ollama.log &
    OLLAMA_PID=$!

    # Wait for server to start
    echo_info "Waiting for server to start..."
    for i in {1..30}; do
        if check_ollama_server; then
            echo_info "Ollama server started (PID: $OLLAMA_PID)"
            return 0
        fi
        sleep 1
    done

    echo_error "Failed to start Ollama server. Check /tmp/ollama.log"
    return 1
}

# Pull a model
pull_model() {
    local model="$1"
    echo_info "Pulling model: $model"
    ollama pull "$model"
}

# Main setup flow
main() {
    echo ""
    echo "================================================"
    echo "  Agent Governor - Local Development Setup"
    echo "================================================"
    echo ""

    # Step 1: Check/Install Ollama
    if ! check_ollama; then
        install_ollama
    fi

    # Step 2: Start server
    start_ollama_server

    # Step 3: Pull models
    if [[ "$SKIP_PULL" == "false" ]]; then
        if [[ "$PULL_ALL" == "true" ]]; then
            echo_info "Pulling all recommended models..."
            pull_model "deepseek-coder:6.7b"
            pull_model "codellama:7b"
            echo_warn "Skipping 33b model (large). Pull manually if needed: ollama pull deepseek-coder:33b"
        else
            pull_model "$MODEL"
        fi
    else
        echo_info "Skipping model pull"
    fi

    # Step 4: Verify setup
    echo ""
    echo_info "Verifying setup..."

    echo ""
    echo "Available models:"
    ollama list

    # Step 5: Setup Python environment
    echo ""
    echo_info "Setting up Python environment..."
    cd "$PROJECT_ROOT"

    if [[ -f "pyproject.toml" ]]; then
        if command -v pip3 &> /dev/null; then
            pip3 install -e ".[dev]" --quiet
            echo_info "Python package installed in development mode"
        fi
    fi

    # Step 6: Run tests to verify
    echo ""
    echo_info "Running quick test verification..."
    if python3 -m pytest tests/test_ops_governor.py -x -q --tb=no 2>/dev/null; then
        echo_info "Tests passing!"
    else
        echo_warn "Some tests may have failed - check manually"
    fi

    # Done
    echo ""
    echo "================================================"
    echo "  Setup Complete!"
    echo "================================================"
    echo ""
    echo "Quick commands:"
    echo "  ollama run deepseek-coder:6.7b    # Interactive chat"
    echo "  ollama list                        # List models"
    echo "  python3 -m pytest tests/ -x -q    # Run tests"
    echo ""
    echo "See QUICKSTART.md for usage tips with Claude Code"
    echo ""
}

main
