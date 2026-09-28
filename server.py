"""MCP server que gera personagens LPC (Universal LPC Spritesheet Character Generator).

Lê as definições JSON do repositório clonado em ./lpc e baixa os PNGs sob demanda
do GitHub (com cache local em ./cache).
"""
import csv
import io
import json
import os
import random
import re
import urllib.parse
import urllib.request
from pathlib import Path

from mcp.server.mcpserver import Image as MCPImage
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
    files = _sprite_files()
    if files is not None and rel not in files:
        return None  # não existe no repositório: nem tenta baixar
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


_FILES = None


def _sprite_files():
    """Lista de PNGs que existem no repositório (lida da árvore do git, sem baixar imagens).
    Fica em cache por commit; devolve None se o git não estiver disponível."""
    global _FILES
    if _FILES is None:
        try:
            import subprocess
            run = lambda *a: subprocess.run(a, cwd=REPO, check=True, capture_output=True,
                                            text=True, encoding="utf8").stdout
            head = run("git", "rev-parse", "HEAD").strip()
            cache = CACHE / f"_files_{head}.txt"
            if not cache.exists():
                CACHE.mkdir(exist_ok=True)
                cache.write_text(run("git", "ls-tree", "-r", "--name-only", "HEAD", "spritesheets"),
                                 encoding="utf8")
            n = len("spritesheets/")
            _FILES = {line[n:] for line in cache.read_text(encoding="utf8").splitlines()}
        except Exception:
            _FILES = set()
    return _FILES or None


def item_animations(item_id, body):
    """Animações normais em que o item tem arte para esse corpo (pela lista de arquivos)."""
    d, files = ITEMS[item_id], _sprite_files()
    layers = [v for k, v in d.items() if k.startswith("layer_")
              and not v.get("custom_animation") and v.get(body)]
    if not layers:
        return []
    if files is None:
        return list(d.get("animations") or ANIMATIONS)
    path = layers[0][body]
    if d.get("variants"):
        dirs = {f.rsplit("/", 1)[0] for f in files if f.startswith(path)}
        return [a for a in ANIMATIONS if f"{path}{a}" in dirs]
    return [a for a in ANIMATIONS if f"{path}{a}.png" in files]


def _item_bodies(d):
    return sorted({b for k, v in d.items() if k.startswith("layer_") for b in v if b in BODY_TYPES})


@mcp.tool()
def search_items(query: str = "", category: str = "", body_type: str = "",
                 animation: str = "", type_name: str = "", limit: int = 50) -> list[dict]:
    """Procura itens. Todos os filtros são opcionais e se combinam:
    query: palavras no nome/id (todas precisam aparecer), ex.: "leather armour".
    category: prefixo do id, ex.: 'hair', 'torso/shirts', 'weapons/sword'.
    body_type: só itens que existem para esse corpo (male, female, teen...).
    animation: só itens com arte nessa animação (idle, walk, slash...) para o body_type
               (ou para male, se body_type não for dado). Evita surpresas como a túnica sem idle.
    type_name: tipo do item (hair, clothes, legs, shoes, weapon, hat...)."""
    words = query.lower().split()
    res = []
    for i, d in ITEMS.items():
        text = f"{i} {d.get('name', '')}".lower().replace("_", " ")
        if category and not i.startswith(category):
            continue
        if not all(w in text or w in i.lower() for w in words):
            continue
        if type_name and d.get("type_name") != type_name:
            continue
        if body_type and body_type not in _item_bodies(d):
            continue
        if animation and animation not in item_animations(i, body_type or "male"):
            continue
        res.append({"id": i, "name": d.get("name"), "type": d.get("type_name")})
        if len(res) >= limit:
            break
    return res


@mcp.tool()
def get_item(item_id: str) -> dict:
    """Detalhes de um item: corpos suportados, animações com arte em cada corpo,
    cores (recolor) ou variantes, partes com cores separadas e animações especiais."""
    d = ITEMS[item_id]
    bodies = _item_bodies(d)
    info = {"id": item_id, "name": d.get("name"), "type": d.get("type_name"),
            "body_types": bodies,
            "animations": {b: item_animations(item_id, b) for b in bodies}}
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

