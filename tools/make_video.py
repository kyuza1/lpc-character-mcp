"""Promo media made with the MCP itself.

    python tools/make_video.py            # videos + install gifs, English and Portuguese
    python tools/make_video.py --gif      # only the install gifs

output/promo.mp4       1280x720 video: ask -> result -> engines -> showcase -> install
output/promo_pt.mp4    the same in Portuguese
docs/install.gif       the install in a terminal (cmd); docs/install_pt.gif in Portuguese
docs/chat.gif          asking the AI for a character and getting it; docs/chat_pt.gif in Portuguese
docs/media_credits.*   authors and licenses of every sprite shown in the media

The terminal text is the real output of a fresh install (paths shortened to the defaults).
Needs ffmpeg on PATH for the video.
"""
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import make_showcase as ms  # noqa: E402
from lpc_character_mcp import render, server  # noqa: E402
from lpc_character_mcp.catalog import LICENSE_FAMILIES, license_family  # noqa: E402

W, H, FPS = 1280, 720, 30
DOCS, OUT = ROOT / "docs", ROOT / "output"
FONTS = Path("C:/Windows/Fonts")
BG = (13, 15, 21)
PANEL = (24, 27, 36)
PANEL2 = (32, 36, 48)
TEXT = (232, 234, 242)
DIM = (140, 147, 164)
GOLD = (255, 196, 76)
GREEN = (120, 210, 130)
BLUE = (110, 170, 255)


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def bold(size):
    return font("segoeuib.ttf", size)


def regular(size):
    return font("segoeui.ttf", size)


def mono(size):
    return font("CascadiaMono.ttf", size)


LANG = "en"
TX = {  # key: (English, Portuguese)
    "install": ("Install with one command", "Instale com um comando"),
    "install_sub": ("uv downloads Python and the package - then register it in your AI",
                    "O uv baixa o Python e o pacote - depois é só registrar na sua IA"),
    "terminal": ("Command Prompt", "Prompt de Comando"),
    "ask": ("Ask for the character in plain words", "Peça o personagem com suas palavras"),
    "ask_sub": ("Works in Claude Code, Claude Desktop, Codex, Antigravity...",
                "Funciona no Claude Code, Claude Desktop, Codex, Antigravity..."),
    "prompt": ("Make a blacksmith NPC: tan skin, dark brown hair, white shirt, "
               "overalls and a hammer. Export it to Godot, Unity and web.",
               "Crie um ferreiro NPC: pele morena, cabelo castanho escuro, camisa branca, "
               "macacão e um martelo. Exporte para Godot, Unity e web."),
    "placeholder": ("Ask anything...", "Pergunte qualquer coisa..."),
    "name": ("blacksmith", "ferreiro"),
    "done": ("Done! Your blacksmith is ready:", "Pronto! Seu ferreiro foi gerado:"),
    "done_anims": ("✓  62 animations, all complete (hammering included)",
                   "✓  62 animações, todas completas (com a martelada)"),
    "done_license": ("✓  Store-safe: every sprite allows CC0 or OGA-BY",
                     "✓  Pode ir para Steam/App Store: toda arte aceita CC0 ou OGA-BY"),
    "done_files": ("→  {n}.png · Godot .tres · Unity clips · web atlas · credits",
                   "→  {n}.png · Godot .tres · clipes Unity · atlas web · créditos"),
    "sheet": ("Get the full spritesheet", "Receba a spritesheet completa"),
    "sheet_sub": ("Every animation, 4 directions, ready for any engine",
                  "Todas as animações, 4 direções, pronta para qualquer engine"),
    "anims1": ("62 animations · walk, run, slash, thrust, spellcast,",
               "62 animações · walk, run, slash, thrust, spellcast,"),
    "engines": ("Drop it into your engine", "Coloque direto na sua engine"),
    "engines_sub": ("Exports are generated next to the PNG", "As exportações saem junto com o PNG"),
    "godot": ("SpriteFrames .tres - drop on an AnimatedSprite2D",
              "SpriteFrames .tres - é só pôr num AnimatedSprite2D"),
    "unity": ("sliced sprites + 62 clips + Animator Controller",
              "sprites fatiados + 62 clipes + Animator Controller"),
    "web": ("Phaser 3 / PixiJS atlas + a ready demo page", "atlas Phaser 3 / PixiJS + página de demo pronta"),
    "credits": ("Credits", "Créditos"),
    "credits_desc": ("authors and licenses of exactly the art used",
                     "autores e licenças exatamente das artes usadas"),
    "showcase": ("657 items · random characters · batches · license filter",
                 "657 itens · personagens aleatórios · lotes · filtro de licença"),
    "free": ("Free & open source (MIT) · PyPI · MCP Registry",
             "Grátis e código aberto (MIT) · PyPI · MCP Registry"),
    "sprites_by": ("Sprites: Liberated Pixel Cup contributors ({})",
                   "Sprites: colaboradores do Liberated Pixel Cup ({})"),
    "full_credits": ("full art credits: {}", "créditos completos das artes: {}"),
}


