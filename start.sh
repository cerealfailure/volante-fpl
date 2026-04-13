#!/bin/bash
# Volante — start both servers
cd "$(dirname "$0")"

echo "Starting Volante..."

# Backend (port 8555)
cd server
source ../.venv/bin/activate
python3 -m uvicorn main:app --host 0.0.0.0 --port 8555 --reload &
BACKEND_PID=$!
cd ..

# Frontend (port 5555)
cd app
npm run dev -- --port 5555 &
FRONTEND_PID=$!
cd ..

echo ""
echo "  Backend:  http://localhost:8555"
echo "  Frontend: http://localhost:5555"
echo ""
echo "  Press Ctrl+C to stop both servers"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