# ---------- links do site ----------
SITE = "https://liberatedpixelcup.github.io/Universal-LPC-Spritesheet-Character-Generator/"


def _norm(v):
    return urllib.parse.unquote(v).replace(" ", "_").lower()


def _by_type():
    out = {}
    for item_id, d in ITEMS.items():
        out.setdefault(d.get("type_name"), []).append(item_id)
    return out


def _sub_parts():
    """type_name de partes extras (color_2...) -> [(item_id, índice da parte)]."""
    out = {}
    for item_id, d in ITEMS.items():
        for n, e in enumerate(_recolor_entries(d)):
            if n and e.get("type_name"):
                out.setdefault(e["type_name"], []).append((item_id, n))
    return out


def _match_param(type_name, value, by_type):
    """Mesmo algoritmo do site: tenta 'Nome' + '_variante' com cortes crescentes."""
    parts = value.split("_")
    for i in range(1, len(parts) + 1):
        name, rest = "_".join(parts[:i]), "_".join(parts[i:])
        variant, _, recolor = rest.partition("|")
        for item_id in by_type.get(type_name, []):
            d = ITEMS[item_id]
            if d.get("name", "").replace(" ", "_").lower() != name.lower():
                continue
            for v in d.get("variants") or []:
                if _norm(v) == _norm(variant):
                    return {"id": item_id, "variant": v}
            entries = _recolor_entries(d)
            if entries:
                want = _norm(recolor or variant)
                for c in _colors_for(entries[0]):
                    if _norm(c) == want:
                        return {"id": item_id, "color": c}
            if not variant:
                return {"id": item_id}
    return None


def parse_url(url: str) -> dict:
    frag = url.split("#", 1)[1] if "#" in url else url
    params = [p.split("=", 1) for p in frag.split("&") if "=" in p]
    by_type, subs = _by_type(), _sub_parts()
    body, items, unresolved, extras = "male", [], {}, []
    for key, value in params:
        if key in ("sex", "bodyType"):
            body = value
        elif key in by_type:
            it = _match_param(key, value, by_type)
            if it:
                items.append(it)
            else:
                unresolved[key] = value
        elif key in subs:
            extras.append((key, value))
        else:
            unresolved[key] = value
    # cores de partes extras (ex.: handle=Grip_oak)
    for key, value in extras:
        for it in items:
            for item_id, n in subs[key]:
                if it["id"] == item_id:
                    cols = _color_list(it)
                    cols += [None] * (n + 1 - len(cols))
                    # valor = "<Rótulo>_<cor>"; a cor pode ter "_" (dark_brown)
                    match = [c for c in _colors_for(_recolor_entries(ITEMS[item_id])[n])
                             if _norm(value).endswith("_" + _norm(c)) or _norm(value) == _norm(c)]
                    cols[n] = max(match, key=len) if match else None
                    it["color"] = cols
    result = {"body_type": body, "items": items}
    if unresolved:
        result["unresolved"] = unresolved
    return result


def build_url(items: list[dict], body_type: str = "male") -> str:
    params = [("sex", body_type)]
    for it in items:
        d = ITEMS[it["id"]]
        cols = _color_list(it)
        entries = _recolor_entries(d)
        value = d["name"].replace(" ", "_")
        if d.get("variants"):
            v = it.get("variant") or (cols[0] if cols[0] in d["variants"] else d["variants"][0])
            value += "_" + v.replace(" ", "_")
        elif entries:
            value += "_" + (cols[0] or _default_color(entries[0]))
        params.append((d["type_name"], value))
        for n, e in enumerate(entries[1:], start=1):
            if n < len(cols) and cols[n] and e.get("type_name"):
                label = (e.get("label") or e["type_name"]).replace(" ", "_")
                params.append((e["type_name"], f"{label}_{cols[n]}"))
    return SITE + "#" + "&".join(f"{k}={urllib.parse.quote(v, safe='_|-')}" for k, v in params)


