"""MCP server que gera personagens LPC (Universal LPC Spritesheet Character Generator).

Lê as definições JSON do repositório clonado em ./lpc e baixa os PNGs sob demanda
do GitHub (com cache local em ./cache).
"""
import csv
import io
import json
import os
import re
import urllib.request
from pathlib import Path

from mcp.server.mcpserver import MCPServer
import numpy as np
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

# Layout padrão do site (spritesheet "universal"): linha inicial de cada animação
STANDARD_ROWS = {"spellcast": 0, "thrust": 4, "walk": 8, "slash": 12, "shoot": 16, "hurt": 20,
                 "climb": 21, "idle": 22, "jump": 26, "sit": 30, "emote": 34, "run": 38,
                 "combat_idle": 42, "backslash": 46, "halfslash": 50}
SHEET_WIDTH, SHEET_HEIGHT = 832, 3456  # 13 x 54 quadros de 64px

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


def _read_palette(path):
    return json.loads(path.read_text(encoding="utf8")) if path.exists() else {}


def _colors_for(recolor):
    """Retorna {nome_da_cor: [hex...]} para uma entrada de recolor."""
    out = {}
    for spec in recolor.get("palettes", []):
        for name, cols in _read_palette(_palette_file(recolor["material"], spec)).items():
            out.setdefault(name, cols)
    return out


def _base_colors(recolor):
    """Cores de referência (as que estão desenhadas no PNG original)."""
    material = recolor["material"]
    base = recolor.get("base") or _material_base(material)
    if base and "." in base:  # 'lpcr.brown' = versão.cor
        ver, name = base.split(".", 1)
        return _read_palette(PALS / material / f"{material}_{ver}.json").get(name)
    return _colors_for(recolor).get(base)


def _default_color(recolor):
    base = recolor.get("base") or _material_base(recolor["material"])
    return base.split(".")[-1] if base else None


def _recolor_entries(d):
    r = d.get("recolors")
    if not r:
        return []
    if "material" in r:
        return [r]
    return [r[k] for k in sorted(r, key=lambda k: int(k.split("_")[1])) if k.startswith("color_")]


def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ---------- imagens ----------
_used_files = set()  # PNGs usados na geração atual (para os créditos)


def _fetch(rel):
    local = CACHE / rel
    if not local.exists():
        local.parent.mkdir(parents=True, exist_ok=True)
        try:
            local.write_bytes(urllib.request.urlopen(RAW + rel, timeout=30).read())
        except Exception:
            local.write_bytes(b"")  # marca como inexistente
    if not local.stat().st_size:
        return None
    _used_files.add(rel)
    return Image.open(local).convert("RGBA")


def _color_list(it):
    """'color' pode ser uma string ou uma lista (uma cor por parte: color_1, color_2...)."""
    c = it.get("color")
    return c if isinstance(c, list) else [c]


def _recolor(img, d, colors):
    """Troca a paleta de cada parte (color_1, color_2...) pela cor pedida, como o site faz."""
    mapping = {}
    for entry, color in zip(_recolor_entries(d), colors):
        if not color:
            continue
        src, dst = _base_colors(entry), _colors_for(entry).get(color)
        if src and dst:
            mapping.update({_hex(a): _hex(b) for a, b in zip(src, dst) if a != b})
    if not mapping:
        return img
    arr = np.array(img)
    rgb = arr[..., :3].astype(np.uint32)
    key = (rgb[..., 0] << 16) | (rgb[..., 1] << 8) | rgb[..., 2]
    for (r, g, b), new in mapping.items():
        arr[..., :3][key == ((r << 16) | (g << 8) | b)] = new
    return Image.fromarray(arr, "RGBA")


