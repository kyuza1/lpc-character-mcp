"""MCP server que gera personagens LPC (Universal LPC Spritesheet Character Generator).

Lê as definições JSON do repositório clonado em ./lpc e baixa os PNGs sob demanda
do GitHub (com cache local em ./cache).
"""
import csv
import functools
import io
import json
import os
import random
import re
import threading
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from mcp.server.mcpserver import Image as MCPImage
from mcp.server.mcpserver import MCPServer
import numpy as np
from PIL import Image

import exporters

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

mcp = MCPServer(
    "lpc-character-generator",
    instructions=(
        "Gera personagens LPC em pixel art. Ao escolher itens, prefira os que têm todas as "
        "animações (search_items mostra 'complete' e lista os completos primeiro). Depois de "
        "generate_character, SEMPRE leia 'animation_check': se complete=false, avise o usuário "
        "quais itens não têm quais animações e ofereça as alternativas completas ou gerar de "
        "novo com prefer_complete=True. Armas e ferramentas só aparecem nas animações delas "
        "(equipment_only_in) — isso é normal. Use preview_character para mostrar o resultado."
    ),
)


# ---------- catálogo ----------
def _ensure_definitions():
    """Na primeira execução, baixa só as pastas de definições JSON do repositório (sem os PNGs)."""
    if DEFS.exists():
        return
    import shutil
    import subprocess
    import sys
    if not shutil.which("git"):
        sys.exit("lpc-mcp: o Git não foi encontrado. Instale em https://git-scm.com/downloads "
                 "e rode de novo (ele só é usado para baixar as definições dos itens).")
    url = "https://github.com/LiberatedPixelCup/Universal-LPC-Spritesheet-Character-Generator.git"
    run = lambda *a, **kw: subprocess.run(a, check=True, capture_output=True, text=True, **kw)
    try:
        run("git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", url, str(REPO))
        run("git", "sparse-checkout", "set", "sheet_definitions", "palette_definitions", cwd=REPO)
    except subprocess.CalledProcessError as e:
        shutil.rmtree(REPO, ignore_errors=True)  # não deixa um clone pela metade
        sys.exit(f"lpc-mcp: falha ao baixar as definições do GitHub (verifique a internet).\n{e.stderr}")


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


MASK_COLOR = (255, 44, 230)  # camadas de máscara são pintadas nesse rosa e depois apagadas


def _download(rel):
    """Garante o PNG no cache; devolve o caminho local ou None se não existir."""
    files = _sprite_files()
    if files is not None and rel not in files:
        return None  # não existe no repositório: nem tenta baixar
    local = CACHE / rel
    if not local.exists():
        local.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = urllib.request.urlopen(RAW + rel, timeout=30).read()
        except Exception:
            data = b""  # marca como inexistente
        tmp = local.with_suffix(f".{threading.get_ident()}.tmp")
        tmp.write_bytes(data)
        tmp.replace(local)
    return local if local.stat().st_size else None


def _prefetch(rels):
    """Baixa vários PNGs ao mesmo tempo (a primeira geração fica bem mais rápida)."""
    todo = [r for r in set(rels) if not (CACHE / r).exists()]
    if todo:
        with ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(_download, todo))


def _fetch(rel):
    local = _download(rel)
    if local is None:
        return None
    _used_files.add(rel)
    return Image.open(local).convert("RGBA")


def _apply_mask(img):
    """Apaga os pixels rosa das camadas de máscara (ex.: perna de pau esconde a perna)."""
    arr = np.array(img)
    pink = (arr[..., 0] == MASK_COLOR[0]) & (arr[..., 1] == MASK_COLOR[1]) & (arr[..., 2] == MASK_COLOR[2])
    if pink.any():
        arr[pink] = 0
        return Image.fromarray(arr, "RGBA")
    return img


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


def _item_rel(d, it, path, anim=None):
    """Caminho do PNG de uma camada: '<path><anim>.png', '<path><anim>/<variante>.png' ou,
    em animações especiais (anim=None), '<path><variante>.png'."""
    colors = _color_list(it)
    if d.get("variants"):
        v = it.get("variant") or (colors[0] if colors[0] in d["variants"] else d["variants"][0])
        v = v.replace(" ", "_")
        return f"{path}{anim}/{v}.png" if anim else f"{path}{v}.png"
    return f"{path}{anim}.png" if anim else f"{path}.png"


