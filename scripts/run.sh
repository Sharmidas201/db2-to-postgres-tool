#!/bin/bash
# Azure Migration Assistant Launcher

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Check if .venv exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv --system-site-packages .venv
    .venv/bin/pip install -r requirements.txt
fi

echo "Starting Azure Migration Assistant UI..."
.venv/bin/streamlit run app.py
