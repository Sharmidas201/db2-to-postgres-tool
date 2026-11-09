#!/bin/bash
# Run the Azure Migration Assistant from source.
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$DIR"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

echo "Starting Azure Migration Assistant UI..."
.venv/bin/streamlit run app.py
