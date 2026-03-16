#!/bin/bash
# Moon Browse Daemon Startup Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Set Bun path
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"

# Set state file location
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
export BROWSE_STATE_FILE="$PROJECT_ROOT/.gstack/browse.json"

# Start daemon
exec bun run src/server.ts "$@"
