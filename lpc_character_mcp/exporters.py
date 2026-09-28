"""Exporta a spritesheet gerada para engines: Godot, Unity e Web (Phaser/PixiJS).

Todas as funções recebem (path, img, index) — o PNG salvo, a imagem e o índice de
animações devolvido por generate_character — e salvam os arquivos ao lado do PNG.
"""
import hashlib
import json
import time
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
def godot_res_dir(folder):
    """Se `folder` está dentro de um projeto Godot (tem project.godot acima), devolve o
    caminho res:// dela; senão, None."""
    folder = Path(folder).resolve()
    for parent in [folder, *folder.parents]:
        if (parent / "project.godot").exists():
            rel = folder.relative_to(parent).as_posix()
            return "res://" + (rel + "/" if rel != "." else "")
    return None


def godot(path, img, index, res_dir=None):
    """SpriteFrames (.tres) para AnimatedSprite2D. Se o PNG já está dentro de um projeto
    Godot, usa o caminho res:// dele; senão, espera os arquivos em res://characters/."""
    path = Path(path)
    in_project = godot_res_dir(path.parent)
    res_dir = (res_dir or in_project or "res://characters/").rstrip("/") + "/"
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
    use = (f"Já está no projeto: use {res_dir}{out.name} em Sprite Frames de um AnimatedSprite2D"
           if in_project else
           f"Copie {path.name} e {out.name} para {res_dir} no projeto Godot 4 e use o .tres em "
           f"Sprite Frames de um AnimatedSprite2D")
    return {"file": str(out), "res_path": f"{res_dir}{out.name}", "animations": len(clips),
            "how_to_use": use + " (animações: walk_down, walk_up, idle_left...)."}


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
    sprites, table = [], []
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
        # guid fixo para o controlador conseguir apontar para o clipe
        (folder / f"{name}.anim.meta").write_text(
            _native_meta(_guid(f"lpc-clip:{path.name}:{name}"), 7400000), encoding="utf8")

    controller = _unity_controller(path, [c[0] for c in clips])
    return {"meta": f"{path}.meta", "anims_folder": str(folder), "clips": len(clips),
            "controller": str(controller),
            "how_to_use": f"Copie {path.name}, {path.name}.meta, {controller.name}(.meta) e a pasta "
                          f"{folder.name} para Assets/ no Unity (ou gere com output_dir dentro de "
                          f"Assets/). Coloque o {controller.name} no Animator de um objeto com "
                          f"SpriteRenderer e troque a animação com animator.Play(\"walk_left\")."}


def _native_meta(guid, main_id):
    return (f"fileFormatVersion: 2\nguid: {guid}\nNativeFormatImporter:\n  externalObjects: {{}}\n"
            f"  mainObjectFileID: {main_id}\n  userData: \n  assetBundleName: \n  assetBundleVariant: \n")


def _unity_controller(path, clip_names):
    """AnimatorController com um estado por clipe (sem transições): o jogo escolhe o estado
    com animator.Play("walk_down"). Começa em idle_down (ou no primeiro clipe)."""
    path = Path(path)
    default = "idle_down" if "idle_down" in clip_names else clip_names[0]
    ids = {n: _internal_id(f"lpc-state:{path.name}:{n}") for n in clip_names}
    sm_id = _internal_id(f"lpc-sm:{path.name}")
    states, children = [], []
    for i, name in enumerate(clip_names):
        clip_guid = _guid(f"lpc-clip:{path.name}:{name}")
        x, y = 300 + (i // 12) * 260, (i % 12) * 60
        children.append(f"  - serializedVersion: 1\n    m_State: {{fileID: {ids[name]}}}\n"
                        f"    m_Position: {{x: {x}, y: {y}, z: 0}}\n")
        states.append(f"""--- !u!1102 &{ids[name]}
AnimatorState:
  serializedVersion: 6
  m_ObjectHideFlags: 1
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  m_Name: {name}
  m_Speed: 1
  m_CycleOffset: 0
  m_Transitions: []
  m_StateMachineBehaviours: []
  m_Position: {{x: 50, y: 50, z: 0}}
  m_IKOnFeet: 0
  m_WriteDefaultValues: 1
  m_Mirror: 0
  m_SpeedParameterActive: 0
  m_MirrorParameterActive: 0
  m_CycleOffsetParameterActive: 0
  m_TimeParameterActive: 0
  m_Motion: {{fileID: 7400000, guid: {clip_guid}, type: 2}}
  m_Tag: 
  m_SpeedParameter: 
  m_MirrorParameter: 
  m_CycleOffsetParameter: 
  m_TimeParameter: 
""")
    text = f"""%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!91 &9100000
AnimatorController:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  m_Name: {path.stem}
  serializedVersion: 6
  m_AnimatorParameters: []
  m_AnimatorLayers:
  - serializedVersion: 5
    m_Name: Base Layer
    m_StateMachine: {{fileID: {sm_id}}}
    m_Mask: {{fileID: 0}}
    m_Motions: []
    m_Behaviours: []
    m_BlendingMode: 0
    m_SyncedLayerIndex: -1
    m_DefaultWeight: 0
    m_IKPass: 0
    m_SyncedLayerAffectsTiming: 0
    m_Controller: {{fileID: 9100000}}
  m_EvaluateTransitionsOnStart: 1
--- !u!1107 &{sm_id}
AnimatorStateMachine:
  serializedVersion: 7
  m_ObjectHideFlags: 1
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  m_Name: Base Layer
  m_ChildStates:
{"".join(children)}  m_ChildStateMachines: []
  m_AnyStateTransitions: []
  m_EntryTransitions: []
  m_StateMachineTransitions: {{}}
  m_StateMachineBehaviours: []
  m_AnyStatePosition: {{x: 50, y: 20, z: 0}}
  m_EntryPosition: {{x: 50, y: 120, z: 0}}
  m_ExitPosition: {{x: 800, y: 120, z: 0}}
  m_ParentStateMachinePosition: {{x: 800, y: 20, z: 0}}
  m_DefaultState: {{fileID: {ids[default]}}}
{"".join(states)}"""
    out = path.with_suffix(".controller")
    out.write_text(text, encoding="utf8")
    Path(f"{out}.meta").write_text(_native_meta(_guid(f"lpc-ctrl:{path.name}"), 9100000), encoding="utf8")
    return out


# ---------- Web (Phaser 3 / PixiJS) ----------
def web(path, img, index, missing=None):
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
                      "loop": {name: anim in LOOPING for name, anim, _, _ in clips},
                      # itens sem arte em cada animação (a demo avisa)
                      "missing": missing or {}}}
    atlas_file = path.with_suffix(".json")
    atlas_file.write_text(json.dumps(atlas, indent=1), encoding="utf8")
    html = path.parent / f"{path.stem}_demo.html"
    page = (Path(__file__).with_name("demo_template.html").read_text(encoding="utf8")
            .replace("__TITLE__", path.stem).replace("__ATLAS_FILE__", atlas_file.name)
            .replace("__IMAGE__", path.name).replace("__VERSION__", str(int(time.time())))
            .replace("__ATLAS__", json.dumps(atlas)))
    html.write_text(page, encoding="utf8")
    return {"atlas": str(atlas_file), "demo": str(html),
            "how_to_use": "Phaser 3: this.load.atlas('char', '" + path.name + "', '" + atlas_file.name
                          + "') e crie as animações a partir de atlas.animations. PixiJS: "
                          "Assets.load('" + atlas_file.name + "') e use sheet.animations['walk_down'] "
                          "num AnimatedSprite. Abra " + html.name + " no navegador para ver."}
