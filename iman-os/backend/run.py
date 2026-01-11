#!/usr/bin/env python3
"""
IMAN OS Backend Runner

Loads environment variables and starts the uvicorn server.
"""

import os
import sys

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Verify required environment variables
if not os.getenv("SMARTLEAD_API_KEY"):
    print("ERROR: SMARTLEAD_API_KEY not set in .env file")
    sys.exit(1)

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    debug = os.getenv("DEBUG", "false").lower() == "true"

    print(f"Starting IMAN OS Backend on port {port}...")
    print(f"Debug mode: {debug}")
    print(f"API docs: http://localhost:{port}/docs")

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=debug,
    )