def _item_file(d, it, path, anim=None):
    img = _fetch(_item_rel(d, it, path, anim))
    if img is None or d.get("variants"):
        return img
    return _recolor(img, d, _color_list(it))


def _layer_image(d, layer, body, anim, variant, colors):
    path = layer.get(body)
    if not path or layer.get("custom_animation"):
        return None
    return _item_file(d, {"variant": variant, "color": colors}, path, anim)


# ---------- animações especiais (armas grandes, ferramentas) ----------
_CUSTOM_ANIMS = None


def _custom_animations():
    """Lê sources/custom-animations.ts do repositório: {nome: {frameSize, frames, single}}."""
    global _CUSTOM_ANIMS
    if _CUSTOM_ANIMS is None:
        local = REPO / "sources" / "custom-animations.ts"
        cached = CACHE / "_custom-animations.ts"
        if local.exists():
            text = local.read_text(encoding="utf8")
        elif cached.exists():
            text = cached.read_text(encoding="utf8")
        else:
            url = RAW.replace("/spritesheets/", "/sources/custom-animations.ts")
            text = urllib.request.urlopen(url, timeout=30).read().decode("utf8")
            CACHE.mkdir(exist_ok=True)
            cached.write_text(text, encoding="utf8")
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
        if not path:
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
    return _apply_mask(sheet), drawn


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


def _fill_path(d, path, names):
    """Resolve "${tipo}" no caminho (ex.: expressões usam head/faces/${head}/...) com a tabela
    replace_in_path do item e o nome do item escolhido daquele tipo. None se não combinar."""
    for var in re.findall(r"\$\{(\w+)\}", path or ""):
        value = d.get("replace_in_path", {}).get(var, {}).get(names.get(var, ""))
        if not value:
            return None
        path = path.replace("${" + var + "}", value)
    return path


def _template_options(d, path):
    """Todos os caminhos possíveis de um caminho com "${tipo}" (para checar animações sem saber a cabeça)."""
    if "${" not in (path or ""):
        return [path]
    out = []
    for var, table in d.get("replace_in_path", {}).items():
        for value in dict.fromkeys(table.values()):
            out.append(path.replace("${" + var + "}", value))
    return out


_SPRITE_DIRS = None


def _sprite_dirs():
    global _SPRITE_DIRS
    if _SPRITE_DIRS is None:
        _SPRITE_DIRS = {f.rsplit("/", 1)[0] for f in (_sprite_files() or ())}
    return _SPRITE_DIRS


@functools.lru_cache(maxsize=None)
def item_animations(item_id, body):
    """Animações normais em que o item tem arte para esse corpo (pela lista de arquivos)."""
    d, files = ITEMS[item_id], _sprite_files()
    layers = [v for k, v in d.items() if k.startswith("layer_")
              and not v.get("custom_animation") and v.get(body)]
    if not layers:
        return []
    if files is None:
        return list(d.get("animations") or ANIMATIONS)
    found = set()
    for path in _template_options(d, layers[0][body]):
        if d.get("variants"):
            found |= {a for a in ANIMATIONS if f"{path}{a}" in _sprite_dirs()}
        else:
            found |= {a for a in ANIMATIONS if f"{path}{a}.png" in files}
    return [a for a in ANIMATIONS if a in found]


def _item_bodies(d):
    return sorted({b for k, v in d.items() if k.startswith("layer_") for b in v if b in BODY_TYPES})


# ---------- animações completas ----------
# Itens que por natureza só aparecem em algumas animações (armas, ferramentas, escudos):
# não contam como "incompletos", só informam onde aparecem.
EQUIPMENT_PREFIXES = ("weapons/", "tools/")
# Faltas intencionais: ao escalar (climb) o personagem fica de costas, então rosto, nariz,
# barba, óculos, colares etc. não aparecem; expressões também não têm "hurt" (deitado).
INTENTIONAL_GAPS = [
    (("head/", "hair/beards", "hair/mustaches", "hair/extensions", "headwear/accessories",
      "headwear/neck"), {"climb"}),
    (("head/faces",), {"hurt"}),
]


def is_equipment(item_id):
    return item_id.startswith(EQUIPMENT_PREFIXES)


