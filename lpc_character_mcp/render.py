"""Montagem das imagens: baixa as camadas, troca cores, aplica máscaras e monta as animações."""
import csv
import re
import threading
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from .catalog import (ANIMATIONS, BODY_TYPES, CACHE, INTENTIONAL_GAPS, ITEMS, RAW, REPO, _base_colors, _color_list, _colors_for, _fill_path, _hex, _recolor_entries, _sprite_files, is_equipment)

# Layout padrão do site (spritesheet "universal"): linha inicial de cada animação
STANDARD_ROWS = {"spellcast": 0, "thrust": 4, "walk": 8, "slash": 12, "shoot": 16, "hurt": 20,
                 "climb": 21, "idle": 22, "jump": 26, "sit": 30, "emote": 34, "run": 38,
                 "combat_idle": 42, "backslash": 46, "halfslash": 50}
SHEET_WIDTH, SHEET_HEIGHT = 832, 3456  # 13 x 54 quadros de 64px


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
    # mesmo critério do animation_check: equipamentos (armas, ferramentas) e faltas
    # intencionais (ex.: barba ao escalar, de costas) não são aviso
    for item_id, lacking in list(missing.items()):
        if is_equipment(item_id):
            del missing[item_id]
            continue
        intentional = set().union(*(gaps for prefixes, gaps in INTENTIONAL_GAPS
                                    if item_id.startswith(prefixes)))
        lacking = [a for a in lacking if a not in intentional]
        if lacking:
            missing[item_id] = lacking
        else:
            del missing[item_id]
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


def reset_caches():
    """Esquece as animações especiais lidas (depois de atualizar as definições)."""
    global _CUSTOM_ANIMS
    _CUSTOM_ANIMS = None
    (CACHE / "_custom-animations.ts").unlink(missing_ok=True)
