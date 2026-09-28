"""MCP server que gera personagens LPC (Universal LPC Spritesheet Character Generator).

Lê as definições JSON do repositório oficial (clonadas em <dados>/lpc) e baixa os PNGs
sob demanda do GitHub (cache em <dados>/cache). Veja `_data_dir` para onde fica <dados>.
"""
import io
import json
import random
from pathlib import Path

from mcp.server.mcpserver import Image as MCPImage
from mcp.server.mcpserver import MCPServer
from PIL import Image

from . import exporters
from . import catalog, render
from .i18n import t
from .paths import OUT
from .catalog import (ANIMATIONS, CACHE, ITEMS, REPO, _colors_for, _default_color, _item_bodies, _recolor_entries, _special_animations, _swap_for_complete, animation_gaps, animation_report, complete_alternatives, is_complete, is_equipment, item_animations)
from .render import (_assemble, _compose, _credits, _custom_animations, _custom_base, _missing_by_animation, _row_info, _used_files, _write_credits)
from .links import build_url, parse_url

mcp = MCPServer(
    "lpc-character-generator",
    instructions=(
        "Generates LPC pixel-art characters. Reply in the user's language. When choosing items, "
        "prefer ones that have every animation (search_items marks 'complete' and lists complete "
        "items first). After generate_character, ALWAYS read 'animation_check': if complete=false, "
        "tell the user which items lack which animations and offer the complete alternatives or "
        "regenerating with prefer_complete=True. Do not use prefer_complete unless the user asks or "
        "agrees, because it swaps items and changes the look. Weapons and tools only appear in their "
        "own animations (equipment_only_in) - that is normal; animations the body itself lacks are "
        "listed in body_missing. Use preview_character to show the result."
    ),
)


# ---------- ferramentas MCP ----------
@mcp.tool()
def list_categories() -> dict:
    """Lists item categories (e.g. body, hair, torso/shirts) with how many items each has."""
    cats = {}
    for i in ITEMS:
        cat = i.rsplit("/", 1)[0]
        cats[cat] = cats.get(cat, 0) + 1
    return dict(sorted(cats.items()))


