# LPC Character Generator — MCP

*[English](README.md) · Português*

[![tests](https://github.com/kyuza1/lpc-character-mcp/actions/workflows/tests.yml/badge.svg)](https://github.com/kyuza1/lpc-character-mcp/actions/workflows/tests.yml)

Servidor MCP que gera spritesheets de personagens no estilo LPC — as mesmas peças do
[Universal LPC Spritesheet Character Generator](https://liberatedpixelcup.github.io/Universal-LPC-Spritesheet-Character-Generator/) —
e exporta prontos para **Godot**, **Unity** e **Web** (Phaser/PixiJS).

Peça em linguagem natural ("gera um ferreiro moreno com avental e martelo") e o
assistente monta o personagem, mostra uma prévia animada no chat e salva os arquivos.

## Instalação

Precisa de **[uv](https://docs.astral.sh/uv/getting-started/installation/)** e **Git**.
O uv baixa o Python certo e o pacote sozinho — não precisa clonar nada nem instalar
dependências.

1. Instale o uv (uma vez):
   - Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
   - macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. Prepare o servidor (baixa as definições dos itens, ~10 s, uma vez só):
   ```
   uvx lpc-character-mcp --setup
   ```
3. Registre no seu assistente (abaixo). Em todos, o comando é o mesmo:
   `uvx lpc-character-mcp`

Para usar a versão mais recente direto do GitHub (antes de sair no PyPI), troque
`uvx lpc-character-mcp` por `uvx --from git+https://github.com/kyuza1/lpc-character-mcp lpc-character-mcp` em qualquer exemplo.

Os personagens são salvos em `~/lpc-characters` (no Windows,
`C:\Users\<você>\lpc-characters`). Para mudar, defina `LPC_OUTPUT_DIR` — por exemplo,
apontando para a pasta de sprites do seu projeto Godot/Unity. `lpc-character-mcp --where`
mostra todas as pastas usadas. As mensagens saem em inglês por padrão; para português,
defina `LPC_LANG=pt` (no Claude Code: `claude mcp add lpc --scope user -e LPC_LANG=pt -- uvx lpc-character-mcp`).

### Claude Code
```
claude mcp add lpc --scope user -- uvx lpc-character-mcp
```

### Claude Desktop
**Com um clique:** baixe o `lpc-character-mcp.mcpb` da
[release mais recente](https://github.com/kyuza1/lpc-character-mcp/releases/latest) e abra
o arquivo (ou arraste para **Configurações → Extensões**). Na instalação dá para escolher a
pasta de saída e o idioma.

Ou adicione à mão em **Configurações → Desenvolvedor → Editar configuração** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "lpc": {
      "command": "uvx",
      "args": ["lpc-character-mcp"]
    }
  }
}
```

### Codex (OpenAI)
Pelo terminal:
```
codex mcp add lpc -- uvx lpc-character-mcp
```
Ou edite `~/.codex/config.toml` (no Windows, `%USERPROFILE%\.codex\config.toml`):
```toml
[mcp_servers.lpc]
command = "uvx"
args = ["lpc-character-mcp"]
startup_timeout_sec = 60
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
      "command": "uvx",
      "args": ["lpc-character-mcp"]
    }
  }
}
```
Salve e clique em **Refresh** na tela de MCP Servers. Na CLI do Antigravity, use `/mcp`
para ver e recarregar os servidores.

### Catálogos
Está no [Smithery](https://smithery.ai/servers/digitalinovadora/lpc-character-mcp),
no [Glama](https://glama.ai/mcp/servers/kyuza1/lpc-character-mcp) e no [registro oficial de MCP](https://registry.modelcontextprotocol.io/v0/servers?search=io.github.kyuza1/lpc-character-mcp)
como `io.github.kyuza1/lpc-character-mcp`, de onde clientes e catálogos que leem o registro
puxam automaticamente.

### Outros clientes MCP
Qualquer cliente que rode servidores **stdio** funciona com o mesmo comando `uvx` acima.

### Sem uv (pip)
```
pip install lpc-character-mcp
lpc-character-mcp --setup
```
E registre o comando `lpc-character-mcp` (sem argumentos) no seu assistente.

### Dicas
- **Liberar espaço:** `lpc-character-mcp --clear-cache` apaga as imagens em cache
  (`--clear-cache 30` só as sem uso há 30 dias).
- **Atualizar para a versão mais nova:** `uvx lpc-character-mcp@latest --version`
- **`uvx` não encontrado pelo app:** use o caminho completo (`where uvx` no Windows,
  `which uvx` no macOS/Linux).
- **Instalação antiga** (`python C:\lpc-mcp\server.py`): continua funcionando.

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
| `clear_cache(older_than_days, dry_run)` | Apaga as imagens baixadas em cache (ou só as sem uso há N dias) |

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

### Onde salvar
`output_dir` salva direto numa pasta — por exemplo a de sprites do seu jogo:
"gera o ferreiro em C:/meu-jogo/art/npcs com export godot". Sem ele, vai para
`LPC_OUTPUT_DIR` ou `~/lpc-characters`.

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
| `"godot"` | `<nome>.tres` (SpriteFrames) | Gere com `output_dir` dentro do projeto (o caminho `res://` sai certo sozinho) ou copie `<nome>.png` e `<nome>.tres` para `res://characters/`. Use o `.tres` em **Sprite Frames** de um `AnimatedSprite2D`. Animações: `walk_down`, `idle_left`, `tool_hammer_right`... Testado no Godot 4.6. |
| `"unity"` | `<nome>.png.meta`, `<nome>.controller` + `<nome>_unity_anims/*.anim` | Gere com `output_dir` dentro de `Assets/` (ou copie tudo para lá). Os sprites já vêm fatiados (Sprite Mode Multiple, filtro Point, sem compressão) e o `.controller` tem um estado por animação (começa em `idle_down`): ponha no Animator de um objeto com SpriteRenderer e use `animator.Play("walk_left")`. Testado no Unity 6. |
| `"web"` | `<nome>.json` (atlas) + `<nome>_demo.html` | Atlas no formato TexturePacker (hash) com `animations`: Phaser 3 `this.load.atlas(...)`, PixiJS `Assets.load(...)`. Testado no Phaser 3.80 e PixiJS 8.5. A demo toca o personagem com setas/WASD, Shift e Espaço — abra por um servidor local (`python -m http.server`). |
| `"site"` | `<nome>_site.json` | Cole no botão **Import from Clipboard (JSON)** do site do gerador para continuar editando lá. |

