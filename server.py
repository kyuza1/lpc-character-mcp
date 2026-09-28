"""MCP server que gera personagens LPC (Universal LPC Spritesheet Character Generator).

Lê as definições JSON do repositório clonado em ./lpc e baixa os PNGs sob demanda
do GitHub (com cache local em ./cache).
"""
import io
import json
import os
import urllib.request
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from PIL import Image

ROOT = Path(__file__).parent
REPO = ROOT / "lpc"
DEFS = REPO / "sheet_definitions"
PALS = REPO / "palette_definitions"
CACHE = ROOT / "cache"
OUT = Path(os.environ.get("LPC_OUTPUT_DIR", ROOT / "output"))
RAW = "https://raw.githubusercontent.com/LiberatedPixelCup/Universal-LPC-Spritesheet-Character-Generator/master/spritesheets/"

BODY_TYPES = ["male", "female", "muscular", "pregnant", "teen", "child"]
# Ordem padrão da spritesheet ULPC (cada linha = 64px por direção)
ANIMATIONS = ["spellcast", "thrust", "walk", "slash", "shoot", "hurt", "climb", "idle",
              "jump", "sit", "emote", "run", "combat_idle", "backslash", "halfslash"]

mcp = MCPServer("lpc-character-generator")


# ---------- catálogo ----------
def _ensure_definitions():
    """Na primeira execução, baixa só as pastas de definições JSON do repositório (sem os PNGs)."""
    if DEFS.exists():
        return
    import subprocess
    url = "https://github.com/LiberatedPixelCup/Universal-LPC-Spritesheet-Character-Generator.git"
    run = lambda *a, **kw: subprocess.run(a, check=True, capture_output=True, **kw)
    run("git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", url, str(REPO))
    run("git", "sparse-checkout", "set", "sheet_definitions", "palette_definitions", cwd=REPO)


_ensure_definitions()


def _load_items():
    items = {}
    for f in DEFS.rglob("*.json"):
        if f.name.startswith("meta_"):
            continue
        d = json.loads(f.read_text(encoding="utf8"))
        item_id = f.relative_to(DEFS).with_suffix("").as_posix()
        items[item_id] = d
    return items


ITEMS = _load_items()


def _material_base(material):
    meta = PALS / material / f"meta_{material}.json"
    return json.loads(meta.read_text(encoding="utf8")).get("base") if meta.exists() else None


def _palette_file(material, spec):
    """'ulpc' -> <material>/<material>_ulpc.json ; 'metal.ulpc' -> metal/metal_ulpc.json"""
    mat, ver = spec.split(".") if "." in spec else (material, spec)
    return PALS / mat / f"{mat}_{ver}.json"


def _colors_for(recolor):
    """Retorna {nome_da_cor: [hex...]} para uma entrada de recolor."""
    out = {}
    for spec in recolor.get("palettes", []):
        p = _palette_file(recolor["material"], spec)
        if p.exists():
            for name, cols in json.loads(p.read_text(encoding="utf8")).items():
                out.setdefault(name, cols)
    return out


def _recolor_entries(d):
    r = d.get("recolors")
    if not r:
        return []
    if "material" in r:
        return [r]
    return [r[k] for k in sorted(r) if k.startswith("color_")]


def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ---------- imagens ----------
def _fetch(rel):
    local = CACHE / rel
    if local.exists():
        return Image.open(local).convert("RGBA") if local.stat().st_size else None
    local.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = urllib.request.urlopen(RAW + rel, timeout=30).read()
    except Exception:
        local.write_bytes(b"")  # marca como inexistente
        return None
    local.write_bytes(data)
    return Image.open(io.BytesIO(data)).convert("RGBA")


def _recolor(img, recolor, color):
    colors = _colors_for(recolor)
    base = recolor.get("base") or _material_base(recolor["material"])
    if not color or color == base or base not in colors or color not in colors:
        return img
    mapping = {_hex(a): _hex(b) for a, b in zip(colors[base], colors[color])}
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px[x, y]
            if a and (r, g, b) in mapping:
                px[x, y] = (*mapping[(r, g, b)], a)
    return img


