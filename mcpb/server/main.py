"""Entry point for MCP Bundle hosts that run the bundled Python directly.
The manifest's mcp_config runs `uvx lpc-character-mcp` instead, so this is only a fallback."""
from lpc_character_mcp.cli import main

main()