## Créditos das artes
Cada geração salva `<nome>_credits.txt` e `<nome>_credits.csv` com autores, licenças e
links **só das artes usadas**. As sprites são LPC (CC-BY-SA 3.0, OGA-BY 3.0, GPL 3.0 e
outras) — se publicar um jogo, inclua esses créditos.

## Limitações
- Alguns tipos não têm nenhuma versão completa (capas, mochilas, vestidos, saias). Com
  `prefer_complete` eles ficam como estão, e o `animation_check` avisa.
- Os corpos musculoso, criança e grávida do LPC não têm algumas animações (ex.: o
  musculoso não tem `shoot` nem `climb`). O `animation_check` mostra isso em `body_missing`.
- Godot 3 não é suportado (só Godot 4). O Unity foi testado no Unity 6.
- Roda localmente (stdio); não funciona em clientes que só aceitam servidor remoto.

## Desenvolvimento
```
git clone https://github.com/kyuza1/lpc-character-mcp.git
cd lpc-character-mcp
pip install -e ".[dev]"
python -m pytest -q
```
Rodando de um clone, as definições, o cache e os personagens ficam dentro da pasta do
clone (`lpc/`, `cache/`, `output/`).
Os testes rodam no GitHub Actions em Linux, Windows e macOS a cada push e toda segunda
(para pegar mudanças no repositório oficial do LPC).

## Licença
Código sob [MIT](LICENSE). As artes baixadas pertencem aos artistas do LPC e seguem as
licenças deles (veja os arquivos de créditos gerados).
