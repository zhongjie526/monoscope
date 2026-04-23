#!/bin/bash
# Monoscope — stop all services
echo "🛑 Stopping Monoscope..."
lsof -ti :8000 | xargs kill -9 2>/dev/null && echo "  Backend stopped" || echo "  Backend not running"
lsof -ti :5173 | xargs kill -9 2>/dev/null && echo "  Frontend stopped" || echo "  Frontend not running"
echo "Done."