def animation_gaps(item_id, body):
    """Animações padrão que faltam no item para esse corpo, sem contar faltas intencionais.
    Equipamentos devolvem [] (use item_animations para ver onde aparecem)."""
    if is_equipment(item_id) or body not in _item_bodies(ITEMS[item_id]):
        return []
    ok = set(item_animations(item_id, body))
    for prefixes, gaps in INTENTIONAL_GAPS:
        if item_id.startswith(prefixes):
            ok |= gaps
    return [a for a in ANIMATIONS if a not in ok]


def _special_animations(item_id, body):
    """Animações especiais (tool_hammer, slash_128...) que o item tem para esse corpo."""
    d = ITEMS[item_id]
    return sorted({v["custom_animation"] for k, v in d.items()
                   if k.startswith("layer_") and v.get("custom_animation") and v.get(body)})


def is_complete(item_id, body):
    return body in _item_bodies(ITEMS[item_id]) and not animation_gaps(item_id, body)


def complete_alternatives(item_id, body, limit=5):
    """Itens completos do mesmo tipo, os mais parecidos primeiro (mesma pasta, palavras do nome)."""
    d = ITEMS[item_id]
    folder = item_id.rsplit("/", 1)[0]
    words = set(re.findall(r"[a-z]+", d.get("name", "").lower() + " " + item_id.lower()))
    # mesmo tipo ou mesma pasta (ex.: avental -> macacão, ambos em torso/aprons)
    cands = [i for i, o in ITEMS.items() if i != item_id and is_complete(i, body)
             and (o.get("type_name") == d.get("type_name") or i.rsplit("/", 1)[0] == folder)]

    def score(i):
        o = ITEMS[i]
        w = set(re.findall(r"[a-z]+", o.get("name", "").lower() + " " + i.lower()))
        return (i.startswith(folder), len(words & w), -len(i))
    return sorted(cands, key=score, reverse=True)[:limit]


def _swap_for_complete(it, body):
    """Troca um item incompleto pelo parecido mais próximo que tem todas as animações,
    mantendo a cor/variante quando ela existe no novo item."""
    alts = complete_alternatives(it["id"], body, 1)
    if not alts:
        return None
    new_id = alts[0]
    new = {"id": new_id}
    d = ITEMS[new_id]
    wanted = it.get("variant") or (_color_list(it)[0] if it.get("color") else None)
    if d.get("variants") and wanted in d["variants"]:
        new["variant"] = wanted
    elif _recolor_entries(d) and wanted in _colors_for(_recolor_entries(d)[0]):
        new["color"] = it.get("color")
    return new


def animation_report(items, body):
    """Relatório para o usuário: itens incompletos (com alternativas) e equipamentos."""
    incomplete, equipment = {}, {}
    for it in items:
        i = it["id"]
        if i not in ITEMS or body not in _item_bodies(ITEMS[i]):
            continue
        if is_equipment(i):
            equipment[i] = item_animations(i, body) + _special_animations(i, body)
            continue
        gaps = animation_gaps(i, body)
        if gaps:
            incomplete[i] = {"missing": gaps, "complete_alternatives": complete_alternatives(i, body, 3)}
    report = {"complete": not incomplete, "incomplete_items": incomplete}
    if equipment:
        report["equipment_only_in"] = equipment
    if incomplete:
        partes = []
        for i, info in incomplete.items():
            alt = f" (completos parecidos: {', '.join(info['complete_alternatives'])})" \
                if info["complete_alternatives"] else " (não há alternativa completa do mesmo tipo)"
            partes.append(f"{ITEMS[i]['name']} não tem {', '.join(info['missing'])}{alt}")
        report["summary"] = ("ATENÇÃO: nem todas as animações ficaram completas. " + "; ".join(partes)
                             + ". Use prefer_complete=True para trocar por itens completos.")
    else:
        report["summary"] = "Todas as animações estão completas para todos os itens."
    return report



