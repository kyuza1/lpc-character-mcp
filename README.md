# LPC Character Generator — MCP

[![tests](https://github.com/kyuza1/lpc-character-mcp/actions/workflows/tests.yml/badge.svg)](https://github.com/kyuza1/lpc-character-mcp/actions/workflows/tests.yml)

Servidor MCP que gera spritesheets de personagens no estilo LPC — as mesmas peças do
[Universal LPC Spritesheet Character Generator](https://liberatedpixelcup.github.io/Universal-LPC-Spritesheet-Character-Generator/) —
e exporta prontos para **Godot**, **Unity** e **Web** (Phaser/PixiJS).

Peça em linguagem natural ("gera um ferreiro moreno com avental e martelo") e o
assistente monta o personagem, mostra uma prévia animada no chat e salva os arquivos.

## Requisitos
- Python 3.10+
- Git (usado para baixar as definições dos itens na primeira vez)

## Instalação
```
git clone https://github.com/kyuza1/lpc-character-mcp.git C:\lpc-mcp
cd C:\lpc-mcp
pip install -r requirements.txt
python server.py --setup
```
O `--setup` baixa as definições dos itens (~1 min) e sai. Sem ele, isso acontece na
primeira vez que o assistente abrir o servidor — e alguns clientes desistem antes.

Nos exemplos abaixo troque `C:\lpc-mcp` pela pasta onde você clonou. No macOS/Linux
use algo como `/home/voce/lpc-mcp/server.py` e, se preciso, `python3`.

### Claude Code
```
claude mcp add lpc --scope user -- python "C:\lpc-mcp\server.py"
```

### Claude Desktop
Em **Configurações → Desenvolvedor → Editar configuração** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "lpc": {
      "command": "python",
      "args": ["C:\\lpc-mcp\\server.py"],
      "env": { "LPC_OUTPUT_DIR": "C:\\lpc-mcp\\output" }
    }
  }
}
```

### Codex (OpenAI)
Pelo terminal:
```
codex mcp add lpc -- python "C:\lpc-mcp\server.py"
```
Ou edite `~/.codex/config.toml` (no Windows, `%USERPROFILE%\.codex\config.toml`):
```toml
[mcp_servers.lpc]
command = "python"
args = ["C:\\lpc-mcp\\server.py"]
startup_timeout_sec = 60

[mcp_servers.lpc.env]
LPC_OUTPUT_DIR = "C:\\lpc-mcp\\output"
```
Confira com `codex mcp list`. O mesmo arquivo vale para a extensão do Codex no VS Code.

### Antigravity (Google)
No painel do agente clique em **…** → **MCP Servers** → **Manage MCP Servers** →
**View raw config** e adicione ao `mcp_config.json`
(fica em `~/.gemini/config/mcp_config.json`; no Windows,
`%USERPROFILE%\.gemini\config\mcp_config.json`):
```json
{
  "mcpServers": {
    "lpc": {
      "command": "python",
      "args": ["C:\\lpc-mcp\\server.py"],
      "env": { "LPC_OUTPUT_DIR": "C:\\lpc-mcp\\output" }
    }
  }
}
```
Salve e clique em **Refresh** na tela de MCP Servers. Na CLI do Antigravity, use `/mcp`
para ver e recarregar os servidores. Se o `python` não for encontrado, use o caminho
completo (ex.: `C:\\Users\\voce\\AppData\\Local\\Programs\\Python\\Python313\\python.exe`).

### Outros clientes MCP
Qualquer cliente que rode servidores **stdio** funciona: comando `python`, argumento
o caminho do `server.py`.

## Exemplos de pedidos
- "Gera um ferreiro moreno com avental de couro e martelo e exporta para Godot"
- "Me mostra uma prévia animada dele martelando"
- "Gera 10 aldeões aleatórios com seed 1, com os arquivos da Unity"
- "Abre este link e gera o personagem: https://liberatedpixelcup.github.io/...#sex=male&body=..."
- "Quais aventais têm animação idle no corpo masculino?"

## Ferramentas
| Ferramenta | O que faz |
|---|---|
| `generate_character(items, body_type, animations, filename, layout, split, export, prefer_complete)` | Gera o PNG, os créditos, o relatório de animações e (opcional) os arquivos das engines |
| `preview_character(items, body_type, animation, animated)` | Prévia no chat: GIF animado com as 4 direções |
| `search_items(query, category, body_type, animation, type_name, complete_only)` | Busca itens com filtros; itens completos primeiro |
| `get_item(item_id)` | Cores, variantes, partes com cor separada e animações que existem em cada corpo |
| `list_categories` | Lista as categorias de itens |
| `random_character(body_type, seed, fixed_items)` | Sorteia um personagem |
| `generate_batch(count, body_types, seed, prefix, fixed_items, ...)` | Gera vários NPCs aleatórios |
| `from_site_url(url)` / `to_site_url(items, body_type)` | Lê / monta links do site do gerador (inclusive links antigos) |
| `update_definitions(clear_image_cache)` | Atualiza itens e paletas do repositório oficial |

Exemplo de `items`:
```json
[
  {"id": "body/body", "color": "bronze"},
  {"id": "head/heads/human/heads_human_male"},
  {"id": "hair/short/hair_plain", "color": "dark_brown"},
  {"id": "torso/shirts/longsleeve/torso_clothes_longsleeve", "color": "white"},
  {"id": "torso/aprons/torso_aprons_apron", "variant": "leather"},
  {"id": "legs/pants/legs_cuffed", "color": "white"},
  {"id": "feet/boots/feet_boots_basic", "color": "brown"},
  {"id": "tools/tool_hammer", "color": ["steel", "walnut"]}
]
```

### Cores
- `"color": "blonde"` — uma cor (veja `colors` em `get_item`).
- `"color": ["steel", "walnut"]` — itens com várias partes (cabeça e cabo, armadura e
  cinto...). As partes aparecem em `color_parts` no `get_item`; `null` mantém a cor padrão.
- Cabeça, orelhas, nariz e outros itens de pele sem cor herdam a cor do corpo.
- Um item por tipo, como no site: pedir dois cabelos mantém o último (e avisa em `warnings`).

### Layout e partes
- `layout: "standard"` (padrão) — igual ao site: 832px de largura, cada animação sempre na
  mesma linha (walk em y=512, slash em y=768...). Animações especiais vêm abaixo de y=3456.
- `layout: "compact"` — só as animações pedidas, empilhadas.
- `split` — salva também em partes: `"animation"` (um PNG por animação), `"frame"` (um PNG
  por quadro, em `<nome>_frames/<animação>/<direção>_NN.png`) e/ou `"item"` (uma folha por
  item, para trocar roupas no jogo). Aceita lista: `["animation", "frame"]`.

### Animações especiais
Armas grandes e ferramentas (espadas, lanças, martelo, machado, arco...) usam quadros de
128 ou 192px. Elas entram sozinhas quando a animação base é pedida (pedir `slash` com o
martelo gera também `tool_hammer`).

## Animações completas
Nem todo item do LPC tem arte para as 15 animações (ex.: o avental não tem `idle`,
`run`, `jump`...). Nessas animações o item simplesmente some. Para evitar surpresas:

- **Todo resultado avisa.** `generate_character` sempre traz `animation_check`:
  ```json
  "animation_check": {
    "complete": false,
    "incomplete_items": {
      "torso/aprons/torso_aprons_apron": {
        "missing": ["climb", "idle", "jump", "sit", "emote", "run", ...],
        "complete_alternatives": ["torso/aprons/torso_aprons_overalls", ...]
      }
    },
    "summary": "ATENÇÃO: nem todas as animações ficaram completas. Apron não tem ..."
  }
  ```
  A prévia, o lote e a demo web também avisam.
- **`prefer_complete: true`** troca sozinho cada item incompleto pelo parecido mais
  próximo que tem todas as animações, mantendo a cor (ex.: avental → macacão). As trocas
  aparecem em `replaced`.
- **A busca prioriza completos.** `search_items` lista os completos primeiro, mostra
  `missing_animations` dos outros e aceita `complete_only: true`. `get_item` mostra o que
  falta e sugere `complete_alternatives`.
- **Aleatórios só com itens completos.** `random_character` e `generate_batch` sorteiam
  apenas itens com todas as animações.

Não contam como falta: rosto, nariz, barba, óculos e colares em `climb` (o personagem
fica de costas), expressões em `hurt`, e armas/ferramentas/escudos — que por natureza só
aparecem nas animações delas (listadas em `equipment_only_in`).

## Exportar para engines
Passe `export` no `generate_character` (pode combinar vários):

| `export` | Arquivos | Como usar |
|---|---|---|
| `"godot"` | `<nome>.tres` (SpriteFrames) | Copie `<nome>.png` e `<nome>.tres` para `res://characters/` e use o `.tres` em **Sprite Frames** de um `AnimatedSprite2D`. Animações: `walk_down`, `idle_left`, `tool_hammer_right`... Testado no Godot 4.6. |
| `"unity"` | `<nome>.png.meta` + `<nome>_unity_anims/*.anim` | Copie o PNG, o `.meta` e a pasta para `Assets/`. Os sprites já vêm fatiados (Sprite Mode Multiple, filtro Point, sem compressão) e cada `.anim` vai direto num Animator com SpriteRenderer. Testado no Unity 6. |
| `"web"` | `<nome>.json` (atlas) + `<nome>_demo.html` | Atlas no formato TexturePacker (hash) com `animations`: Phaser 3 `this.load.atlas(...)`, PixiJS `Assets.load(...)`. A demo toca o personagem com setas/WASD, Shift e Espaço — abra por um servidor local (`python -m http.server`). |
| `"site"` | `<nome>_site.json` | Cole no botão **Import from Clipboard (JSON)** do site do gerador para continuar editando lá. |

## Créditos das artes
Cada geração salva `<nome>_credits.txt` e `<nome>_credits.csv` com autores, licenças e
links **só das artes usadas**. As sprites são LPC (CC-BY-SA 3.0, OGA-BY 3.0, GPL 3.0 e
outras) — se publicar um jogo, inclua esses créditos.

## Limitações
- Alguns tipos não têm nenhuma versão completa (capas, mochilas, vestidos, saias). Com
  `prefer_complete` eles ficam como estão, e o `animation_check` avisa.

## Desenvolvimento
```
pip install pytest
python -m pytest -q
```
Os testes rodam no GitHub Actions em Linux, Windows e macOS a cada push e toda segunda
(para pegar mudanças no repositório oficial do LPC).

## Licença
Código sob [MIT](LICENSE). As artes baixadas pertencem aos artistas do LPC e seguem as
licenças deles (veja os arquivos de créditos gerados).