@mcp.tool()
def search_items(query: str = "", category: str = "", body_type: str = "",
                 animation: str = "", type_name: str = "", complete_only: bool = False,
                 limit: int = 50) -> list[dict]:
    """Searches items. All filters are optional and combine:
    query: words in the name/id (all must match), e.g. "leather armour".
    category: id prefix, e.g. 'hair', 'torso/shirts', 'weapons/sword'.
    body_type: only items that exist for this body (male, female, teen...).
    animation: only items with art for this animation (idle, walk, slash...) for body_type
               (or male if body_type is not given).
    type_name: item type (hair, clothes, legs, shoes, weapon, hat...).
    complete_only: only items with every animation. Otherwise complete items come first.
    Each result says whether it is complete and which animations are missing (for body_type or male)."""
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
    """Item details: supported bodies, animations with art per body, missing animations and
    complete alternatives, colors or variants, multi-color parts and oversized animations."""
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
                       export: list[str] | None = None, prefer_complete: bool = False,
                       output_dir: str | None = None) -> dict:
    """Builds the character spritesheet and saves it as PNG.

    Every result has `animation_check`: whether every item has every animation and, if not,
    what is missing plus complete alternatives. TELL the user when complete=false.
    prefer_complete=True swaps incomplete items for the closest item with every animation
    (keeping the color when possible) and lists the swaps in `replaced`. Only use it with the
    user's consent: it changes the look (e.g. apron becomes overalls).
    output_dir: folder to save into (e.g. the game project's sprites folder). Inside a Godot
           project the .tres gets the right res:// path; for Unity, save inside Assets/.
           Default: LPC_OUTPUT_DIR or ~/lpc-characters.

    items: list of {"id": "<item id>", "color": "<color>" | ["<color 1>", "<color 2>"], "variant": "<variant>"}.
           Include a body (body/body) and a head (e.g. head/heads/human/heads_human_male).
           Skin items (head, ears, nose...) without a color inherit the body color.
           Multi-part items (see `color_parts` in get_item) accept a list of colors.
    body_type: male | female | muscular | pregnant | teen | child
    animations: subset of walk, idle, slash, thrust, spellcast, shoot, hurt, run, jump... (default: all).
           Oversized weapon/tool animations (e.g. slash_128, tool_hammer) are added automatically
           when their base animation (slash, thrust...) is requested.
    layout: "standard" = same layout as the site (832px wide, each animation always on the same
           row; oversized animations below y=3456). It is what Godot/Unity/RPG Maker importers expect.
           "compact" = only the requested animations, stacked.
    split: also save pieces. True or "animation" = one PNG per animation (<name>_anims/);
           "frame" = one PNG per frame (<name>_frames/<animation>/<direction>_NN.png);
           "item" = one sheet per item (<name>_items/), for swapping outfits in-game.
           Can be a list: ["animation", "frame"].
    export: engine-ready files: "godot" (SpriteFrames .tres), "unity" (sliced sprites .meta,
           .anim clips and an AnimatorController), "web" (JSON atlas for Phaser/PixiJS + demo page),
           "site" (JSON for the generator site's "Import from Clipboard" button).
    Always writes <name>_credits.txt and <name>_credits.csv with authors and licenses of the art used.
    """
    if layout not in ("standard", "compact"):
        return {"error": t("bad_layout")}
    if split is True:
        split_modes = ["animation"]
    elif not split:
        split_modes = []
    else:
        split_modes = [split] if isinstance(split, str) else list(split)
    bad = set(split_modes) - {"animation", "item", "frame"}
    if bad:
        return {"error": t("bad_split", bad=sorted(bad))}
    bad = set(export or []) - set(EXPORTERS)
    if bad:
        return {"error": t("bad_export", bad=sorted(bad), valid=sorted(EXPORTERS))}

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

    out = Path(output_dir).expanduser() if output_dir else OUT
    out.mkdir(parents=True, exist_ok=True)
    path = out / filename
    final.save(path)
    result = {"file": str(path), "size": list(final.size), "frame": 64, "layout": layout,
              "animations": index}
    used = set(_used_files)

    if "animation" in split_modes:
        folder = out / f"{path.stem}_anims"
        folder.mkdir(exist_ok=True)
        for anim, s, _ in rows:
            s.save(folder / f"{anim}.png")
        result["split_folder"] = str(folder)
    if "frame" in split_modes:
        folder = out / f"{path.stem}_frames"
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
        folder = out / f"{path.stem}_items"
        folder.mkdir(exist_ok=True)
        for it in items:
            one = _compose([it], body_type, animations, inherit_from=items)
            if "error" not in one:
                img, _ = _assemble(one["rows"], layout, like=index)
                img.save(folder / f"{it['id'].replace('/', '__')}.png")
        result["items_folder"] = str(folder)

    _used_files.clear()
    _used_files.update(used)
    result["credits"] = _write_credits(_credits(items), out / path.stem)
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


@mcp.tool()
def from_site_url(url: str) -> dict:
    """Reads a link from the LPC generator site (e.g. ...Character-Generator/#sex=male&body=Body_Color_light&...)
    and returns {body_type, items} ready for generate_character (old links work too).
    Unrecognized parameters are listed in `unresolved`."""
    return parse_url(url)


@mcp.tool()
def to_site_url(items: list[dict], body_type: str = "male") -> str:
    """Builds a generator site link with these items, to open and tweak the character in a browser."""
    for it in items:
        if it["id"] not in ITEMS:
            raise ValueError(t("unknown_item", id=it["id"]))
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
    # corpos sem camisas no LPC (ex.: musculoso) caem nas peças de reserva
    (1.0, ["torso/shirts"], None, ["torso/vest", "torso/jacket/", "torso/armour", "torso/aprons"]),
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
    for chance, prefixes, bodies, *fallback in RANDOM_SLOTS:
        if bodies and body_type not in bodies or rng.random() > chance:
            continue

        def slot_pool(prefs):
            return [i for i in ITEMS if any(i.startswith(p) for p in prefs)
                    and _supports(i, body_type) and not ITEMS[i].get("match_body_color")]
        pool = slot_pool(prefixes) or (slot_pool(fallback[0]) if fallback else [])
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
    """Rolls a random character (skin, head, hair, clothes, shoes and sometimes a beard, hat or
    vest), using only items that have every animation. Does not render: returns
    {items, body_type, url} to review and pass to generate_character. `fixed_items` are always
    added (e.g. a weapon). Use `seed` to repeat the same roll."""
    items = random_items(body_type, random.Random(seed), fixed_items)
    return {"body_type": body_type, "items": items, "url": build_url(items, body_type)}