@mcp.tool()
def search_items(query: str = "", category: str = "", body_type: str = "",
                 animation: str = "", type_name: str = "", complete_only: bool = False,
                 limit: int = 50) -> list[dict]:
    """Procura itens. Todos os filtros são opcionais e se combinam:
    query: palavras no nome/id (todas precisam aparecer), ex.: "leather armour".
    category: prefixo do id, ex.: 'hair', 'torso/shirts', 'weapons/sword'.
    body_type: só itens que existem para esse corpo (male, female, teen...).
    animation: só itens com arte nessa animação (idle, walk, slash...) para o body_type
               (ou para male, se body_type não for dado). Evita surpresas como a túnica sem idle.
    type_name: tipo do item (hair, clothes, legs, shoes, weapon, hat...).
    complete_only: só itens com todas as animações. Sem isso, os completos vêm primeiro.
    Cada resultado diz se é completo e quais animações faltam (para o body_type ou male)."""
    words = query.lower().split()
    body = body_type or "male"
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
        entry = {"id": i, "name": d.get("name"), "type": d.get("type_name")}
        if is_equipment(i):
            entry["equipment_only_in"] = item_animations(i, body) + _special_animations(i, body)
        else:
            gaps = animation_gaps(i, body)
            entry["complete"] = not gaps
            if gaps:
                entry["missing_animations"] = gaps
        if complete_only and not entry.get("complete", False):
            continue
        res.append(entry)
    # completos primeiro, mantendo a ordem dentro de cada grupo
    res.sort(key=lambda e: not e.get("complete", False))
    return res[:limit]


@mcp.tool()
def get_item(item_id: str) -> dict:
    """Detalhes de um item: corpos suportados, animações com arte em cada corpo,
    cores (recolor) ou variantes, partes com cores separadas e animações especiais."""
    d = ITEMS[item_id]
    bodies = _item_bodies(d)
    info = {"id": item_id, "name": d.get("name"), "type": d.get("type_name"),
            "body_types": bodies,
            "animations": {b: item_animations(item_id, b) for b in bodies}}
    if is_equipment(item_id):
        info["equipment"] = True
    else:
        info["missing_animations"] = {b: animation_gaps(item_id, b) for b in bodies}
        info["complete"] = {b: not info["missing_animations"][b] for b in bodies}
        alts = {b: complete_alternatives(item_id, b, 3) for b in bodies if info["missing_animations"][b]}
        if alts:
            info["complete_alternatives"] = alts
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
                       layout: str = "standard", split: bool | str | list[str] = False,
                       export: list[str] | None = None, prefer_complete: bool = False) -> dict:
    """Gera a spritesheet do personagem e salva em PNG.

    Todo resultado traz `animation_check`: se todos os itens têm todas as animações e,
    se não, quais faltam e alternativas completas. AVISE o usuário quando complete=false.
    prefer_complete=True troca sozinho itens incompletos pelo parecido mais próximo que
    tem todas as animações (mantendo a cor quando dá) e lista as trocas em `replaced`.

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
    split: também salva em partes. True ou "animation" = um PNG por animação (<nome>_anims/);
           "frame" = um PNG por quadro (<nome>_frames/<animação>/<direção>_NN.png);
           "item" = uma folha por item (<nome>_items/), para trocar roupas no jogo.
           Pode ser uma lista: ["animation", "frame"].
    export: arquivos prontos para engines: "godot" (SpriteFrames .tres), "unity" (.meta com os
           sprites fatiados + clipes .anim), "web" (atlas JSON para Phaser/PixiJS + página de
           demonstração), "site" (JSON para o botão "Import from Clipboard" do site).
    Sempre salva <nome>_credits.txt e <nome>_credits.csv com autores e licenças das artes usadas.
    """
    if layout not in ("standard", "compact"):
        return {"error": "layout deve ser 'standard' ou 'compact'"}
    if split is True:
        split_modes = ["animation"]
    elif not split:
        split_modes = []
    else:
        split_modes = [split] if isinstance(split, str) else list(split)
    bad = set(split_modes) - {"animation", "item", "frame"}
    if bad:
        return {"error": f"split inválido: {sorted(bad)}. Use animation, item e/ou frame."}
    bad = set(export or []) - set(EXPORTERS)
    if bad:
        return {"error": f"export inválido: {sorted(bad)}. Use {sorted(EXPORTERS)}."}

    replaced = []
    if prefer_complete:
        swapped = []
        for it in items:
            new = None
            if it.get("id") in ITEMS and not is_equipment(it["id"]) and animation_gaps(it["id"], body_type):
                new = _swap_for_complete(it, body_type)
            if new:
                replaced.append({"from": it["id"], "to": new["id"]})
            swapped.append(new or it)
        items = swapped

    comp = _compose(items, body_type, animations)
    if "error" in comp:
        return comp
    items, rows = comp["items"], comp["rows"]
    final, index = _assemble(rows, layout)

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / filename
    final.save(path)
    result = {"file": str(path), "size": list(final.size), "frame": 64, "layout": layout,
              "animations": index}
    used = set(_used_files)

    if "animation" in split_modes:
        folder = OUT / f"{path.stem}_anims"
        folder.mkdir(exist_ok=True)
        for anim, s, _ in rows:
            s.save(folder / f"{anim}.png")
        result["split_folder"] = str(folder)
    if "frame" in split_modes:
        folder = OUT / f"{path.stem}_frames"
        for anim, s, frame in rows:
            info = index[anim]
            for r, direction in enumerate(info["directions"]):
                sub = folder / anim
                sub.mkdir(parents=True, exist_ok=True)
                for c in range(info["columns"]):
                    cell = s.crop((c * frame, r * frame, (c + 1) * frame, (r + 1) * frame))
                    if cell.getbbox():
                        cell.save(sub / f"{direction}_{c:02d}.png")
        result["frames_folder"] = str(folder)
    if "item" in split_modes:
        folder = OUT / f"{path.stem}_items"
        folder.mkdir(exist_ok=True)
        for it in items:
            one = _compose([it], body_type, animations, inherit_from=items)
            if "error" not in one:
                img, _ = _assemble(one["rows"], layout, like=index)
                img.save(folder / f"{it['id'].replace('/', '__')}.png")
        result["items_folder"] = str(folder)

    _used_files.clear()
    _used_files.update(used)
    result["credits"] = _write_credits(_credits(items), OUT / path.stem)
    if export:
        by_anim = _missing_by_animation(comp["missing"], index)
        result["exports"] = {e: EXPORTERS[e](path, final, index, items, body_type, by_anim) for e in export}
    if comp["missing"]:
        # item sem arte para esse corpo/animação: não aparece nessas linhas
        result["missing"] = comp["missing"]
    if comp["warnings"]:
        result["warnings"] = comp["warnings"]
    if replaced:
        result["replaced"] = replaced
    result["animation_check"] = animation_report(items, body_type)
    return result