@mcp.tool()
def from_site_url(url: str) -> dict:
    """Lê um link do gerador LPC (ex.: ...Character-Generator/#sex=male&body=Body_Color_light&...)
    e devolve {body_type, items} prontos para generate_character.
    Parâmetros que não foram reconhecidos aparecem em `unresolved`."""
    return parse_url(url)


@mcp.tool()
def to_site_url(items: list[dict], body_type: str = "male") -> str:
    """Monta o link do site com esses itens, para abrir e ajustar o personagem no navegador."""
    for it in items:
        if it["id"] not in ITEMS:
            raise ValueError(f"item desconhecido: {it['id']}")
    return build_url(items, body_type)


# ---------- personagens aleatórios ----------
SKIN_COLORS = ["light", "amber", "olive", "taupe", "bronze", "brown", "black"]
HAIR_COLORS = ["black", "dark_brown", "chestnut", "light_brown", "blonde", "platinum", "ginger",
               "redhead", "gray", "white", "ash", "sandy", "raven"]
CLOTH_COLORS = ["white", "black", "gray", "charcoal", "slate", "brown", "tan", "leather", "walnut",
                "navy", "blue", "bluegray", "sky", "teal", "forest", "green", "maroon", "red",
                "rose", "lavender", "purple", "orange", "yellow", "linen", "ivory", "oak"]
# (chance, prefixos de id, só para corpo)
RANDOM_SLOTS = [
    (1.0, ["hair/short", "hair/long", "hair/bob", "hair/curly", "hair/spiky", "hair/braids",
           "hair/afro", "hair/pigtails", "hair/xlong"], None),
    (0.35, ["hair/beards", "hair/mustaches"], {"male", "muscular"}),
    (1.0, ["torso/shirts"], None),
    (0.25, ["torso/vest", "torso/jacket/", "torso/aprons"], None),
    (1.0, ["legs/pants", "legs/skirts", "legs/shorts"], None),
    (1.0, ["feet/shoes", "feet/boots"], None),
    (0.2, ["headwear/hats/caps", "headwear/hats/formal", "headwear/coverings/bandana",
           "headwear/coverings/headbands"], None),
    (0.15, ["torso/cape/"], None),
]


def _supports(item_id, body, anim="walk"):
    d = ITEMS[item_id]
    layers = [v for k, v in d.items() if k.startswith("layer_") and not v.get("custom_animation")]
    anims = d.get("animations")
    return bool(layers) and all(body in l for l in layers) and (anims is None or anim in anims)


def _random_color(rng, d, it, hair=False):
    """Sorteia cor/variante preferindo tons naturais (cabelo) ou discretos (roupa)."""
    preferred = HAIR_COLORS if hair else CLOTH_COLORS
    if d.get("variants"):
        options = d["variants"]
        it["variant"] = rng.choice([v for v in options if v in preferred] or options)
        return
    entries = _recolor_entries(d)
    if not entries:
        return
    options = sorted(_colors_for(entries[0]))
    it["color"] = rng.choice([c for c in preferred if c in options] or options)


def random_items(body_type="male", rng=None, fixed=None):
    rng = rng or random.Random()
    skin = rng.choice(SKIN_COLORS)
    female = body_type in ("female", "pregnant")
    heads = [i for i in ITEMS if i.startswith("head/heads/human/") and _supports(i, body_type)
             and ("female" in i) == female and "child" not in i and "elderly" not in i]
    if body_type == "child":
        heads = [i for i in ITEMS if i.startswith("head/heads/human/") and "child" in i] or heads
    items = [{"id": "body/body", "color": skin}]
    if heads:
        items.append({"id": rng.choice(heads)})
    for chance, prefixes, bodies in RANDOM_SLOTS:
        if bodies and body_type not in bodies or rng.random() > chance:
            continue
        pool = [i for i in ITEMS if any(i.startswith(p) for p in prefixes)
                and _supports(i, body_type) and not ITEMS[i].get("match_body_color")]
        if not female:
            pool = [i for i in pool if "skirt" not in i and "blouse" not in i and "corset" not in i]
        if not pool:
            continue
        item_id = rng.choice(pool)
        it = {"id": item_id}
        _random_color(rng, ITEMS[item_id], it, hair=item_id.startswith("hair/"))
        items.append(it)
    # barba/bigode com a mesma cor do cabelo
    hair = next((it for it in items if it["id"].startswith("hair/") and "color" in it), None)
    for it in items:
        if hair and it is not hair and it["id"].startswith(("hair/beards", "hair/mustaches")):
            if hair["color"] in _colors_for(_recolor_entries(ITEMS[it["id"]])[0]):
                it["color"] = hair["color"]
    return items + list(fixed or [])


