#!/bin/bash
export PATH="$PATH:/usr/local/bin"
export PATH="$PATH:/opt/render/project/.venv/bin"
export PATH="$PATH:/opt/render/project/python/bin"

# Find where gunicorn is installed
which gunicorn || echo "gunicorn not found in PATH"

# Run with the path we found
$(which python) -m gunicorn app:app