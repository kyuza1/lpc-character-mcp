"""Exporta a spritesheet gerada para engines: Godot, Unity e Web (Phaser/PixiJS).

Todas as funções recebem (path, img, index) — o PNG salvo, a imagem e o índice de
animações devolvido por generate_character — e salvam os arquivos ao lado do PNG.
"""
import hashlib
import json
from pathlib import Path

# animações que repetem em loop (as outras tocam uma vez)
LOOPING = {"walk", "run", "idle", "combat_idle", "climb", "walk_128", "spellcast"}
# quadros por segundo de cada animação (padrão: 10)
FPS = {"idle": 3, "combat_idle": 3, "walk": 10, "run": 12, "sit": 3, "emote": 6, "hurt": 8,
       "climb": 8, "jump": 10, "shoot": 14, "thrust": 12, "spellcast": 10}


def frames_of(img, index):
    """[(nome_clipe, animação, direção, [(x, y, tamanho)...])] sem quadros vazios no fim."""
    clips = []
    for anim, info in index.items():
        f = info["frame"]
        for r, direction in enumerate(info["directions"]):
            y = info["y"] + r * f
            cells = [(c * f, y, f) for c in range(info["columns"])]
            while cells and not img.crop((cells[-1][0], y, cells[-1][0] + f, y + f)).getbbox():
                cells.pop()
            if cells:
                name = anim if len(info["directions"]) == 1 else f"{anim}_{direction}"
                clips.append((name, anim, direction, cells))
    return clips


def _fps(anim):
    return FPS.get(anim, FPS.get(anim.split("_")[0], 10))


# ---------- Godot 4 ----------
def godot(path, img, index, res_dir="res://characters/"):
    """SpriteFrames (.tres) para AnimatedSprite2D. Coloque o .png e o .tres em `res_dir`."""
    path = Path(path)
    res_dir = res_dir.rstrip("/") + "/"
    clips = frames_of(img, index)
    subs, anims, n = [], [], 0
    for name, anim, _, cells in clips:
        frames = []
        for x, y, f in cells:
            n += 1
            subs.append(f'[sub_resource type="AtlasTexture" id="AtlasTexture_{n}"]\n'
                        f'atlas = ExtResource("1_tex")\nregion = Rect2({x}, {y}, {f}, {f})\n')
            frames.append(f'{{\n"duration": 1.0,\n"texture": SubResource("AtlasTexture_{n}")\n}}')
        loop = "true" if anim in LOOPING else "false"
        anims.append(f'{{\n"frames": [{", ".join(frames)}],\n"loop": {loop},\n'
                     f'"name": &"{name}",\n"speed": {float(_fps(anim))}\n}}')
    text = (f'[gd_resource type="SpriteFrames" load_steps={n + 2} format=3]\n\n'
            f'[ext_resource type="Texture2D" path="{res_dir}{path.name}" id="1_tex"]\n\n'
            + "\n".join(subs)
            + f'\n[resource]\nanimations = [{", ".join(anims)}]\n')
    out = path.with_suffix(".tres")
    out.write_text(text, encoding="utf8")
    return {"file": str(out), "animations": len(clips),
            "how_to_use": f"Copie {path.name} e {out.name} para {res_dir} no projeto Godot 4 e use "
                          f"o .tres em Sprite Frames de um AnimatedSprite2D "
                          f"(animações: walk_down, walk_up, idle_left...)."}


# ---------- Unity ----------
def _guid(seed):
    return hashlib.md5(seed.encode()).hexdigest()


def _internal_id(seed):
    return int(hashlib.md5(seed.encode()).hexdigest()[:15], 16)  # int64 positivo


