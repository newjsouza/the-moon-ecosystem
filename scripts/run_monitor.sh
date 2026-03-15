#!/bin/bash

# Kill any existing vite processes
pkill -f "vite"

echo "🚀 Iniciando Frontend do Monitor Visual..."
echo "💡 Nota: O Backend agora é iniciado automaticamente pelo sistema principal (main.py)."

# Start Frontend
cd apps/workspace_monitor
npm run dev -- --host 0.0.0.0 &
FRONTEND_PID=$!

echo "✅ Monitor Online!"
echo "🎨 Frontend: http://localhost:3000"

# Wait for process and handle exit
trap "kill $FRONTEND_PID" EXIT
wait