@mcp.tool()
def generate_batch(count: int = 5, body_types: list[str] | None = None, seed: int | None = None,
                   prefix: str = "npc", fixed_items: list[dict] | None = None,
                   animations: list[str] | None = None, layout: str = "standard",
                   split: bool = False, export: list[str] | None = None,
                   output_dir: str | None = None) -> dict:
    """Generates many random characters at once (e.g. villagers for a town).
    Saves <prefix>_01.png, <prefix>_02.png... and the credits for each.
    body_types: bodies to pick from (default: male and female).
    fixed_items: items everyone gets (e.g. [{"id": "tools/tool_hammer"}])."""
    rng = random.Random(seed)
    bodies = body_types or ["male", "female"]
    out = []
    for n in range(1, count + 1):
        body = rng.choice(bodies)
        items = random_items(body, rng, fixed_items)
        r = generate_character(items, body, animations, f"{prefix}_{n:02d}.png", layout, split,
                               export, output_dir=output_dir)
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
        raise ValueError(t("unknown_animation", anim=animation, valid=ANIMATIONS))
    comp = _compose(items, body_type, [base])
    if "error" in comp:
        raise ValueError(comp["error"])
    rows = {a: (img, f) for a, img, f in comp["rows"]}
    if animation not in rows:
        raise ValueError(t("animation_not_available", anim=animation, available=list(rows)))
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
    """Shows the character in the chat without saving files: the 4 directions side by side.
    animated=True (default) returns an animated GIF of the animation; False, a still image.
    animation: walk, idle, slash, run... or an oversized one (tool_hammer, slash_128, walk_128...).
    Use it to check the look before generate_character."""
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


# ---------- cache ----------
def _cache_images():
    """PNGs baixados no cache (sem os arquivos internos que começam com _)."""
    if not CACHE.exists():
        return []
    return [p for p in CACHE.rglob("*") if p.is_file() and not p.relative_to(CACHE).parts[0].startswith("_")]


@mcp.tool()
def clear_cache(older_than_days: int = 0, dry_run: bool = False) -> dict:
    """Deletes cached images (they are downloaded again when needed).
    older_than_days: only delete images unused for more than N days (0 = all).
    dry_run: only report how much would be freed, without deleting."""
    import time
    limit = time.time() - older_than_days * 86400
    files = [p for p in _cache_images() if not older_than_days or p.stat().st_atime < limit]
    size = sum(p.stat().st_size for p in files)
    if not dry_run:
        for p in files:
            p.unlink(missing_ok=True)
        for d in sorted((d for d in CACHE.rglob("*") if d.is_dir()), key=lambda d: len(d.parts), reverse=True):
            if not any(d.iterdir()):
                d.rmdir()
    remaining = sum(p.stat().st_size for p in _cache_images())
    return {"files": len(files), "freed_mb" if not dry_run else "would_free_mb": round(size / 2**20, 1),
            "cache_now_mb": round(remaining / 2**20, 1), "cache_dir": str(CACHE)}


# ---------- atualização ----------
@mcp.tool()
def update_definitions(clear_image_cache: bool = False) -> dict:
    """Pulls new items and palettes from the official LPC generator repository.
    clear_image_cache=True also deletes downloaded PNGs so they are fetched again."""
    import shutil
    import subprocess
    run = lambda *a: subprocess.run(a, cwd=REPO, check=True, capture_output=True,
                                    text=True, encoding="utf8").stdout.strip()
    before, count_before = run("git", "rev-parse", "HEAD"), len(ITEMS)
    run("git", "fetch", "--depth", "1", "--filter=blob:none", "origin", "master")
    run("git", "reset", "--hard", "FETCH_HEAD")
    after = run("git", "rev-parse", "HEAD")
    if after != before:
        catalog.reload()
        render.reset_caches()
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
            "how_to_use": t("site_how")}


EXPORTERS = {
    "godot": lambda path, img, index, items, body, missing: exporters.godot(path, img, index),
    "unity": lambda path, img, index, items, body, missing: exporters.unity(path, img, index),
    "web": lambda path, img, index, items, body, missing: exporters.web(path, img, index, missing),
    "site": _export_site,
}


if __name__ == "__main__":
    from .cli import main
    main()