def unity(path, img, index, pixels_per_unit=64):
    """PNG .meta com os sprites já fatiados (Sprite Mode: Multiple, Point filter, sem compressão)
    e um clipe .anim por animação/direção. Copie tudo para Assets/ no Unity."""
    path = Path(path)
    tex_guid = _guid(f"lpc-texture:{path.name}")
    clips = frames_of(img, index)
    height = img.height
    sprites, table, clip_files = [], [], []
    for name, anim, _, cells in clips:
        for i, (x, y, f) in enumerate(cells):
            sname = f"{name}_{i}"
            iid = _internal_id(f"{path.name}:{sname}")
            sprites.append(
                f"    - serializedVersion: 2\n"
                f"      name: {sname}\n"
                f"      rect:\n        serializedVersion: 2\n"
                f"        x: {x}\n        y: {height - y - f}\n        width: {f}\n        height: {f}\n"
                f"      alignment: 9\n      pivot: {{x: 0.5, y: {0.16 * 64 / f:.4f}}}\n"
                f"      border: {{x: 0, y: 0, z: 0, w: 0}}\n"
                f"      outline: []\n      physicsShape: []\n      tessellationDetail: -1\n"
                f"      bones: []\n      spriteID: {_guid(f'{path.name}:{sname}:id')}\n"
                f"      internalID: {iid}\n      vertices: []\n      indices: \n      edges: []\n"
                f"      weights: []\n")
            table.append(f"      {sname}: {iid}\n")
    meta = f"""fileFormatVersion: 2
guid: {tex_guid}
TextureImporter:
  internalIDToNameTable: []
  externalObjects: {{}}
  serializedVersion: 13
  mipmaps:
    mipMapMode: 0
    enableMipMap: 0
    sRGBTexture: 1
    linearTexture: 0
    fadeOut: 0
    borderMipMap: 0
    mipMapsPreserveCoverage: 0
    alphaTestReferenceValue: 0.5
    mipMapFadeDistanceStart: 1
    mipMapFadeDistanceEnd: 3
  bumpmap:
    convertToNormalMap: 0
    externalNormalMap: 0
    heightScale: 0.25
    normalMapFilter: 0
  isReadable: 0
  streamingMipmaps: 0
  streamingMipmapsPriority: 0
  grayScaleToAlpha: 0
  generateCubemap: 6
  cubemapConvolution: 0
  seamlessCubemap: 0
  textureFormat: 1
  maxTextureSize: 8192
  textureSettings:
    serializedVersion: 2
    filterMode: 0
    aniso: 1
    mipBias: 0
    wrapU: 1
    wrapV: 1
    wrapW: 1
  nPOTScale: 0
  lightmap: 0
  compressionQuality: 50
  spriteMode: 2
  spriteExtrude: 1
  spriteMeshType: 0
  alignment: 0
  spritePivot: {{x: 0.5, y: 0.5}}
  spritePixelsToUnits: {pixels_per_unit}
  spriteBorder: {{x: 0, y: 0, z: 0, w: 0}}
  spriteGenerateFallbackPhysicsShape: 0
  alphaUsage: 1
  alphaIsTransparency: 1
  spriteTessellationDetail: -1
  textureType: 8
  textureShape: 1
  singleChannelComponent: 0
  flipbookRows: 1
  flipbookColumns: 1
  maxTextureSizeSet: 0
  compressionQualitySet: 0
  textureFormatSet: 0
  ignorePngGamma: 0
  applyGammaDecoding: 0
  swizzle: 50462976
  cookieLightType: 0
  platformSettings:
  - serializedVersion: 3
    buildTarget: DefaultTexturePlatform
    maxTextureSize: 8192
    resizeAlgorithm: 0
    textureFormat: -1
    textureCompression: 0
    compressionQuality: 50
    crunchedCompression: 0
    allowsAlphaSplitting: 0
    overridden: 0
    ignorePlatformSupport: 0
    androidETC2FallbackOverride: 0
    forceMaximumCompressionQuality_BC6H_BC7: 0
  spriteSheet:
    serializedVersion: 2
    sprites:
{"".join(sprites)}    outline: []
    physicsShape: []
    bones: []
    spriteID: {_guid(f"{path.name}:sheet")}
    internalID: 0
    vertices: []
    indices:
    edges: []
    weights: []
    secondaryTextures: []
    nameFileIdTable:
{"".join(table)}  mipmapLimitGroupName:
  pSDRemoveMatte: 0
  userData:
  assetBundleName:
  assetBundleVariant:
"""
    Path(f"{path}.meta").write_text(meta, encoding="utf8")

    folder = path.parent / f"{path.stem}_unity_anims"
    folder.mkdir(exist_ok=True)
    for name, anim, _, cells in clips:
        fps = _fps(anim)
        keys = "".join(
            f"    - time: {i / fps:.6f}\n      value: {{fileID: {_internal_id(f'{path.name}:{name}_{i}')}, "
            f"guid: {tex_guid}, type: 3}}\n" for i in range(len(cells)))
        refs = "".join(
            f"    - {{fileID: {_internal_id(f'{path.name}:{name}_{i}')}, guid: {tex_guid}, type: 3}}\n"
            for i in range(len(cells)))
        stop = len(cells) / fps
        clip = f"""%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!74 &7400000
AnimationClip:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  m_Name: {name}
  serializedVersion: 8
  m_Legacy: 0
  m_Compressed: 0
  m_UseHighQualityCurve: 1
  m_RotationCurves: []
  m_CompressedRotationCurves: []
  m_EulerCurves: []
  m_PositionCurves: []
  m_ScaleCurves: []
  m_FloatCurves: []
  m_PPtrCurves:
  - serializedVersion: 2
    curve:
{keys}    attribute: m_Sprite
    path:
    classID: 212
    script: {{fileID: 0}}
    flags: 2
  m_SampleRate: {fps}
  m_WrapMode: 0
  m_Bounds:
    m_Center: {{x: 0, y: 0, z: 0}}
    m_Extent: {{x: 0, y: 0, z: 0}}
  m_ClipBindingConstant:
    genericBindings:
    - serializedVersion: 2
      path: 0
      attribute: 0
      script: {{fileID: 0}}
      typeID: 212
      customType: 23
      isPPtrCurve: 1
      isIntCurve: 0
      isSerializeReferenceCurve: 0
      metaData: 0
    pptrCurveMapping:
{refs}  m_AnimationClipSettings:
    serializedVersion: 2
    m_AdditiveReferencePoseClip: {{fileID: 0}}
    m_AdditiveReferencePoseTime: 0
    m_StartTime: 0
    m_StopTime: {stop:.6f}
    m_OrientationOffsetY: 0
    m_Level: 0
    m_CycleOffset: 0
    m_HasAdditiveReferencePose: 0
    m_LoopTime: {1 if anim in LOOPING else 0}
    m_LoopBlend: 0
    m_LoopBlendOrientation: 0
    m_LoopBlendPositionY: 0
    m_LoopBlendPositionXZ: 0
    m_KeepOriginalOrientation: 0
    m_KeepOriginalPositionY: 1
    m_KeepOriginalPositionXZ: 0
    m_HeightFromFeet: 0
    m_Mirror: 0
  m_EditorCurves: []
  m_EulerEditorCurves: []
  m_HasGenericRootTransform: 0
  m_HasMotionFloatCurves: 0
  m_Events: []
"""
        (folder / f"{name}.anim").write_text(clip, encoding="utf8")
    return {"meta": f"{path}.meta", "anims_folder": str(folder), "clips": len(clips),
            "how_to_use": f"Copie {path.name}, {path.name}.meta e a pasta {folder.name} para "
                          f"Assets/ no Unity. Os sprites já vêm fatiados (walk_down_0...) e cada "
                          f".anim pode ir direto num Animator de um SpriteRenderer."}