def _missing_by_animation(missing, index):
    """{item: [anims] | {only_in}} -> {animação: [nomes dos itens que não aparecem nela]}."""
    out = {}
    for item_id, info in missing.items():
        lacking = [a for a in index if a in ANIMATIONS and a not in info["only_in"]]             if isinstance(info, dict) else info
        for a in lacking:
            out.setdefault(a, []).append(ITEMS[item_id]["name"])
    return out


DIRECTIONS = ["up", "left", "down", "right"]


def _compose(items, body_type, animations=None, inherit_from=None):
    """Monta as camadas de cada animação. Devolve {items, rows, missing, warnings}
    (rows = [(animação, imagem, tamanho do quadro)]) ou {error}."""
    anims = animations or ANIMATIONS
    _used_files.clear()
    for it in items:
        if it["id"] not in ITEMS:
            return {"error": f"item desconhecido: {it['id']}"}
    if body_type not in BODY_TYPES:
        return {"error": f"body_type deve ser um de {BODY_TYPES}"}

    # um item por tipo, como no site: o último pedido vence
    warnings, by_type = [], {}
    for it in items:
        t = ITEMS[it["id"]].get("type_name")
        if t in by_type and by_type[t]["id"] != it["id"]:
            warnings.append(f"{it['id']} substituiu {by_type[t]['id']} (mesmo tipo: {t})")
        by_type[t] = it
    items = [it for it in items if by_type.get(ITEMS[it["id"]].get("type_name")) is it]

    # cor da pele: itens com match_body_color sem cor herdam a cor do corpo
    skin = next((it.get("color") for it in (inherit_from or items)
                 if ITEMS[it["id"]].get("match_body_color") and it.get("color")), None)
    items = [dict(it, color=skin) if skin and not it.get("color")
             and ITEMS[it["id"]].get("match_body_color") else it for it in items]

    # nomes escolhidos por tipo, para resolver caminhos como head/faces/${head}/...
    names = {ITEMS[it["id"]]["type_name"]: ITEMS[it["id"]]["name"].replace(" ", "_")
             for it in (inherit_from or items)}
    layers = []  # (zPos, ordem, item, layer, pedido)
    for n, it in enumerate(items):
        d = ITEMS[it["id"]]
        for k, v in d.items():
            if not k.startswith("layer_"):
                continue
            if "${" in (v.get(body_type) or ""):
                path = _fill_path(d, v[body_type], names)
                if path is None:
                    need = ", ".join(sorted(d.get("replace_in_path", {})))
                    msg = f"{it['id']} não combina com o {need} escolhido e foi ignorado"
                    if msg not in warnings:
                        warnings.append(msg)
                    continue
                v = dict(v, **{body_type: path})
            layers.append((v.get("zPos", 0), n, d, v, it))
    layers.sort(key=lambda t: (t[0], t[1]))

    customs = []
    for _, _, _, layer, _ in layers:
        name = layer.get("custom_animation")
        if name and layer.get(body_type) and name not in customs and _custom_base(name) in anims:
            customs.append(name)

    # baixa tudo o que vai ser usado de uma vez, em paralelo
    rels = []
    for _, _, d, layer, it in layers:
        path = layer.get(body_type)
        if not path:
            continue
        if layer.get("custom_animation"):
            rels.append(_item_rel(d, it, path))
        else:
            rels += [_item_rel(d, it, path, a) for a in anims]
    _prefetch(rels)

    rows, missing, drawn_in = [], {}, {}
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
        if sheet is None:
            continue
        rows.append((anim, _apply_mask(sheet), 64))
        # itens que só têm animação especial nessa base não contam como faltando aqui
        special = {it["id"] for _, _, _, l, it in layers
                   if l.get("custom_animation") and l.get(body_type)
                   and _custom_base(l["custom_animation"]) == anim}
        for it in items:
            if it["id"] in drawn | special:
                drawn_in.setdefault(it["id"], []).append(anim)
            else:
                missing.setdefault(it["id"], []).append(anim)

    for name in customs:
        sheet, _ = _render_custom(name, layers, body_type)
        if sheet is not None:
            rows.append((name, sheet, _custom_animations()[name]["frameSize"]))

    if not rows:
        return {"error": "nenhuma camada encontrada para essa combinação"}
    # aviso curto: se o item falta na maioria, diz só onde ele aparece
    for item_id, lacking in list(missing.items()):
        present = drawn_in.get(item_id, [])
        if present and len(lacking) > len(present):
            missing[item_id] = {"only_in": present}
    return {"items": items, "rows": rows, "missing": missing, "warnings": warnings}


