#!/bin/bash
# Start the Butler API

echo "Starting SOTA Butler API..."

# Install dependencies if needed
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Installing dependencies..."
source venv/bin/activate
pip install -r requirements.txt

echo "Starting Butler API server..."
python butler_api.py
