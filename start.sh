#!/bin/bash
# Volante — start both servers
cd "$(dirname "$0")"

echo "Starting Volante..."

# Backend (port 8556)
./scripts/volante-api.sh &
BACKEND_PID=$!

# Frontend (port 5556)
./scripts/volante-web.sh &
FRONTEND_PID=$!

echo ""
echo "  Backend:  http://${VOLANTE_API_HOST:-127.0.0.1}:${VOLANTE_API_PORT:-8556}"
echo "  Frontend: http://${VOLANTE_WEB_HOST:-127.0.0.1}:${VOLANTE_WEB_PORT:-5556}"
echo ""
echo "  Press Ctrl+C to stop both servers"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
