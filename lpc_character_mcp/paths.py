"""Pastas usadas pelo servidor (sem dependências pesadas, para a CLI responder rápido)."""
import os
import sys
from pathlib import Path

PACKAGE = Path(__file__).parent
# rodando de um clone do repositório (desenvolvimento): dados ficam na raiz do clone
DEV_CHECKOUT = (PACKAGE.parent / ".git").exists()


def _data_dir():
    """Onde ficam as definições e o cache de imagens.
    LPC_DATA_DIR > raiz do clone (desenvolvimento) > pasta de dados do usuário."""
    if os.environ.get("LPC_DATA_DIR"):
        return Path(os.environ["LPC_DATA_DIR"])
    if DEV_CHECKOUT:
        return PACKAGE.parent
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "lpc-character-mcp"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "lpc-character-mcp"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "lpc-character-mcp"


def _output_dir():
    """Onde os personagens são salvos: LPC_OUTPUT_DIR > <clone>/output > ~/lpc-characters."""
    if os.environ.get("LPC_OUTPUT_DIR"):
        return Path(os.environ["LPC_OUTPUT_DIR"])
    return PACKAGE.parent / "output" if DEV_CHECKOUT else Path.home() / "lpc-characters"


DATA = _data_dir()
OUT = _output_dir()
