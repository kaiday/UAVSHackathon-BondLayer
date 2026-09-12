#!/bin/bash
set -e

echo "🚀 BondLayer Chat App — Phase P0 Launch"
echo ""

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt -q

# Install Node dependencies
echo "📦 Installing Node dependencies..."
cd src/ui
npm install -q
cd ../..

echo ""
echo "✓ Dependencies installed"
echo ""
echo "🔥 Starting services..."
echo ""
echo "Merchant Service (:8000)"
echo "Agent Service (:8001)"
echo "UI Server (:5173)"
echo ""
echo "Open http://localhost:5173"
echo ""

# Start merchant service in background
python -m src.merchant.main &
MERCHANT_PID=$!

# Start agent service in background
python -m src.agent.main &
AGENT_PID=$!

# Start UI in foreground (blocks)
cd src/ui && npm run dev

# Cleanup on exit
trap "kill $MERCHANT_PID $AGENT_PID" EXIT