# ---------- Web (Phaser 3 / PixiJS) ----------
def web(path, img, index):
    """Atlas JSON (formato TexturePacker "hash", lido por Phaser e PixiJS) com as animações,
    mais uma página HTML de demonstração que toca o personagem (setas/WASD para andar)."""
    path = Path(path)
    clips = frames_of(img, index)
    frames, animations = {}, {}
    for name, anim, _, cells in clips:
        keys = []
        for i, (x, y, f) in enumerate(cells):
            key = f"{name}_{i}"
            frames[key] = {"frame": {"x": x, "y": y, "w": f, "h": f}, "rotated": False,
                           "trimmed": False, "spriteSourceSize": {"x": 0, "y": 0, "w": f, "h": f},
                           "sourceSize": {"w": f, "h": f}, "anchor": {"x": 0.5, "y": 0.84}}
            keys.append(key)
        animations[name] = keys
    atlas = {"frames": frames, "animations": animations,
             "meta": {"app": "lpc-character-mcp", "version": "1.0", "image": path.name,
                      "format": "RGBA8888", "size": {"w": img.width, "h": img.height}, "scale": "1",
                      "fps": {name: _fps(anim) for name, anim, _, _ in clips},
                      "loop": {name: anim in LOOPING for name, anim, _, _ in clips}}}
    atlas_file = path.with_suffix(".json")
    atlas_file.write_text(json.dumps(atlas, indent=1), encoding="utf8")
    html = path.parent / f"{path.stem}_demo.html"
    html.write_text(DEMO_HTML.replace("__IMAGE__", path.name)
                    .replace("__ATLAS__", json.dumps(atlas)), encoding="utf8")
    return {"atlas": str(atlas_file), "demo": str(html),
            "how_to_use": "Phaser 3: this.load.atlas('char', '" + path.name + "', '" + atlas_file.name
                          + "') e crie as animações a partir de atlas.animations. PixiJS: "
                          "Assets.load('" + atlas_file.name + "') e use sheet.animations['walk_down'] "
                          "num AnimatedSprite. Abra " + html.name + " no navegador para ver."}


