"""Comando `lpc-character-mcp`. As opções simples não importam o servidor (que baixa as
definições ao carregar)."""
import sys

from . import __version__

HELP = """lpc-character-mcp — servidor MCP que gera personagens LPC em pixel art.

Uso:
  lpc-character-mcp            inicia o servidor MCP (stdio) — é isso que o cliente chama
  lpc-character-mcp --setup    baixa as definições dos itens e sai (rode uma vez ao instalar)
  lpc-character-mcp --where    mostra onde ficam os dados, o cache e os personagens gerados
  lpc-character-mcp --clear-cache [dias]   apaga as imagens em cache (ou só as sem uso há N dias)
  lpc-character-mcp --version

Variáveis de ambiente:
  LPC_OUTPUT_DIR   pasta dos personagens gerados (padrão: ~/lpc-characters)
  LPC_DATA_DIR     pasta das definições e do cache de imagens
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
        print(f"dados:       {DATA}")
        print(f"definições:  {DATA / 'lpc' / 'sheet_definitions'}")
        print(f"cache:       {DATA / 'cache'}")
        print(f"personagens: {OUT}")
    elif "--clear-cache" in args:
        from .server import clear_cache
        rest = args[args.index("--clear-cache") + 1:]
        days = int(rest[0]) if rest and rest[0].isdigit() else 0
        r = clear_cache(days)
        print(f"{r['files']} arquivos apagados, {r['freed_mb']} MB liberados "
              f"(cache agora: {r['cache_now_mb']} MB em {r['cache_dir']})")
    elif "--setup" in args:
        from .server import DEFS, ITEMS, OUT, _custom_animations, _sprite_files
        # as definições já foram baixadas na importação; prepara a lista de arquivos e as
        # animações especiais para o primeiro uso ser rápido
        _sprite_files()
        _custom_animations()
        print(f"lpc-character-mcp pronto: {len(ITEMS)} itens.")
        print(f"Definições em {DEFS}")
        print(f"Personagens serão salvos em {OUT}")
    else:
        from .server import mcp
        mcp.run()


if __name__ == "__main__":
    main()