def _assemble(rows, layout, like=None):
    """Junta as animações numa imagem só. `like` reaproveita as posições de outro índice."""
    index = {}
    if layout == "standard":
        custom_h = sum(s.height for a, s, _ in rows if a not in STANDARD_ROWS)
        w = max([SHEET_WIDTH] + [s.width for _, s, _ in rows])
        h = SHEET_HEIGHT + custom_h
        if like:
            h = max(h, max(i["y"] + i["height"] for i in like.values()))
            w = max(w, max(i["columns"] * i["frame"] for i in like.values()))
        final = Image.new("RGBA", (w, h))
        y = SHEET_HEIGHT
        for anim, s, frame in rows:
            if like and anim in like:
                pos = like[anim]["y"]
            elif anim in STANDARD_ROWS:
                pos = STANDARD_ROWS[anim] * 64
            else:
                pos, y = y, y + s.height
            final.paste(s, (0, pos))
            index[anim] = _row_info(anim, s, frame, pos)
    else:
        if like:
            final = Image.new("RGBA", (max(i["columns"] * i["frame"] for i in like.values()),
                                       max(i["y"] + i["height"] for i in like.values())))
            for anim, s, frame in rows:
                if anim in like:
                    final.paste(s, (0, like[anim]["y"]))
                    index[anim] = _row_info(anim, s, frame, like[anim]["y"])
            return final, index
        final = Image.new("RGBA", (max(s.width for _, s, _ in rows), sum(s.height for _, s, _ in rows)))
        y = 0
        for anim, s, frame in rows:
            final.paste(s, (0, y))
            index[anim] = _row_info(anim, s, frame, y)
            y += s.height
    return final, index


