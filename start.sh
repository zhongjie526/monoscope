#!/bin/bash
# Monoscope — start backend + frontend
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "🔬 Monoscope — Starting..."

# Kill any existing processes on our ports
lsof -ti :8000 | xargs kill -9 2>/dev/null || true
lsof -ti :5173 | xargs kill -9 2>/dev/null || true

# Start backend
echo "🔧 Starting backend (port 8000)..."
cd "$ROOT/backend"
python3 -m uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!

# Start frontend
echo "🎨 Starting frontend (port 5173)..."
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ Backend:  http://localhost:8000  (PID $BACKEND_PID)"
echo "✅ Frontend: http://localhost:5173  (PID $FRONTEND_PID)"
echo "📖 API docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both."

# Trap Ctrl+C to kill both
trap "echo '🛑 Shutting down...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM

wait
