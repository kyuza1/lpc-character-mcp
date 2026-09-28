"""Catálogo: definições dos itens do LPC, paletas de cores e quais animações existem."""
import functools
import json
import re
import sys

from .paths import DATA

REPO = DATA / "lpc"
DEFS = REPO / "sheet_definitions"
PALS = REPO / "palette_definitions"
CACHE = DATA / "cache"
RAW = "https://raw.githubusercontent.com/LiberatedPixelCup/Universal-LPC-Spritesheet-Character-Generator/master/spritesheets/"

BODY_TYPES = ["male", "female", "muscular", "pregnant", "teen", "child"]
# Ordem padrão da spritesheet ULPC (cada linha = 64px por direção)
ANIMATIONS = ["spellcast", "thrust", "walk", "slash", "shoot", "hurt", "climb", "idle",
              "jump", "sit", "emote", "run", "combat_idle", "backslash", "halfslash"]


# ---------- catálogo ----------
def _ensure_definitions():
    """Na primeira execução, baixa só as pastas de definições JSON do repositório (sem os PNGs)."""
    if DEFS.exists():
        return
    import shutil
    import subprocess
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


def _color_list(it):
    """'color' pode ser uma string ou uma lista (uma cor por parte: color_1, color_2...)."""
    c = it.get("color")
    return c if isinstance(c, list) else [c]


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
    # só conta o que o próprio corpo tem (o musculoso, por ex., não tem shoot nem climb)
    if item_id != "body/body":
        ok |= set(ANIMATIONS) - set(item_animations("body/body", body))
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


# corpo e cabeça definem o personagem: nunca são sugeridos para troca
BASE_PREFIXES = ("body/body", "head/heads/")


def complete_alternatives(item_id, body, limit=5):
    """Itens completos do mesmo tipo, os mais parecidos primeiro (mesma pasta, palavras do nome)."""
    if item_id.startswith(BASE_PREFIXES):
        return []
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
    """Relatório para o usuário: limitações do próprio corpo, itens incompletos (com
    alternativas) e equipamentos."""
    incomplete, equipment = {}, {}
    body_missing = [a for a in ANIMATIONS if a not in item_animations("body/body", body)]         if body in _item_bodies(ITEMS["body/body"]) else []
    for it in items:
        i = it["id"]
        if i == "body/body" or i not in ITEMS or body not in _item_bodies(ITEMS[i]):
            continue
        if is_equipment(i):
            equipment[i] = item_animations(i, body) + _special_animations(i, body)
            continue
        gaps = animation_gaps(i, body)
        if gaps:
            incomplete[i] = {"missing": gaps, "complete_alternatives": complete_alternatives(i, body, 3)}
    report = {"complete": not incomplete and not body_missing, "incomplete_items": incomplete}
    if body_missing:
        # o corpo base não tem essas animações no LPC: nenhuma peça aparece nelas
        report["body_missing"] = body_missing
    if equipment:
        report["equipment_only_in"] = equipment
    partes = []
    if body_missing:
        partes.append(f"o corpo {body} do LPC não tem {', '.join(body_missing)} "
                      f"(nenhuma peça resolve; use outro tipo de corpo se precisar delas)")
    for i, info in incomplete.items():
        alt = f" (completos parecidos: {', '.join(info['complete_alternatives'])})"             if info["complete_alternatives"] else " (não há alternativa completa do mesmo tipo)"
        partes.append(f"{ITEMS[i]['name']} não tem {', '.join(info['missing'])}{alt}")
    if partes:
        dica = (" Use prefer_complete=True para trocar por itens completos."
                if any(v["complete_alternatives"] for v in incomplete.values()) else "")
        report["summary"] = "ATENÇÃO: nem todas as animações ficaram completas: " + "; ".join(partes) + "." + dica
    else:
        report["summary"] = "Todas as animações estão completas para todos os itens."
    return report


def reload():
    """Relê as definições depois de uma atualização (o dicionário ITEMS é trocado no lugar,
    então quem já importou ITEMS enxerga os itens novos)."""
    global _FILES, _SPRITE_DIRS
    ITEMS.clear()
    ITEMS.update(_load_items())
    _FILES = _SPRITE_DIRS = None
    item_animations.cache_clear()