def _layer_image(d, layer, body, anim, variant, colors):
    path = layer.get(body) or layer.get("male")
    if not path or layer.get("custom_animation") or layer.get("is_mask"):
        return None
    if d.get("variants"):
        v = variant or d["variants"][0]
        return _fetch(f"{path}{anim}/{v}.png")
    img = _fetch(f"{path}{anim}.png")
    if img is None:
        return None
    entries = _recolor_entries(d)
    if entries:
        img = _recolor(img, entries[0], colors[0] if colors else None)
    return img


# ---------- ferramentas MCP ----------
@mcp.tool()
def list_categories() -> dict:
    """Lista as categorias de itens (ex.: body, hair, torso/clothes) com a quantidade de itens."""
    cats = {}
    for i in ITEMS:
        cat = i.rsplit("/", 1)[0]
        cats[cat] = cats.get(cat, 0) + 1
    return dict(sorted(cats.items()))


@mcp.tool()
def search_items(query: str = "", category: str = "", limit: int = 50) -> list[dict]:
    """Procura itens pelo nome/id. `category` filtra por prefixo (ex.: 'hair', 'torso', 'legs')."""
    q = query.lower()
    res = []
    for i, d in ITEMS.items():
        if category and not i.startswith(category):
            continue
        if q and q not in i.lower() and q not in d.get("name", "").lower():
            continue
        res.append({"id": i, "name": d.get("name"), "type": d.get("type_name")})
        if len(res) >= limit:
            break
    return res


@mcp.tool()
def get_item(item_id: str) -> dict:
    """Detalhes de um item: tipos de corpo suportados, cores (recolor) ou variantes disponíveis."""
    d = ITEMS[item_id]
    bodies = sorted({b for k, v in d.items() if k.startswith("layer_") for b in v if b in BODY_TYPES})
    info = {"id": item_id, "name": d.get("name"), "type": d.get("type_name"),
            "body_types": bodies, "animations": d.get("animations")}
    if d.get("variants"):
        info["variants"] = d["variants"]
    entries = _recolor_entries(d)
    if entries:
        info["colors"] = sorted(_colors_for(entries[0]))
        info["default_color"] = entries[0].get("base") or _material_base(entries[0]["material"])
    return info


@mcp.tool()
def generate_character(items: list[dict], body_type: str = "male",
                       animations: list[str] | None = None, filename: str = "character.png") -> dict:
    """Gera a spritesheet do personagem e salva em PNG.

    items: lista de {"id": "<item id>", "color": "<cor opcional>", "variant": "<variante opcional>"}.
           Inclua um corpo (ex.: body/body) e uma cabeça (ex.: head/heads/heads_human_male).
    body_type: male | female | muscular | pregnant | teen | child
    animations: subconjunto de walk, idle, slash, thrust, spellcast, shoot, hurt, run, jump... (padrão: todas)
    """
    anims = animations or ANIMATIONS
    layers = []  # (zPos, ordem, item, layer)
    for n, it in enumerate(items):
        d = ITEMS.get(it["id"])
        if d is None:
            return {"error": f"item desconhecido: {it['id']}"}
        for k, v in d.items():
            if k.startswith("layer_"):
                layers.append((v.get("zPos", 0), n, d, v, it))
    layers.sort(key=lambda t: (t[0], t[1]))

    rows = []
    for anim in anims:
        sheet = None
        for _, _, d, layer, it in layers:
            img = _layer_image(d, layer, body_type, anim, it.get("variant"), [it.get("color")])
            if img is None:
                continue
            if sheet is None:
                sheet = Image.new("RGBA", img.size)
            if img.size != sheet.size:
                grown = Image.new("RGBA", (max(sheet.width, img.width), max(sheet.height, img.height)))
                grown.paste(sheet, (0, 0))
                sheet = grown
            sheet.alpha_composite(img, (0, 0))
        if sheet is not None:
            rows.append((anim, sheet))

    if not rows:
        return {"error": "nenhuma camada encontrada para essa combinação"}
    w = max(s.width for _, s in rows)
    h = sum(s.height for _, s in rows)
    final = Image.new("RGBA", (w, h))
    y, index = 0, {}
    for anim, s in rows:
        final.paste(s, (0, y))
        index[anim] = {"y": y, "height": s.height}
        y += s.height
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / filename
    final.save(path)
    return {"file": str(path), "size": [w, h], "frame": 64, "animations": index}


if __name__ == "__main__":
    mcp.run()