def _item_file(d, it, path, anim=None):
    """PNG de uma camada: '<path><anim>.png', '<path><anim>/<variante>.png' ou,
    em animações especiais (anim=None), '<path><variante>.png'."""
    colors = _color_list(it)
    if d.get("variants"):
        v = it.get("variant") or (colors[0] if colors[0] in d["variants"] else d["variants"][0])
        v = v.replace(" ", "_")
        return _fetch(f"{path}{anim}/{v}.png" if anim else f"{path}{v}.png")
    img = _fetch(f"{path}{anim}.png" if anim else f"{path}.png")
    return _recolor(img, d, colors) if img is not None else None


def _layer_image(d, layer, body, anim, variant, colors):
    path = layer.get(body)
    if not path or layer.get("custom_animation") or layer.get("is_mask"):
        return None
    return _item_file(d, {"variant": variant, "color": colors}, path, anim)


# ---------- animações especiais (armas grandes, ferramentas) ----------
_CUSTOM_ANIMS = None


def _custom_animations():
    """Lê sources/custom-animations.ts do repositório: {nome: {frameSize, frames, single}}."""
    global _CUSTOM_ANIMS
    if _CUSTOM_ANIMS is None:
        local = REPO / "sources" / "custom-animations.ts"
        if local.exists():
            text = local.read_text(encoding="utf8")
        else:
            url = RAW.replace("/spritesheets/", "/sources/custom-animations.ts")
            text = urllib.request.urlopen(url, timeout=30).read().decode("utf8")
        body = text[text.index("customAnimations: Record"):]
        _CUSTOM_ANIMS = {}
        for m in re.finditer(r"\n  (\w+): \{(.*?)\n  \},", body, re.S):
            block = m.group(2)
            rows = re.findall(r"\[\s*((?:\"[^\"]+\",?\s*)+)\]", block)
            _CUSTOM_ANIMS[m.group(1)] = {
                "frameSize": int(re.search(r"frameSize:\s*(\d+)", block).group(1)),
                "single": "sourceSingleAnimation: true" in block,
                "frames": [re.findall(r"\"([^\"]+)\"", r) for r in rows],
            }
    return _CUSTOM_ANIMS


def _extract_frames(dest, spec, src, src_frame):
    """Copia quadros de uma animação normal (4 linhas n/w/s/e) para o layout especial,
    centralizando quando o quadro de destino é maior (ex.: 64px dentro de 128px)."""
    size = spec["frameSize"]
    off = (size - src_frame) // 2
    for i, row in enumerate(spec["frames"]):
        for j, cell in enumerate(row):
            name, col = cell.split(",")
            r = "nwse".index(name.split("-")[1])
            frame = src.crop((src_frame * int(col), src_frame * r,
                              src_frame * (int(col) + 1), src_frame * (r + 1)))
            dest.alpha_composite(frame, (size * j + off, size * i + off))


