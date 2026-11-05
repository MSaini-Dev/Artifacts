"""Run the FastAPI backend."""

import sys
import os
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn

from backend.server import _api_bind_host, app

def main():
    port = int(os.environ.get("PORT", 8000))
    host = _api_bind_host()
    print("=" * 60)
    print("Starting the Brain Studio backend")
    print("=" * 60)
    print(f"👉 Local URL : http://{host}:{port}")
    print(f"👉 API Docs  : http://{host}:{port}/docs")
    print(f"Static UI : {Path(__file__).resolve().parent / 'static'}")
    print("=" * 60)
    
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    main()
