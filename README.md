# LPC Character Generator — MCP

Servidor MCP que gera spritesheets de personagens no estilo LPC
(mesmas peças do site https://liberatedpixelcup.github.io/Universal-LPC-Spritesheet-Character-Generator/).

## Requisitos
- Python 3.10+
- Git (usado só na primeira execução, para baixar as definições dos itens)

## Instalação
1. Clone o repositório (ou baixe o zip e extraia):
   ```
   git clone https://github.com/kyuza1/lpc-character-mcp.git C:\lpc-mcp
   cd C:\lpc-mcp
   ```
2. Instale as dependências:
   ```
   pip install -r requirements.txt
   ```
3. Registre no Claude Code (troque o caminho pelo seu):
   ```
   claude mcp add lpc --scope user -- python "C:\lpc-mcp\server.py"
   ```
   Para o Claude Desktop, adicione em `claude_desktop_config.json`:
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
4. Abra uma sessão nova e peça, por exemplo:
   > "Gera um guerreiro loiro de armadura de placas com espada"

A primeira execução demora um pouco: ele baixa as definições e, depois, cada PNG
usado (fica em cache na pasta `cache/`).

## Ferramentas
| Ferramenta | O que faz |
|---|---|
| `list_categories` | Lista categorias de itens |
| `search_items(query, category, body_type, animation, type_name)` | Busca itens com filtros (ex.: aventais com arte de `idle` no corpo `male`) |
| `get_item(item_id)` | Cores, variantes, partes com cor separada e animações que têm arte em cada corpo |
| `generate_character(items, body_type, animations, filename, layout, split)` | Gera o PNG + créditos |
| `preview_character(items, body_type, animation)` | Mostra uma prévia (4 direções) direto no chat |
| `random_character(body_type, seed, fixed_items)` | Sorteia um personagem (não gera imagem) |
| `generate_batch(count, body_types, seed, prefix, fixed_items, ...)` | Gera vários NPCs aleatórios de uma vez |
| `from_site_url(url)` | Lê um link do site do gerador e devolve os itens |
| `to_site_url(items, body_type)` | Monta o link do site para abrir o personagem no navegador |
| `update_definitions(clear_image_cache)` | Atualiza itens e paletas do repositório oficial |

### Exemplos de pedidos
- "Gera um ferreiro moreno com avental de couro e martelo"
- "Abre este link e gera o personagem: https://liberatedpixelcup.github.io/...#sex=male&body=..."
- "Gera 10 aldeões aleatórios com seed 1"
- "Me mostra uma prévia antes de gerar"

Exemplo de `items`:
```json
[
  {"id": "body/body", "color": "light"},
  {"id": "head/heads/human/heads_human_male", "color": "light"},
  {"id": "hair/short/hair_plain", "color": "blonde"},
  {"id": "torso/armour/torso_armour_plate"},
  {"id": "legs/legs_armour"},
  {"id": "feet/feet_armour"},
  {"id": "weapons/sword/weapon_sword_arming"}
]
```

A imagem sai em `output/` (ou em `LPC_OUTPUT_DIR`). O resultado diz a posição `y`
e o tamanho do quadro (`frame`) de cada animação.

### Layout
- `layout: "standard"` (padrão) — igual ao site: 832px de largura, cada animação
  sempre na mesma linha (walk em y=512, slash em y=768...). É o formato que
  importadores de Godot/Unity/RPG Maker esperam. Animações especiais (128/192px)
  vêm abaixo, a partir de y=3456.
- `layout: "compact"` — só as animações pedidas, empilhadas.
- `split: true` — também salva cada animação num PNG separado em `<nome>_anims/`.

### Créditos
Cada geração salva `<nome>_credits.txt` e `<nome>_credits.csv` com os autores,
licenças e links **só das artes usadas**. Inclua isso no seu jogo.

### Cores
- `"color": "blonde"` — uma cor (veja `colors` em `get_item`).
- `"color": ["steel", "oak"]` — itens com várias partes (lâmina e cabo, armadura e
  cinto...). As partes aparecem em `color_parts` no `get_item`; use `null` para
  manter a cor padrão de uma parte.
- Cabeça, orelhas, nariz e outros itens de pele sem cor herdam a cor do corpo.

### Animações especiais
Armas grandes e ferramentas (espadas, lanças, martelo, machado, arco...) usam
quadros de 128 ou 192px. Elas entram sozinhas quando a animação base é pedida
(ex.: pedir `slash` com uma espada gera também `slash_128`; o martelo gera
`tool_hammer`).

## Testes
```
pip install pytest
python -m pytest -q
```

## Limitações
- Nem todo item tem arte para todas as animações/corpos (ex.: a túnica só existe
  no corpo feminino e não tem "idle"; o arco só aparece em "shoot"). Nesses casos o
  resultado traz um campo `missing` dizendo o que ficou de fora.

## Licença das artes
As sprites são LPC (CC-BY-SA 3.0 / OGA-BY 3.0 / GPL 3.0). Se publicar um jogo,
dê crédito aos autores — veja `lpc/CREDITS.csv` ou o site do gerador.