def _render_custom(name, layers, body):
    spec = _custom_animations().get(name)
    if not spec:
        return None, set()
    base_anim = spec["frames"][0][0].split(",")[0].split("-")[0]
    size = spec["frameSize"]
    sheet = Image.new("RGBA", (size * len(spec["frames"][0]), size * len(spec["frames"])))
    drawn = set()
    for _, _, d, layer, it in layers:
        path = layer.get(body)
        if not path or layer.get("is_mask"):
            continue
        custom = layer.get("custom_animation")
        if custom == name:
            img = _item_file(d, it, path)
            if img is None:
                continue
            if spec["single"]:
                _extract_frames(sheet, spec, img, img.height // 4)
            else:
                sheet.alpha_composite(img.crop((0, 0, sheet.width, sheet.height)))
        elif not custom:
            img = _item_file(d, it, path, base_anim)
            if img is None:
                continue
            _extract_frames(sheet, spec, img, 64)
        else:
            continue
        drawn.add(it["id"])
    return sheet, drawn


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
        info["default_color"] = _default_color(entries[0])
    if len(entries) > 1:
        # passe "color": [cor_parte_1, cor_parte_2, ...]
        info["color_parts"] = [{"label": e.get("label") or e.get("type_name") or d.get("type_name"),
                                "default": _default_color(e), "colors": sorted(_colors_for(e))}
                               for e in entries]
    if d.get("match_body_color"):
        info["match_body_color"] = True
    specials = sorted({v["custom_animation"] for k, v in d.items()
                       if k.startswith("layer_") and v.get("custom_animation")})
    if specials:
        info["special_animations"] = specials
    return info


@mcp.tool()
def generate_character(items: list[dict], body_type: str = "male",
                       animations: list[str] | None = None, filename: str = "character.png",
                       layout: str = "standard", split: bool = False) -> dict:
    """Gera a spritesheet do personagem e salva em PNG.

    items: lista de {"id": "<item id>", "color": "<cor>" | ["<cor 1>", "<cor 2>"], "variant": "<variante>"}.
           Inclua um corpo (body/body) e uma cabeça (ex.: head/heads/human/heads_human_male).
           Itens de pele (cabeça, orelhas, nariz...) sem cor herdam a cor do corpo.
           Itens com várias partes (ver `color_parts` em get_item) aceitam uma lista de cores.
    body_type: male | female | muscular | pregnant | teen | child
    animations: subconjunto de walk, idle, slash, thrust, spellcast, shoot, hurt, run, jump... (padrão: todas).
           Animações especiais de armas/ferramentas (ex.: slash_128, tool_hammer) entram
           automaticamente quando a animação base delas (slash, thrust...) é pedida.
    layout: "standard" = mesmo layout do site (832px de largura, cada animação sempre na
           mesma posição; animações especiais vêm abaixo, a partir de y=3456). É o formato
           que importadores de Godot/Unity/RPG Maker esperam.
           "compact" = só as animações pedidas, empilhadas.
    split: também salva cada animação num PNG separado (pasta <nome>_anims/).
    Sempre salva <nome>_credits.txt e <nome>_credits.csv com autores e licenças das artes usadas.
    """
    anims = animations or ANIMATIONS
    if layout not in ("standard", "compact"):
        return {"error": "layout deve ser 'standard' ou 'compact'"}
    _used_files.clear()
    for it in items:
        if it["id"] not in ITEMS:
            return {"error": f"item desconhecido: {it['id']}"}

    # cor da pele: itens com match_body_color sem cor herdam a cor do corpo
    skin = next((it.get("color") for it in items
                 if ITEMS[it["id"]].get("match_body_color") and it.get("color")), None)
    items = [dict(it, color=skin) if skin and not it.get("color")
             and ITEMS[it["id"]].get("match_body_color") else it for it in items]

    layers = []  # (zPos, ordem, item, layer, pedido)
    for n, it in enumerate(items):
        d = ITEMS[it["id"]]
        for k, v in d.items():
            if k.startswith("layer_"):
                layers.append((v.get("zPos", 0), n, d, v, it))
    layers.sort(key=lambda t: (t[0], t[1]))

    rows, missing = [], {}

    def note_missing(anim, drawn, only=None):
        for it in items:
            if it["id"] not in drawn and (only is None or it["id"] in only):
                missing.setdefault(it["id"], []).append(anim)

    for anim in anims:
        sheet, drawn = None, set()
        for _, _, d, layer, it in layers:
            img = _layer_image(d, layer, body_type, anim, it.get("variant"), _color_list(it))
            if img is None:
                continue
            drawn.add(it["id"])
            if sheet is None:
                sheet = Image.new("RGBA", img.size)
            if img.size != sheet.size:
                grown = Image.new("RGBA", (max(sheet.width, img.width), max(sheet.height, img.height)))
                grown.paste(sheet, (0, 0))
                sheet = grown
            sheet.alpha_composite(img, (0, 0))
        if sheet is not None:
            rows.append((anim, sheet, 64))
            # itens que só têm animação especial nessa base não contam como faltando aqui
            special = {it["id"] for _, _, _, l, it in layers
                       if l.get("custom_animation") and l.get(body_type)
                       and _custom_base(l["custom_animation"]) == anim}
            note_missing(anim, drawn | special)

    customs = []
    for _, _, _, layer, _ in layers:
        name = layer.get("custom_animation")
        if name and layer.get(body_type) and name not in customs and _custom_base(name) in anims:
            customs.append(name)
    for name in customs:
        sheet, _ = _render_custom(name, layers, body_type)
        if sheet is not None:
            rows.append((name, sheet, _custom_animations()[name]["frameSize"]))

    if not rows:
        return {"error": "nenhuma camada encontrada para essa combinação"}

    index = {}
    if layout == "standard":
        custom_h = sum(s.height for a, s, _ in rows if a not in STANDARD_ROWS)
        w = max([SHEET_WIDTH] + [s.width for _, s, _ in rows])
        final = Image.new("RGBA", (w, SHEET_HEIGHT + custom_h))
        y = SHEET_HEIGHT
        for anim, s, frame in rows:
            if anim in STANDARD_ROWS:
                pos = STANDARD_ROWS[anim] * 64
            else:
                pos, y = y, y + s.height
            final.paste(s, (0, pos))
            index[anim] = {"y": pos, "height": s.height, "frame": frame}
    else:
        final = Image.new("RGBA", (max(s.width for _, s, _ in rows), sum(s.height for _, s, _ in rows)))
        y = 0
        for anim, s, frame in rows:
            final.paste(s, (0, y))
            index[anim] = {"y": y, "height": s.height, "frame": frame}
            y += s.height

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / filename
    final.save(path)
    result = {"file": str(path), "size": list(final.size), "frame": 64, "layout": layout,
              "animations": index}

    if split:
        folder = OUT / f"{path.stem}_anims"
        folder.mkdir(exist_ok=True)
        for anim, s, _ in rows:
            s.save(folder / f"{anim}.png")
        result["split_folder"] = str(folder)

    credits = _credits(items)
    result["credits"] = _write_credits(credits, OUT / path.stem)
    if missing:
        # item sem arte para esse corpo/animação: não aparece nessas linhas
        result["missing"] = missing
    return result


def _credits(items):
    """Entradas de crédito dos itens usados, só das pastas cujos PNGs entraram na imagem."""
    out, seen = [], set()
    for it in items:
        for c in ITEMS[it["id"]].get("credits", []):
            prefix = c.get("file", "").rstrip("/") + "/"
            used = any(f.startswith(prefix) or f.startswith(prefix[:-1] + ".") for f in _used_files)
            key = c.get("file")
            if used and key not in seen:
                seen.add(key)
                out.append(c)
    return out


def _write_credits(credits, base):
    txt, rows = [], [["file", "notes", "authors", "licenses", "urls"]]
    for c in credits:
        block = [c.get("file", "")]
        if c.get("notes"):
            block.append(f"  Notas: {c['notes']}")
        block.append(f"  Autores: {', '.join(c.get('authors', []))}")
        block.append(f"  Licenças: {', '.join(c.get('licenses', []))}")
        block += [f"  {u}" for u in c.get("urls", [])]
        txt.append("\n".join(block))
        rows.append([c.get("file", ""), c.get("notes", ""), ", ".join(c.get("authors", [])),
                     ", ".join(c.get("licenses", [])), " ".join(c.get("urls", []))])
    head = ("Artes do Universal LPC Spritesheet Character Generator.\n"
            "Ao usar estas imagens, dê crédito aos autores abaixo conforme as licenças.\n\n")
    Path(f"{base}_credits.txt").write_text(head + "\n\n".join(txt) + "\n", encoding="utf8")
    with open(f"{base}_credits.csv", "w", newline="", encoding="utf8") as f:
        csv.writer(f).writerows(rows)
    authors = sorted({a for c in credits for a in c.get("authors", [])})
    licenses = sorted({l for c in credits for l in c.get("licenses", [])})
    return {"file": f"{base}_credits.txt", "csv": f"{base}_credits.csv",
            "authors": authors, "licenses": licenses}


def _custom_base(name):
    spec = _custom_animations().get(name)
    return spec["frames"][0][0].split(",")[0].split("-")[0] if spec else None

if __name__ == "__main__":
    mcp.run()
