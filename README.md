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
| `search_items(query, category)` | Busca itens por nome (ex.: "sword", "hair") |
| `get_item(item_id)` | Cores e variantes de um item |
| `generate_character(items, body_type, animations, filename)` | Gera o PNG |

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

A imagem sai em `output/` (ou em `LPC_OUTPUT_DIR`), com quadros de 64×64 e
cada animação empilhada verticalmente (4 linhas: cima, esquerda, baixo, direita).

## Limitações
- Itens com várias cores usam só a primeira cor.
- Animações de arma "oversize" (golpe grande de 128/192px) ainda não são incluídas.

## Licença das artes
As sprites são LPC (CC-BY-SA 3.0 / OGA-BY 3.0 / GPL 3.0). Se publicar um jogo,
dê crédito aos autores — veja `lpc/CREDITS.csv` ou o site do gerador.