def _row_info(anim, img, frame, y):
    n_dirs = max(1, img.height // frame)
    return {"y": y, "height": img.height, "frame": frame, "columns": img.width // frame,
            "directions": DIRECTIONS if n_dirs == 4 else ["down"] * n_dirs}


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


def _aliases():
    """Nomes antigos que o site ainda aceita em links (campo "aliases" das definições):
    (tipos renomeados, prefixos de nome renomeados, valores exatos -> item)."""
    types, prefixes, exact = {}, {}, {}
    for item_id, d in ITEMS.items():
        for orig, alias in d.get("aliases", {}).items():
            # formato: "[tipo=]valor"
            o_type, o_val = orig.split("=", 1) if "=" in orig else ("", orig)
            a_type, a_val = alias.split("=", 1) if "=" in alias else ("", alias)
            type_name = o_type or d["type_name"]
            if o_val == "*" and a_val == "*":
                types[type_name] = a_type or d["type_name"]
            elif o_val.endswith("_*") and a_val.endswith("_*"):
                prefixes.setdefault(type_name, []).append((o_val[:-1], a_val[:-1]))
            else:
                target = a_val.split(".")[-1]  # 'metal.bronze' / 'all.lpcr.olivine' -> cor
                if target in (d.get("variants") or []):
                    exact.setdefault(type_name, {})[o_val.lower()] = {"id": item_id, "variant": target}
                else:
                    exact.setdefault(type_name, {})[o_val.lower()] = {"id": item_id, "color": target}
    return types, prefixes, exact


def parse_url(url: str) -> dict:
    frag = url.split("#", 1)[1] if "#" in url else url
    params = [p.split("=", 1) for p in frag.split("&") if "=" in p]
    by_type, subs = _by_type(), _sub_parts()
    alias_types, alias_prefixes, alias_exact = _aliases()
    body, items, unresolved, extras = "male", [], {}, []
    for key, value in params:
        value = urllib.parse.unquote(value)
        key = alias_types.get(key, key)
        for old, new in alias_prefixes.get(key, []):
            if value.startswith(old):
                value = new + value[len(old):]
        if key in ("sex", "bodyType"):
            body = value
        elif value.lower() in alias_exact.get(key, {}):
            items.append(dict(alias_exact[key][value.lower()]))
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
        # sorteia só entre itens com todas as animações; acessório opcional sem versão
        # completa (ex.: capas) fica de fora
        complete = [i for i in pool if is_complete(i, body_type)]
        if complete:
            pool = complete
        elif chance < 1:
            continue
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
                    "complete": r.get("animation_check", {}).get("complete"),
                    "url": build_url(items, body), **({"error": r["error"]} if "error" in r else {})})
    return {"count": len(out), "characters": out}


# ---------- prévia no chat ----------
PREVIEW_BG = (236, 236, 236, 255)


def _preview_frames(items, body_type, animation):
    """Quadros da prévia: para cada instante, as 4 direções lado a lado. Devolve (quadros, fps, nota)."""
    special = animation in _custom_animations()
    base = _custom_base(animation) if special else animation
    if base not in ANIMATIONS:
        raise ValueError(f"animação desconhecida: {animation}. Use uma de {ANIMATIONS} ou uma especial.")
    comp = _compose(items, body_type, [base])
    if "error" in comp:
        raise ValueError(comp["error"])
    rows = {a: (img, f) for a, img, f in comp["rows"]}
    if animation not in rows:
        raise ValueError(f"a animação '{animation}' não existe para esses itens: {list(rows)}")
    img, f = rows[animation]
    info = _row_info(animation, img, f, 0)
    clips = exporters.frames_of(img, {animation: info})
    length = max(len(cells) for *_, cells in clips)
    scale = 3 if f == 64 else 2
    frames = []
    for i in range(length):
        strip = Image.new("RGBA", (f * len(clips), f), PREVIEW_BG)
        for d, (*_, cells) in enumerate(clips):
            x, y, _ = cells[min(i, len(cells) - 1)]
            strip.alpha_composite(img.crop((x, y, x + f, y + f)), (d * f, 0))
        frames.append(strip.resize((strip.width * scale, strip.height * scale), Image.NEAREST))
    note = {"animation": animation, "body_type": body_type, "frames": length,
            "directions": [c[2] for c in clips]}
    if comp["missing"]:
        note["missing"] = comp["missing"]
    if comp["warnings"]:
        note["warnings"] = comp["warnings"]
    note["animation_check"] = animation_report(comp["items"], body_type)["summary"]
    return frames, exporters._fps(animation), note


