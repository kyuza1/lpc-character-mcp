"""Comando `lpc-character-mcp`. As opções simples não importam o servidor (que baixa as
definições ao carregar)."""
import sys

from . import __version__
from .i18n import t

HELP = """lpc-character-mcp - MCP server that generates LPC pixel-art characters.

Usage:
  lpc-character-mcp            starts the MCP server (stdio) - this is what the client runs
  lpc-character-mcp --setup    downloads the item definitions and exits (run once after install)
  lpc-character-mcp --where    shows where data, cache and generated characters live
  lpc-character-mcp --clear-cache [days]   deletes cached images (or only those unused for N days)
  lpc-character-mcp --version

Environment variables:
  LPC_OUTPUT_DIR   folder for generated characters (default: ~/lpc-characters)
  LPC_DATA_DIR     folder for item definitions and the image cache
  LPC_LANG         message language: en (default) or pt
"""


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # acentos no terminal do Windows
    if "--help" in args or "-h" in args:
        print(HELP)
    elif "--version" in args:
        print(f"lpc-character-mcp {__version__}")
    elif "--where" in args:
        from .paths import DATA, OUT
        print(t("cli_where", data=DATA, defs=DATA / "lpc" / "sheet_definitions", cache=DATA / "cache", out=OUT))
    elif "--clear-cache" in args:
        from .server import clear_cache
        rest = args[args.index("--clear-cache") + 1:]
        days = int(rest[0]) if rest and rest[0].isdigit() else 0
        r = clear_cache(days)
        print(t("cli_cleared", files=r["files"], mb=r["freed_mb"], now=r["cache_now_mb"], dir=r["cache_dir"]))
    elif "--setup" in args:
        from .catalog import DEFS, ITEMS, _sprite_files
        from .paths import OUT
        from .render import _custom_animations
        # as definições já foram baixadas na importação; prepara a lista de arquivos e as
        # animações especiais para o primeiro uso ser rápido
        _sprite_files()
        _custom_animations()
        print(t("cli_ready", n=len(ITEMS)))
        print(t("cli_defs", path=DEFS))
        print(t("cli_out", path=OUT))
    else:
        from .server import mcp
        mcp.run()


if __name__ == "__main__":
    main()
