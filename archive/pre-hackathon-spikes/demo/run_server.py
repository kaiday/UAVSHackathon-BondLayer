"""Launcher for the AgentBridge MCP server.

Exists so claude_desktop_config.json can point at one absolute file path
regardless of the working directory Claude Desktop uses.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agentbridge.server import main  # noqa: E402

if __name__ == "__main__":
    main()
