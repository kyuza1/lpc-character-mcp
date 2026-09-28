"""Links do site do gerador LPC: lê e monta a parte depois do # (inclusive nomes antigos)."""
import urllib.parse

from .catalog import ITEMS, _color_list, _colors_for, _default_color, _recolor_entries

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