def T(key, **kw):
    s = TX[key][LANG == "pt"]
    return s.format(**kw) if kw else s


SYMS = "✓✔→"


def rich(d, xy, s, f, fill):
    """Draws text, taking the symbols the font lacks from Segoe UI Symbol. Returns the width."""
    x, y = xy
    sym = ImageFont.truetype(str(FONTS / "seguisym.ttf"), f.size)
    for ch in s:
        ff = sym if ch in SYMS else f
        d.text((x, y), ch, font=ff, fill=fill)
        x += ff.getlength(ch)
    return x - xy[0]


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------- sprites
CREDITS = {}


def remember_credits(items):
    for c in render._credits(items):
        CREDITS.setdefault(c.get("file", ""), c)


def walk_cells(items, body, direction=3):
    comp = render._compose(items, body, ["walk"])
    remember_credits(items)
    img = dict((a, i) for a, i, _ in comp["rows"])["walk"]
    return [img.crop((c * 64, direction * 64, (c + 1) * 64, (direction + 1) * 64)) for c in range(1, 9)]


def anim_frames(items, body, animation, direction=2):
    """Frames of one direction (down by default), transparent, 1x. Returns (frames, fps)."""
    old = server.PREVIEW_BG
    server.PREVIEW_BG = (0, 0, 0, 0)
    try:
        frames, fps, _ = server._preview_frames(items, body, animation)
    finally:
        server.PREVIEW_BG = old
    remember_credits(items)
    n = max(1, round(frames[0].width / frames[0].height))
    cw = frames[0].width // n
    d = direction if n == 4 else 0
    scale = cw // (128 if cw >= 256 else 64)
    out = []
    for fr in frames:
        cell = fr.crop((d * cw, 0, (d + 1) * cw, fr.height))
        out.append(cell.resize((cell.width // scale, cell.height // scale), Image.NEAREST))
    return out, fps


def px(img, k):
    return img.resize((img.width * k, img.height * k), Image.NEAREST)


BLACKSMITH = ms.themed_items(ms.THEMED[11][1])


def load_assets():
    a = {}
    old = server.PREVIEW_BG
    frames, fps, _ = server._preview_frames(BLACKSMITH, "male", "tool_hammer")
    remember_credits(BLACKSMITH)
    server.PREVIEW_BG = old
    a["hammer"] = ([f.convert("RGB") for f in frames], fps)
    grid = ["walk", "run", "slash", "thrust", "spellcast", "shoot", "jump", "1h_slash"]
    a["grid"] = [(name, *anim_frames(BLACKSMITH, "male", name)) for name in grid]
    r = server.generate_character(BLACKSMITH, "male", filename="promo_blacksmith.png")
    a["sheet"] = Image.open(r["file"]).convert("RGBA")
    a["hero_walk"] = [px(c, 3) for c in walk_cells(BLACKSMITH, "male", 2)]
    a["showcase"] = Image.open(DOCS / "showcase.png").convert("RGB")
    # the showcase characters too, for the credits file
    srng = random.Random(42)
    sp = [(b, ms.themed_items(p)) for b, p in ms.THEMED]
    n = 0
    while len(sp) < 48:
        sp.append(ms.random_hero(srng, n))
        n += 1
    for body, items in sp:
        if "error" not in render._compose(items, body, ["walk"]):
            remember_credits(items)
    return a


def write_credits(a):
    credits = sorted(CREDITS.values(), key=lambda c: c.get("file", ""))
    fams = {license_family(x) for c in credits for x in c.get("licenses", [])}
    ordered = [f for f in LICENSE_FAMILIES if f in fams] + sorted(fams - set(LICENSE_FAMILIES))
    a["licenses"] = ", ".join(ordered)
    render._write_credits(credits, str(DOCS / "media"))


# ---------------------------------------------------------------- drawing helpers
def canvas():
    return Image.new("RGB", (W, H), BG)


def rounded(d, box, r, fill, outline=None):
    d.rounded_rectangle(box, r, fill=fill, outline=outline, width=2 if outline else 0)


def text_c(d, xy, s, f, fill):
    d.text(xy, s, font=f, fill=fill, anchor="mm")


def caption(img, step, title, sub=None, t=1.0):
    d = ImageDraw.Draw(img)
    a = ease(t * 3)
    x = int(48 - 30 * (1 - a))
    rounded(d, (x, 34, x + 46, 80), 12, GOLD)
    text_c(d, (x + 23, 56), str(step), bold(28), BG)
    d.text((x + 64, 34), title, font=bold(34), fill=TEXT)
    if sub:
        d.text((x + 66, 80), sub, font=regular(19), fill=DIM)


def fade(img, t, dur, inn=0.35, out=0.35):
    k = min(1.0, t / inn if inn else 1, (dur - t) / out if out else 1)
    if k >= 1:
        return img
    return Image.blend(Image.new("RGB", img.size, (0, 0, 0)), img, max(0.0, k))


def checker(w, h, s=8):
    img = Image.new("RGB", (w, h), (46, 50, 62))
    d = ImageDraw.Draw(img)
    for y in range(0, h, s):
        for x in range((y // s % 2) * s, w, 2 * s):
            d.rectangle((x, y, x + s - 1, y + s - 1), fill=(38, 42, 52))
    return img


# ---------------------------------------------------------------- terminal
DOWNLOADS = [
    ("out", "Downloading cryptography (3.7MiB)", 0.07),
    ("out", "Downloading pydantic-core (1.9MiB)", 0.07),
    ("out", "Downloading numpy (12.0MiB)", 0.07),
    ("out", "Downloading pywin32 (6.6MiB)", 0.07),
    ("out", "Downloading pillow (6.9MiB)", 0.35),
    ("out", " Downloaded pydantic-core", 0.12),
    ("out", " Downloaded cryptography", 0.12),
    ("out", " Downloaded pillow", 0.12),
    ("out", " Downloaded pywin32", 0.2),
    ("out", " Downloaded numpy", 0.2),
    ("out", "Installed 32 packages in 346ms", 1.4),
]
TERM_PT = [
    ("cmd", "set LPC_LANG=pt"),
    ("wait", 0.2),
    ("out", "", 0),
    ("cmd", "uvx lpc-character-mcp --setup"),
    ("wait", 0.4),
    *DOWNLOADS,
    ("ok", "lpc-character-mcp pronto: 657 itens.", 0.1),
    ("out", "Definições em C:\\Users\\voce\\AppData\\Local\\lpc-character-mcp\\lpc\\sheet_definitions", 0.1),
    ("out", "Personagens serão salvos em C:\\Users\\voce\\lpc-characters", 0.8),
    ("out", "", 0),
    ("cmd", "claude mcp add lpc --scope user -e LPC_LANG=pt -- uvx lpc-character-mcp"),
    ("wait", 0.5),
    ("out", "Added stdio MCP server lpc with command: uvx lpc-character-mcp to user config", 0.1),
    ("out", "File modified: C:\\Users\\voce\\.claude.json", 0.8),
    ("out", "", 0),
    ("cmd", "claude mcp list"),
    ("wait", 0.3),
    ("out", "Checking MCP server health…", 0.9),
    ("out", "", 0),
    ("ok", "lpc: uvx lpc-character-mcp - ✔ Connected", 0.6),
    ("out", "", 0),
    ("cmd", ""),
]
TERM = [
    ("cmd", "uvx lpc-character-mcp --setup"),
    ("wait", 0.4),
    *DOWNLOADS,
    ("ok", "lpc-character-mcp ready: 657 items.", 0.1),
    ("out", "Definitions in C:\\Users\\you\\AppData\\Local\\lpc-character-mcp\\lpc\\sheet_definitions", 0.1),
    ("out", "Characters will be saved to C:\\Users\\you\\lpc-characters", 0.8),
    ("out", "", 0),
    ("cmd", "claude mcp add lpc --scope user -- uvx lpc-character-mcp"),
    ("wait", 0.5),
    ("out", "Added stdio MCP server lpc with command: uvx lpc-character-mcp to user config", 0.1),
    ("out", "File modified: C:\\Users\\you\\.claude.json", 0.8),
    ("out", "", 0),
    ("cmd", "claude mcp list"),
    ("wait", 0.3),
    ("out", "Checking MCP server health…", 0.9),
    ("out", "", 0),
    ("ok", "lpc: uvx lpc-character-mcp - ✔ Connected", 0.6),
    ("out", "", 0),
    ("cmd", ""),
]
CPS = 30  # typing speed


def term_timeline():
    """[(time, kind, text)] and the total duration."""
    t, events = 0.6, []
    for ev in (TERM_PT if LANG == "pt" else TERM):
        kind = ev[0]
        if kind == "wait":
            t += ev[1]
        elif kind == "cmd":
            events.append((t, "cmd", ev[1]))
            t += len(ev[1]) / CPS + 0.35
        else:
            events.append((t, kind, ev[1]))
            t += ev[2]
    return events, t + 1.6


def set_lang(lang):
    global LANG, PROMPT, TERM_EVENTS, TERM_DUR
    LANG = lang
    PROMPT = "C:\\Users\\voce>" if lang == "pt" else "C:\\Users\\you>"
    TERM_EVENTS, TERM_DUR = term_timeline()


set_lang("en")


def draw_terminal(img, box, t, size=19):
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    rounded(d, box, 12, (12, 12, 12), outline=(60, 64, 76))
    d.rectangle((x0 + 2, y0 + 2, x1 - 2, y0 + 36), fill=(32, 32, 32))
    d.text((x0 + 16, y0 + 8), T("terminal"), font=regular(16), fill=(200, 200, 200))
    for i, c in enumerate([(200, 200, 200)] * 3):
        cx = x1 - 30 - i * 44
        if i == 0:
            d.line((cx - 6, y0 + 13, cx + 6, y0 + 25), fill=c, width=1)
            d.line((cx - 6, y0 + 25, cx + 6, y0 + 13), fill=c, width=1)
        elif i == 1:
            d.rectangle((cx - 6, y0 + 13, cx + 6, y0 + 25), outline=c)
        else:
            d.line((cx - 6, y0 + 19, cx + 6, y0 + 19), fill=c)
    f = mono(size)
    lh = int(size * 1.45)
    lines = []
    cursor_line = None
    for et, kind, s in TERM_EVENTS:
        if t < et:
            break
        if kind == "cmd":
            n = int((t - et) * CPS)
            lines.append([(PROMPT, (204, 204, 204)), (s[:n], TEXT)])
            cursor_line = len(lines) - 1
        else:
            color = GREEN if kind == "ok" else (204, 204, 204)
            lines.append([(s, color)])
            cursor_line = None
    maxl = (y1 - y0 - 56) // lh
    lines = lines[-maxl:]
    if cursor_line is not None:
        cursor_line = len(lines) - 1
    y = y0 + 48
    for i, parts in enumerate(lines):
        x = x0 + 18
        for s, color in parts:
            x += rich(d, (x, y), s, f, color)
        if i == cursor_line and int(t * 2) % 2 == 0:
            d.rectangle((x + 1, y + 2, x + size * 0.6, y + lh - 4), fill=TEXT)
        y += lh


# ---------------------------------------------------------------- scenes
def scene_install(a, t, dur):
    img = canvas()
    caption(img, 4, T("install"), T("install_sub"), t)
    draw_terminal(img, (48, 122, W - 48, H - 36), t)
    return fade(img, t, dur)


def wrap(s, f, width):
    words, lines, cur = s.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if f.getlength(test) > width:
            lines.append(cur)
            cur = w
        else:
            cur = test
    return lines + [cur]


def pill(d, x, y, label, done, t):
    f = mono(17)
    w = int(f.getlength(label)) + 64
    rounded(d, (x, y, x + w, y + 36), 18, PANEL2)
    if done:
        rich(d, (x + 13, y + 5), "✓", bold(20), GREEN)
    else:
        ang = t * 360 * 1.5
        d.arc((x + 12, y + 9, x + 30, y + 27), ang, ang + 270, fill=GOLD, width=3)
    d.text((x + 42, y + 7), label, font=f, fill=TEXT)
    return w


def scene_chat(a, t, dur):
    img = canvas()
    caption(img, 1, T("ask"), T("ask_sub"), t)
    PROMPT_TEXT = T("prompt")
    d = ImageDraw.Draw(img)
    box = (48, 122, W - 48, H - 30)
    rounded(d, box, 16, PANEL)
    f = regular(22)
    typed_end = 0.15 + len(PROMPT_TEXT) / 45
    sent = t > typed_end + 0.3
    # input box
    ib = (box[0] + 20, box[3] - 74, box[2] - 20, box[3] - 18)
    rounded(d, ib, 14, PANEL2)
    if not sent:
        n = int(max(0.0, t - 0.15) * 45)
        s = PROMPT_TEXT[:n]
        lines = wrap(s, regular(19), ib[2] - ib[0] - 40) if s else [T("placeholder")]
        lines = lines[-2:]
        for i, ln in enumerate(lines):
            d.text((ib[0] + 18, ib[1] + 4 + i * 24), ln, font=regular(19), fill=TEXT if s else DIM)
    else:
        d.text((ib[0] + 18, ib[1] + 16), T("placeholder"), font=regular(19), fill=DIM)
    if not sent:
        return fade(img, t, dur, inn=0)
    ts = t - typed_end - 0.3
    y = box[1] + 20
    # user bubble (right)
    lines = wrap(PROMPT_TEXT, f, 800)
    bw = max(int(f.getlength(ln)) for ln in lines) + 36
    bx = box[2] - 24 - bw
    rounded(d, (bx, y, box[2] - 24, y + 22 + 30 * len(lines)), 16, (48, 70, 120))
    for i, ln in enumerate(lines):
        d.text((bx + 18, y + 8 + i * 30), ln, font=f, fill=TEXT)
    y += 40 + 30 * len(lines)
    # assistant
    x = box[0] + 28
    pw = 0
    if ts > 0.4:
        pw = pill(d, x, y, "lpc · preview_character", ts > 1.4, ts)
    if ts > 2.0:
        pill(d, x + pw + 12, y, "lpc · generate_character", ts > 3.0, ts)
    frames, fps = a["hammer"]
    iy = y + 48
    y2 = iy + 192 - 34
    if ts > 1.4:
        fr = frames[int((ts - 1.4) * fps) % len(frames)]
        fr = fr.resize((fr.width * 3 // 4, fr.height * 3 // 4), Image.NEAREST)
        img.paste(fr, (x, iy))
        d.rounded_rectangle((x, iy, x + fr.width, iy + fr.height), 6, outline=(60, 64, 76), width=2)
    lines = [
        (T("done"), TEXT),
        (T("done_anims"), GREEN),
        (T("done_license"), GREEN),
        (T("done_files", n=T("name")), BLUE),
    ]
    for i, (s, c) in enumerate(lines):
        if ts > 3.2 + i * 0.45:
            rich(d, (x + (0 if i == 0 else 4), y2 + 48 + i * 29), s, regular(21), c)
    return fade(img, t, dur, inn=0)


def scene_result(a, t, dur):
    img = canvas()
    caption(img, 2, T("sheet"), T("sheet_sub"), t)
    d = ImageDraw.Draw(img)
    # sheet panning
    pw, ph = 560, H - 160
    px0, py0 = 48, 128
    sheet = a["sheet"]
    view = checker(pw, ph)
    top = int(ease(t / (dur - 0.5)) * (sheet.height - ph))
    crop = sheet.crop((0, top, pw, top + ph))
    view.paste(crop, (0, 0), crop)
    img.paste(view, (px0, py0))
    d.rounded_rectangle((px0 - 2, py0 - 2, px0 + pw + 2, py0 + ph + 2), 8, outline=(60, 64, 76), width=2)
    d.text((px0, py0 + ph + 6), f"{T('name')}.png  ·  {sheet.width}×{sheet.height}", font=mono(16), fill=DIM)
    # animation grid
    gx, gy = 660, 150
    for k, (name, frames, fps) in enumerate(a["grid"]):
        cx, cy = gx + (k % 4) * 142, gy + (k // 4) * 200
        appear = ease((t - 0.2 - k * 0.12) / 0.4)
        if appear <= 0:
            continue
        rounded(d, (cx, cy, cx + 128, cy + 160), 10, PANEL)
        fr = frames[int(t * fps) % len(frames)]
        if fr.width > 64:  # oversized frame: keep the middle
            fr = fr.crop((32, 32, 96, 96))
        c = px(fr, 2)
        img.paste(c, (cx, cy + 2), c)
        text_c(d, (cx + 64, cy + 145), name, mono(16), TEXT)
    d.text((gx, gy + 410), T("anims1"),
           font=regular(20), fill=DIM)
    d.text((gx, gy + 438), "shoot, jump, hurt, sit, emote, climb, idle, tool_hammer...",
           font=regular(20), fill=DIM)
    return fade(img, t, dur)


def engines():
    return [
        ("Godot 4", T("godot"), (110, 160, 230)),
        ("Unity 6", T("unity"), (220, 220, 220)),
        ("Web", T("web"), (245, 170, 70)),
        (T("credits"), T("credits_desc"), GREEN),
    ]


FILES = [".png", ".tres", ".png.meta", "_unity_anims/", ".controller", ".json", "_demo.html",
         "_credits.txt", ".zip"]


def scene_engines(a, t, dur):
    img = canvas()
    caption(img, 3, T("engines"), T("engines_sub"), t)
    d = ImageDraw.Draw(img)
    rounded(d, (48, 128, 470, H - 40), 14, PANEL)
    d.text((70, 144), "~/lpc-characters", font=mono(18), fill=GOLD)
    for i, name in enumerate(FILES):
        if t > 0.3 + i * 0.18:
            d.text((80, 186 + i * 40), "▸ " + T("name") + name, font=mono(18), fill=TEXT)
    hero = a["hero_walk"][int(t * 10) % 8]
    img.paste(hero, (290, 470), hero)
    for i, (name, desc, color) in enumerate(engines()):
        k = ease((t - 0.6 - i * 0.35) / 0.4)
        if k <= 0:
            continue
        y = 140 + i * 128
        x = 510 + int(40 * (1 - k))
        rounded(d, (x, y, W - 48, y + 108), 14, PANEL)
        d.rectangle((x, y + 14, x + 5, y + 94), fill=color)
        d.text((x + 28, y + 16), name, font=bold(32), fill=color)
        d.text((x + 28, y + 62), desc, font=regular(22), fill=TEXT)
    return fade(img, t, dur)


def scene_showcase(a, t, dur):
    img = canvas()
    sc = a["showcase"]
    top = int(ease(t / dur) * (sc.height - (H - 90)))
    img.paste(sc.crop((0, top, sc.width, top + H - 90)), ((W - sc.width) // 2, 90))
    d = ImageDraw.Draw(img)
    text_c(d, (W // 2, 46), T("showcase"),
           bold(32), TEXT)
    return fade(img, t, dur)


def scene_end(a, t, dur):
    img = canvas()
    d = ImageDraw.Draw(img)
    text_c(d, (W // 2, 150), "LPC Character MCP", bold(64), TEXT)
    rounded(d, (W // 2 - 300, 220, W // 2 + 300, 290), 14, PANEL2)
    text_c(d, (W // 2, 255), "uvx lpc-character-mcp", mono(34), GOLD)
    text_c(d, (W // 2, 340), "github.com/kyuza1/lpc-character-mcp", regular(32), BLUE)
    text_c(d, (W // 2, 390), T("free"), regular(24), DIM)
    hero = a["hero_walk"][int(t * 10) % 8]
    img.paste(hero, (W // 2 - hero.width // 2, 420), hero)
    text_c(d, (W // 2, H - 60), T("sprites_by").format(a["licenses"]),
           regular(18), DIM)
    text_c(d, (W // 2, H - 34), T("full_credits").format("github.com/kyuza1/lpc-character-mcp/blob/main/docs/media_credits.txt"),
           regular(16), DIM)
    return fade(img, t, dur, out=0.6)


def scenes():
    return [
    (scene_chat, 11.0),
    (scene_result, 10.0),
    (scene_engines, 7.0),
    (scene_showcase, 5.0),
    (scene_install, TERM_DUR),
    (scene_end, 6.0),
    ]


def make_video(a, path):
    path.parent.mkdir(exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow",
           "-tune", "animation", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for fn, dur in scenes():
        for i in range(int(dur * FPS)):
            p.stdin.write(fn(a, i / FPS, dur).tobytes())
    p.stdin.close()
    p.wait()


def make_gif(path, gw=960, gh=520, fps=12):
    frames = []
    for i in range(int(TERM_DUR * fps)):
        img = Image.new("RGB", (gw, gh), BG)
        draw_terminal(img, (0, 0, gw - 1, gh - 1), i / fps, size=15)
        frames.append(img.quantize(16))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=int(1000 / fps), loop=0,
                   optimize=True)


def make_chat_gif(a, path, fps=12, until=14.0, width=880):
    """The chat scene (asking -> preview -> result) without the step caption."""
    shots = []
    for i in range(int(until * fps)):
        img = scene_chat(a, i / fps, 99).crop((40, 114, W - 40, H - 22))
        shots.append(img.resize((width, img.height * width // img.width), Image.LANCZOS))
    palette = shots[-1].quantize(96)
    frames = [s.quantize(palette=palette, dither=Image.Dither.NONE) for s in shots]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=int(1000 / fps), loop=0,
                   optimize=True)


if __name__ == "__main__":
    DOCS.mkdir(exist_ok=True)
    assets = None if "--gif" in sys.argv else load_assets()
    if assets:
        write_credits(assets)
    for lang, suffix in (("en", ""), ("pt", "_pt")):
        set_lang(lang)
        gif = DOCS / f"install{suffix}.gif"
        make_gif(gif)
        print(gif.name, gif.stat().st_size // 1024, "KB")
        if assets:
            chat = DOCS / f"chat{suffix}.gif"
            make_chat_gif(assets, chat)
            print(chat.name, chat.stat().st_size // 1024, "KB")
            video = OUT / f"promo{suffix}.mp4"
            make_video(assets, video)
            print(video.name, video.stat().st_size // 1024, "KB")
