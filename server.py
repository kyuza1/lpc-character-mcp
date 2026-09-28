"""Atalho para quem registrou o MCP como `python <pasta>/server.py` (versões antigas).
O código agora fica no pacote lpc_character_mcp; prefira o comando `lpc-character-mcp`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lpc_character_mcp.cli import main  # noqa: E402

main()