DEMO_HTML = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Personagem LPC</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body{margin:0;font:14px system-ui,sans-serif;background:#1d2330;color:#e8ecf3;display:flex;
       flex-direction:column;align-items:center;gap:12px;padding:16px}
  canvas{image-rendering:pixelated;background:#2b3345;border-radius:8px;max-width:100%}
  select{font:inherit;padding:4px 8px}
  p{margin:0;opacity:.75}
</style></head><body>
<canvas id="c" width="384" height="384"></canvas>
<label>Animação <select id="anim"></select></label>
<p>Setas ou WASD para andar · Shift para correr · Espaço para atacar</p>
<script>
const atlas = __ATLAS__;
const img = new Image(); img.src = "__IMAGE__";
const cv = document.getElementById("c"), ctx = cv.getContext("2d"), sel = document.getElementById("anim");
ctx.imageSmoothingEnabled = false;
for (const n of Object.keys(atlas.animations)) sel.add(new Option(n, n));
let clip = atlas.animations.walk_down ? "walk_down" : Object.keys(atlas.animations)[0];
sel.value = clip; sel.onchange = () => { clip = sel.value; frame = 0; manual = true; };
let frame = 0, last = 0, dir = "down", manual = false, x = 0, y = 0;
const keys = new Set();
addEventListener("keydown", e => { keys.add(e.key.toLowerCase()); manual = false; });
addEventListener("keyup", e => keys.delete(e.key.toLowerCase()));
const has = n => atlas.animations[n];
function pick() {
  if (manual) return clip;
  const k = s => s.some(v => keys.has(v));
  let moving = true;
  if (k(["arrowup","w"])) dir = "up"; else if (k(["arrowdown","s"])) dir = "down";
  else if (k(["arrowleft","a"])) dir = "left"; else if (k(["arrowright","d"])) dir = "right";
  else moving = false;
  // ataque: prefere a animação especial da arma/ferramenta (martelo, espada grande...)
  const attack = ["tool_hammer","tool_axe","tool_rod","tool_whip","whip_oversize","slash_oversize",
                  "slash_128","thrust_oversize","thrust_128","slash","thrust","shoot","spellcast"]
    .map(a => a + "_" + dir).find(has);
  if (keys.has(" ") && attack) return attack;
  if (moving) {
    const run = "run_" + dir, walk = has("walk_128_" + dir) ? "walk_128_" + dir : "walk_" + dir;
    return keys.has("shift") && has(run) ? run : walk;
  }
  return has("idle_" + dir) ? "idle_" + dir : "walk_" + dir;
}
function loop(t) {
  const want = pick();
  if (want !== clip && has(want)) { clip = want; frame = 0; sel.value = clip; }
  const frames = atlas.animations[clip], fps = atlas.meta.fps[clip] || 10;
  if (t - last > 1000 / fps) {
    last = t; frame++;
    if (frame >= frames.length) frame = atlas.meta.loop[clip] ? 0 : frames.length - 1;
  }
  const f = atlas.frames[frames[frame]].frame;
  ctx.clearRect(0, 0, cv.width, cv.height);
  const s = f.w > 64 ? 2 : 4;
  ctx.drawImage(img, f.x, f.y, f.w, f.h, (cv.width - f.w * s) / 2, (cv.height - f.h * s) / 2, f.w * s, f.h * s);
  requestAnimationFrame(loop);
}
img.onload = () => requestAnimationFrame(loop);
</script></body></html>
"""
