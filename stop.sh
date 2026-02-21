#!/bin/bash
#
# SOTA - Stop All Services
#

echo "🛑 Stopping SOTA services..."

# Kill by port
lsof -ti:3000 2>/dev/null | xargs kill -9 2>/dev/null && echo "  ✅ Killed frontend (port 3000)" || echo "  ⚪ Frontend not running"
lsof -ti:3001 2>/dev/null | xargs kill -9 2>/dev/null && echo "  ✅ Killed backend (port 3001)" || echo "  ⚪ Backend not running"

# Kill by process name
pkill -f "butler_api.py" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true

echo ""
echo "✅ All SOTA services stopped"