@mcp.tool()
def preview_character(items: list[dict], body_type: str = "male", animation: str = "walk",
                      animated: bool = True):
    """Mostra o personagem direto no chat, sem salvar arquivos: as 4 direções lado a lado.
    animated=True (padrão) devolve um GIF animado tocando a animação; False, uma imagem parada.
    animation: walk, idle, slash, run... ou uma especial (tool_hammer, slash_128, walk_128...).
    Use para conferir o visual antes de generate_character."""
    try:
        frames, fps, note = _preview_frames(items, body_type, animation)
    except ValueError as e:
        return str(e)
    buf = io.BytesIO()
    if animated and len(frames) > 1:
        rgb = [fr.convert("RGB") for fr in frames]
        rgb[0].save(buf, "GIF", save_all=True, append_images=rgb[1:], duration=int(1000 / fps),
                    loop=0, disposal=2)
        fmt = "gif"
    else:
        # quadro parado: no walk o 1º quadro é a pose de pé; usa o do meio do movimento
        frames[min(1, len(frames) - 1) if animation.startswith("walk") else 0].save(buf, "PNG")
        fmt = "png"
    return [MCPImage(data=buf.getvalue(), format=fmt), json.dumps(note, ensure_ascii=False)]


# ---------- atualização ----------
@mcp.tool()
def update_definitions(clear_image_cache: bool = False) -> dict:
    """Atualiza os itens e paletas a partir do repositório oficial do gerador LPC
    (novos itens, correções). clear_image_cache=True também apaga os PNGs baixados,
    para que sejam baixados de novo na versão nova."""
    global ITEMS, _FILES, _CUSTOM_ANIMS
    import shutil
    import subprocess
    run = lambda *a: subprocess.run(a, cwd=REPO, check=True, capture_output=True,
                                    text=True, encoding="utf8").stdout.strip()
    before, count_before = run("git", "rev-parse", "HEAD"), len(ITEMS)
    run("git", "fetch", "--depth", "1", "--filter=blob:none", "origin", "master")
    run("git", "reset", "--hard", "FETCH_HEAD")
    after = run("git", "rev-parse", "HEAD")
    if after != before:
        global _SPRITE_DIRS
        ITEMS, _FILES, _CUSTOM_ANIMS, _SPRITE_DIRS = _load_items(), None, None, None
        item_animations.cache_clear()
        (CACHE / "_custom-animations.ts").unlink(missing_ok=True)
        if clear_image_cache:
            for p in CACHE.iterdir():
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
    return {"updated": after != before, "from": before[:10], "to": after[:10],
            "items_before": count_before, "items_now": len(ITEMS),
            "image_cache_cleared": bool(clear_image_cache and after != before)}


# ---------- exportação ----------
def _export_site(path, img, index, items, body_type, missing=None):
    """JSON aceito pelo botão "Import from Clipboard" do site do gerador."""
    out = Path(path).with_name(f"{Path(path).stem}_site.json")
    out.write_text(json.dumps({"version": 1, "url": build_url(items, body_type)}, indent=2),
                   encoding="utf8")
    return {"file": str(out), "url": build_url(items, body_type),
            "how_to_use": "No site, copie o conteúdo do arquivo e clique em Import from Clipboard (JSON)."}


EXPORTERS = {
    "godot": lambda path, img, index, items, body, missing: exporters.godot(path, img, index),
    "unity": lambda path, img, index, items, body, missing: exporters.unity(path, img, index),
    "web": lambda path, img, index, items, body, missing: exporters.web(path, img, index, missing),
    "site": _export_site,
}


if __name__ == "__main__":
    import sys
    if "--setup" in sys.argv:
        # só prepara (baixa as definições na importação e a lista de arquivos) e sai
        _sprite_files()
        _custom_animations()
        print(f"lpc-mcp pronto: {len(ITEMS)} itens em {DEFS}")
    else:
        mcp.run()