@mcp.tool()
def random_character(body_type: str = "male", seed: int | None = None,
                     fixed_items: list[dict] | None = None) -> dict:
    """Sorteia um personagem (pele, cabeça, cabelo, roupa, calçado e às vezes barba,
    chapéu, colete ou capa). Não gera a imagem: devolve {items, body_type, url} para
    revisar e passar a generate_character. `fixed_items` entram em todos (ex.: uma arma).
    Use `seed` para repetir o mesmo sorteio."""
    items = random_items(body_type, random.Random(seed), fixed_items)
    return {"body_type": body_type, "items": items, "url": build_url(items, body_type)}


@mcp.tool()
def generate_batch(count: int = 5, body_types: list[str] | None = None, seed: int | None = None,
                   prefix: str = "npc", fixed_items: list[dict] | None = None,
                   animations: list[str] | None = None, layout: str = "standard",
                   split: bool = False) -> dict:
    """Gera vários personagens aleatórios de uma vez (ex.: aldeões para um vilarejo).
    Salva <prefix>_01.png, <prefix>_02.png... e os créditos de cada um.
    body_types: corpos sorteados entre esses (padrão: male e female).
    fixed_items: itens que todos recebem (ex.: [{"id": "tools/tool_hammer"}])."""
    rng = random.Random(seed)
    bodies = body_types or ["male", "female"]
    out = []
    for n in range(1, count + 1):
        body = rng.choice(bodies)
        items = random_items(body, rng, fixed_items)
        r = generate_character(items, body, animations, f"{prefix}_{n:02d}.png", layout, split)
        out.append({"file": r.get("file"), "body_type": body, "items": items,
                    "url": build_url(items, body), **({"error": r["error"]} if "error" in r else {})})
    return {"count": len(out), "characters": out}


# ---------- prévia no chat ----------
@mcp.tool()
def preview_character(items: list[dict], body_type: str = "male", animation: str = "walk"):
    """Mostra uma prévia do personagem (4 direções, ampliada) direto no chat, sem salvar
    o arquivo final. Use para conferir o visual antes de generate_character.
    animation: walk, idle, slash... ou uma especial (tool_hammer, slash_128, walk_128...)."""
    global OUT
    special = animation in _custom_animations()
    base = _custom_base(animation) if special else animation
    if base not in ANIMATIONS:
        return f"animação desconhecida: {animation}. Use uma de {ANIMATIONS} ou uma especial."
    saved, OUT = OUT, CACHE / "_preview"
    try:
        r = generate_character(items, body_type, [base], "preview.png", "compact")
    finally:
        OUT = saved
    if "error" in r:
        return r["error"]
    info = r["animations"].get(animation)
    if not info:
        return f"a animação '{animation}' não existe para esses itens: {list(r['animations'])}"
    sheet = Image.open(r["file"])
    f, y0 = info["frame"], info["y"]
    col = 1 if animation == "walk" else (2 if special else 0)  # quadro representativo
    strip = Image.new("RGBA", (f * 4, f), (236, 236, 236, 255))
    for d in range(4):  # cima, esquerda, baixo, direita
        strip.alpha_composite(sheet.crop((col * f, y0 + d * f, (col + 1) * f, y0 + (d + 1) * f)), (d * f, 0))
    scale = 3 if f == 64 else 2
    buf = io.BytesIO()
    strip.resize((strip.width * scale, strip.height * scale), Image.NEAREST).save(buf, "PNG")
    note = {"animation": animation, "body_type": body_type}
    if r.get("missing"):
        note["missing"] = r["missing"]
    return [MCPImage(data=buf.getvalue(), format="png"), json.dumps(note, ensure_ascii=False)]

if __name__ == "__main__":
    mcp.run()
