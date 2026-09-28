"""Testes do MCP. Rode com: python -m pytest -q
Na primeira vez baixam as definições e alguns PNGs do GitHub (precisa de internet)."""
import asyncio

import pytest
from PIL import Image

from lpc_character_mcp import server as s

ELFA = [
    {"id": "body/body", "color": "light"},
    {"id": "head/heads/human/heads_human_female", "color": "light"},
    {"id": "head/ears/head_ears_elven", "color": "light"},
    {"id": "hair/long/hair_long_straight", "color": "platinum"},
    {"id": "torso/shirts/torso_clothes_tunic", "color": "forest"},
    {"id": "legs/pants/legs_cuffed", "color": "brown"},
    {"id": "feet/boots/feet_boots_basic", "color": "brown"},
    {"id": "weapons/ranged/bow/weapon_ranged_bow_normal"},
]


@pytest.fixture(autouse=True)
def output_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(s, "OUT", tmp_path)


def test_catalogo_carregado():
    assert len(s.ITEMS) > 300
    assert "body/body" in s.ITEMS
    cats = s.list_categories()
    assert any(c.startswith("hair") for c in cats)


def test_busca_por_nome_e_categoria():
    ids = [x["id"] for x in s.search_items("elven")]
    assert "head/ears/head_ears_elven" in ids
    assert all(x["id"].startswith("hair") for x in s.search_items(category="hair", limit=20))
    assert len(s.search_items(limit=5)) == 5


def test_get_item_cores_e_variantes():
    hair = s.get_item("hair/short/hair_plain")
    assert "blonde" in hair["colors"] and hair["default_color"] == "orange"
    tunic = s.get_item("torso/shirts/torso_clothes_tunic")
    assert "forest" in tunic["variants"] and tunic["body_types"] == ["female"]


def test_recolor_troca_cor_do_cabelo():
    item = [{"id": "hair/short/hair_plain"}]
    base = Image.open(s.generate_character(item, animations=["walk"], filename="a.png")["file"])
    loiro = Image.open(s.generate_character([{**item[0], "color": "blonde"}],
                                            animations=["walk"], filename="b.png")["file"])
    assert base.size == loiro.size
    assert base.tobytes() != loiro.tobytes()


def test_color_escolhe_variante():
    d = s.ITEMS["torso/shirts/torso_clothes_tunic"]
    layer = d["layer_1"]
    verde = s._layer_image(d, layer, "female", "walk", None, ["forest"])
    vermelha = s._layer_image(d, layer, "female", "walk", None, ["red"])
    assert verde.tobytes() != vermelha.tobytes()


def test_gera_elfa_completa():
    r = s.generate_character(ELFA, body_type="female",
                             animations=["walk", "idle", "shoot"], filename="elfa.png",
                             layout="compact")
    img = Image.open(r["file"])
    assert img.size == tuple(r["size"])
    assert {"walk", "idle", "shoot"} <= set(r["animations"])
    # o arco anda numa animação especial de 128px
    assert r["animations"]["walk_128"]["frame"] == 128
    assert img.height == sum(a["height"] for a in r["animations"].values())
    # sem arte no repositório: túnica e arco em "idle" — deve ser avisado
    assert r["missing"] == {"torso/shirts/torso_clothes_tunic": ["idle"],
                            "weapons/ranged/bow/weapon_ranged_bow_normal": ["idle"]}


def test_masculino_avisa_item_so_feminino():
    r = s.generate_character([{"id": "body/body"}, {"id": "torso/shirts/torso_clothes_tunic"}],
                             animations=["walk"], filename="m.png")
    assert "torso/shirts/torso_clothes_tunic" in r["missing"]


def test_item_desconhecido():
    assert "error" in s.generate_character([{"id": "nao/existe"}])


def test_ferramentas_registradas_no_mcp():
    tools = asyncio.run(s.mcp.list_tools())
    nomes = {t.name for t in tools}
    assert {"list_categories", "search_items", "get_item", "generate_character"} <= nomes


FERREIRO = [
    {"id": "body/body", "color": "bronze"},
    {"id": "head/heads/human/heads_human_male"},
    {"id": "torso/aprons/torso_aprons_apron", "color": "leather"},
    {"id": "tools/tool_hammer"},
]


def test_martelo_gera_animacao_especial():
    r = s.generate_character(FERREIRO, animations=["slash"], filename="f.png")
    anim = r["animations"]["tool_hammer"]
    assert anim["frame"] == 128 and anim["height"] == 4 * 128
    assert "tools/tool_hammer" not in r.get("missing", {})


def test_espada_aparece_no_golpe():
    r = s.generate_character([{"id": "body/body"}, {"id": "weapons/sword/weapon_sword_arming"}],
                             animations=["slash"], filename="e.png")
    assert "slash_128" in r["animations"]
    img = Image.open(r["file"])
    a = r["animations"]["slash_128"]
    area = img.crop((0, a["y"], img.width, a["y"] + a["height"]))
    assert area.getbbox() is not None


def test_cabeca_herda_cor_do_corpo():
    sem = s.generate_character(FERREIRO[:2], animations=["walk"], filename="h1.png")
    com = s.generate_character([FERREIRO[0], {**FERREIRO[1], "color": "bronze"}],
                               animations=["walk"], filename="h2.png")
    assert Image.open(sem["file"]).tobytes() == Image.open(com["file"]).tobytes()


def test_item_com_varias_cores():
    info = s.get_item("tools/tool_hammer")
    assert len(info["color_parts"]) == 2
    padrao = s.generate_character([{"id": "tools/tool_hammer"}], animations=["walk"], filename="c1.png")
    cabo = s.generate_character([{"id": "tools/tool_hammer", "color": [None, "red"]}],
                                animations=["walk"], filename="c2.png")
    assert Image.open(padrao["file"]).tobytes() != Image.open(cabo["file"]).tobytes()


def test_animacoes_especiais_lidas_do_repositorio():
    anims = s._custom_animations()
    assert anims["tool_hammer"]["single"] and anims["tool_hammer"]["frameSize"] == 128
    assert len(anims["slash_128"]["frames"]) == 4
    assert anims["slash_128"]["frames"][0][0] == "slash-n,0"


def test_layout_padrao_igual_ao_site():
    r = s.generate_character(FERREIRO, animations=["walk", "slash"], filename="p.png")
    assert r["layout"] == "standard"
    a = r["animations"]
    assert a["walk"]["y"] == 8 * 64 and a["slash"]["y"] == 12 * 64
    assert a["tool_hammer"]["y"] == s.SHEET_HEIGHT
    assert r["size"] == [9 * 128, s.SHEET_HEIGHT + 4 * 128]


def test_layout_padrao_sem_especiais_tem_tamanho_do_site():
    r = s.generate_character(FERREIRO[:2], filename="p2.png")
    assert r["size"] == [s.SHEET_WIDTH, s.SHEET_HEIGHT]


def test_layout_invalido():
    assert "error" in s.generate_character(FERREIRO, layout="xyz")


def test_split_salva_animacoes_separadas(tmp_path):
    r = s.generate_character(FERREIRO, animations=["walk", "slash"], filename="sp.png", split=True)
    nomes = {p.name for p in (tmp_path / "sp_anims").iterdir()}
    assert nomes == {"walk.png", "slash.png", "tool_hammer.png"}
    assert Image.open(tmp_path / "sp_anims" / "tool_hammer.png").size == (9 * 128, 4 * 128)


def test_creditos_so_das_artes_usadas(tmp_path):
    r = s.generate_character(FERREIRO, animations=["walk"], filename="cr.png")
    c = r["credits"]
    txt = (tmp_path / "cr_credits.txt").read_text(encoding="utf8")
    assert "body/bodies/male" in txt and "tools/hammer" in txt
    assert "Stephen Challener (Redshrike)" in c["authors"]
    assert "CC-BY-SA 3.0" in c["licenses"]
    assert (tmp_path / "cr_credits.csv").read_text(encoding="utf8").startswith("file,notes,authors")
    # item não usado não entra
    assert "hair/" not in txt


URL = ("https://liberatedpixelcup.github.io/Universal-LPC-Spritesheet-Character-Generator/"
       "#sex=male&body=Body_Color_light&head=Human_Male_light&expression=Neutral_light")


def test_le_link_do_site():
    r = s.from_site_url(URL)
    assert r["body_type"] == "male"
    assert r["items"] == [{"id": "body/body", "color": "light"},
                          {"id": "head/heads/human/heads_human_male", "color": "light"},
                          {"id": "head/faces/face_neutral", "color": "light"}]
    assert "unresolved" not in r


def test_link_ida_e_volta_com_variante_e_varias_cores():
    items = [{"id": "body/body", "color": "bronze"},
             {"id": "hair/short/hair_plain", "color": "dark_brown"},
             {"id": "torso/aprons/torso_aprons_apron", "variant": "leather"},
             {"id": "tools/tool_hammer", "color": ["gold", "walnut"]}]
    url = s.to_site_url(items, "female")
    assert "apron=Apron_leather" in url and "handle=Handle_walnut" in url
    r = s.from_site_url(url)
    assert r["body_type"] == "female" and r["items"] == items


def test_link_com_parametro_desconhecido():
    r = s.from_site_url(URL + "&foo=Bar_baz")
    assert r["unresolved"] == {"foo": "Bar_baz"}


def test_personagem_aleatorio_repetivel():
    a = s.random_character("female", seed=42)
    b = s.random_character("female", seed=42)
    assert a == b
    ids = [i["id"] for i in a["items"]]
    assert ids[0] == "body/body" and any(i.startswith("head/heads/human/") for i in ids)
    assert any(i.startswith("torso/") for i in ids) and any(i.startswith("legs/") for i in ids)
    assert all(s._supports(i, "female") for i in ids[1:])
    assert a["url"].startswith(s.SITE)


def test_aleatorio_com_item_fixo():
    r = s.random_character("male", seed=1, fixed_items=[{"id": "tools/tool_hammer"}])
    assert r["items"][-1] == {"id": "tools/tool_hammer"}


def test_gera_lote(tmp_path):
    r = s.generate_batch(3, seed=5, prefix="vila", animations=["walk"], layout="compact")
    assert r["count"] == 3
    for n, c in enumerate(r["characters"], 1):
        assert "error" not in c
        assert (tmp_path / f"vila_{n:02d}.png").exists()
        assert (tmp_path / f"vila_{n:02d}_credits.txt").exists()


def test_previa_devolve_imagem_pelo_mcp():
    res = asyncio.run(s.mcp.call_tool("preview_character", {"items": FERREIRO}))
    tipos = [c.type for c in res.content]
    assert "image" in tipos and "text" in tipos


def test_previa_de_animacao_especial():
    img_data = s.preview_character(FERREIRO, animation="tool_hammer")[0].data
    import io
    img = Image.open(io.BytesIO(img_data))
    assert img.size == (4 * 128 * 2, 128 * 2)


def test_previa_animacao_invalida():
    assert "desconhecida" in s.preview_character(FERREIRO, animation="xyz")


def test_animacoes_reais_de_cada_item():
    tunic = s.get_item("torso/shirts/torso_clothes_tunic")["animations"]
    assert "walk" in tunic["female"] and "idle" not in tunic["female"]
    assert "idle" in s.get_item("body/body")["animations"]["male"]


def test_busca_com_filtros():
    r = s.search_items("apron", body_type="male", animation="idle")
    ids = [x["id"] for x in r]
    assert "torso/aprons/torso_aprons_apron" not in ids
    assert "torso/aprons/torso_aprons_overalls" in ids
    assert [x["id"] for x in s.search_items("leather armour")] == ["torso/armour/torso_armour_leather"]
    assert all(x["type"] == "hair" for x in s.search_items(type_name="hair", limit=10))
    assert all("female" in s.get_item(x["id"])["body_types"]
               for x in s.search_items(category="torso", body_type="female", limit=10))


def test_todas_as_ferramentas_registradas():
    nomes = {t.name for t in asyncio.run(s.mcp.list_tools())}
    assert nomes == {"list_categories", "search_items", "get_item", "generate_character",
                     "preview_character", "random_character", "generate_batch",
                     "from_site_url", "to_site_url", "update_definitions"}


# ---------- ajustes de uso ----------
def test_mascara_rosa_e_apagada():
    r = s.generate_character([{"id": "body/body"}, {"id": "body/prostheses/prosthesis_peg_leg"}],
                             animations=["walk"], layout="compact", filename="peg.png")
    arr = __import__("numpy").array(Image.open(r["file"]))
    pink = (arr[..., 0] == 255) & (arr[..., 1] == 44) & (arr[..., 2] == 230) & (arr[..., 3] > 0)
    assert not pink.any()
    sem = Image.open(s.generate_character([{"id": "body/body"}], animations=["walk"],
                                          layout="compact", filename="nopeg.png")["file"])
    assert Image.open(r["file"]).tobytes() != sem.tobytes()


def test_item_repetido_do_mesmo_tipo_substitui():
    r = s.generate_character([{"id": "body/body"}, {"id": "hair/short/hair_plain"},
                              {"id": "hair/long/hair_long"}], animations=["walk"], filename="dup.png")
    assert r["warnings"] == ["hair/long/hair_long substituiu hair/short/hair_plain (mesmo tipo: hair)"]


def test_aviso_curto_de_item_faltando():
    r = s.generate_character(FERREIRO, filename="curto.png")
    assert r["missing"]["tools/tool_hammer"] == {"only_in": ["walk", "slash"]}


def test_downloads_em_paralelo(monkeypatch):
    chamadas = []
    monkeypatch.setattr(s, "_prefetch", lambda rels: chamadas.append(len(rels)))
    s.generate_character(FERREIRO, animations=["walk", "slash"], filename="par.png")
    assert chamadas and chamadas[0] > 4


def test_body_type_invalido():
    assert "error" in s.generate_character(FERREIRO, body_type="robot")


# ---------- divisão em partes ----------
def test_split_por_quadro_e_por_item(tmp_path):
    r = s.generate_character(FERREIRO, animations=["walk"], filename="sp2.png", split=["frame", "item"])
    walk = sorted(p.name for p in (tmp_path / "sp2_frames" / "walk").iterdir())
    assert walk[0] == "down_00.png" and len(walk) == 36
    itens = {p.name for p in (tmp_path / "sp2_items").iterdir()}
    assert "tools__tool_hammer.png" in itens and len(itens) == 4
    # a folha de cada item tem o mesmo tamanho da folha completa
    assert Image.open(tmp_path / "sp2_items" / "body__body.png").size == tuple(r["size"])


def test_split_invalido():
    assert "error" in s.generate_character(FERREIRO, split="xyz")


# ---------- exportação ----------
def test_exporta_godot(tmp_path):
    r = s.generate_character(FERREIRO, animations=["walk", "slash"], filename="g.png", export=["godot"])
    txt = (tmp_path / "g.tres").read_text(encoding="utf8")
    assert txt.startswith('[gd_resource type="SpriteFrames"')
    assert 'path="res://characters/g.png"' in txt
    assert '&"walk_down"' in txt and '&"tool_hammer_left"' in txt
    assert "region = Rect2(0, 512, 64, 64)" in txt  # 1º quadro do walk_up
    assert r["exports"]["godot"]["animations"] == 12


def test_exporta_unity(tmp_path):
    r = s.generate_character(FERREIRO, animations=["walk"], filename="u.png", export=["unity"])
    meta = (tmp_path / "u.png.meta").read_text(encoding="utf8")
    assert "spriteMode: 2" in meta and "filterMode: 0" in meta and "walk_down_0:" in meta
    anim = (tmp_path / "u_unity_anims" / "walk_down.anim").read_text(encoding="utf8")
    assert "m_Sprite" in anim and "m_LoopTime: 1" in anim
    assert anim.count("time: ") == 9
    # os ids do clipe apontam para sprites do .meta
    import re
    ids = set(re.findall(r"fileID: (\d{6,})", anim))
    assert ids and all(f": {i}\n" in meta for i in ids)


def test_exporta_web(tmp_path):
    import json
    s.generate_character(FERREIRO, animations=["walk"], filename="w.png", export=["web"])
    atlas = json.loads((tmp_path / "w.json").read_text(encoding="utf8"))
    assert atlas["meta"]["image"] == "w.png"
    assert len(atlas["animations"]["walk_down"]) == 9
    assert atlas["frames"]["walk_down_0"]["frame"] == {"x": 0, "y": 640, "w": 64, "h": 64}
    html = (tmp_path / "w_demo.html").read_text(encoding="utf8")
    assert '"w.png"' in html and "walk_down" in html


def test_exporta_json_do_site(tmp_path):
    import json
    s.generate_character(FERREIRO, animations=["walk"], filename="st.png", export=["site"])
    doc = json.loads((tmp_path / "st_site.json").read_text(encoding="utf8"))
    assert doc["version"] == 1 and s.from_site_url(doc["url"])["items"][0]["id"] == "body/body"


def test_export_invalido():
    assert "error" in s.generate_character(FERREIRO, export=["xyz"])


# ---------- prévia animada e links antigos ----------
def test_previa_animada_gif():
    import io
    data = s.preview_character(FERREIRO, animation="walk")[0].data
    gif = Image.open(io.BytesIO(data))
    assert gif.format == "GIF" and gif.n_frames > 1 and gif.size == (4 * 64 * 3, 64 * 3)
    parada = Image.open(io.BytesIO(s.preview_character(FERREIRO, animated=False)[0].data))
    assert parada.format == "PNG"


def test_link_com_nomes_antigos():
    r = s.from_site_url("#sex=male&shoulders=Epaulets_gold&wrinkes=Wrinkles_light&legs=Fur_Pants_black")
    assert r["items"] == [{"id": "arms/shoulders/shoulders_epaulets", "color": "gold"},
                          {"id": "head/head_wrinkles", "color": "light"},
                          {"id": "legs/pants/legs_formal", "color": "black"}]
    assert "unresolved" not in r


def test_demo_web_sem_marcadores_sobrando(tmp_path):
    s.generate_character(FERREIRO, animations=["walk"], filename="dm.png", export=["web"])
    html = (tmp_path / "dm_demo.html").read_text(encoding="utf8")
    import re
    assert not re.findall(r"__[A-Z_]+__", html)
    assert 'img.src = "dm.png?v=' in html and "<title>dm · Personagem LPC</title>" in html


# ---------- animações completas ----------
def test_expressao_aparece_no_rosto():
    sem = s.generate_character([{"id": "body/body"}, {"id": "head/heads/human/heads_human_female"}],
                               "female", ["walk"], "e0.png", "compact")
    com = s.generate_character([{"id": "body/body"}, {"id": "head/heads/human/heads_human_female"},
                                {"id": "head/faces/face_angry"}], "female", ["walk"], "e1.png", "compact")
    assert "missing" not in com or "head/faces/face_angry" not in com["missing"]
    assert Image.open(sem["file"]).tobytes() != Image.open(com["file"]).tobytes()


def test_expressao_com_cabeca_que_nao_combina():
    r = s.generate_character([{"id": "body/body"}, {"id": "head/heads/beast/heads_minotaur"},
                              {"id": "head/faces/face_angry"}], animations=["walk"], filename="e2.png")
    assert any("face_angry" in w for w in r["warnings"])


def test_faltas_intencionais_nao_contam():
    assert s.animation_gaps("hair/beards/beards_trimmed", "male") == []   # só falta climb
    assert s.animation_gaps("head/faces/face_angry", "female") == []      # climb e hurt
    assert s.animation_gaps("tools/tool_hammer", "male") == []            # equipamento
    assert "idle" in s.animation_gaps("torso/aprons/torso_aprons_apron", "male")


def test_relatorio_avisa_e_sugere_alternativa():
    r = s.generate_character(FERREIRO, filename="rel.png")
    check = r["animation_check"]
    assert check["complete"] is False
    apron = check["incomplete_items"]["torso/aprons/torso_aprons_apron"]
    assert "idle" in apron["missing"]
    assert "torso/aprons/torso_aprons_overalls" in apron["complete_alternatives"]
    assert check["summary"].startswith("ATENÇÃO")
    assert "tool_hammer" in check["equipment_only_in"]["tools/tool_hammer"]


def test_prefer_complete_troca_item_incompleto():
    r = s.generate_character(FERREIRO, filename="pc.png", prefer_complete=True)
    assert r["replaced"] == [{"from": "torso/aprons/torso_aprons_apron",
                              "to": "torso/aprons/torso_aprons_overalls"}]
    assert r["animation_check"]["complete"] is True
    # o martelo (equipamento) não é trocado
    assert "tools/tool_hammer" in r["animation_check"]["equipment_only_in"]


def test_prefer_complete_mantem_a_variante():
    novo = s._swap_for_complete({"id": "torso/aprons/torso_aprons_apron", "variant": "leather"}, "male")
    assert novo == {"id": "torso/aprons/torso_aprons_overalls", "variant": "leather"}


def test_busca_mostra_completos_primeiro():
    r = s.search_items("apron", body_type="male")
    assert r[0]["complete"] is True and r[-1]["id"] == "torso/aprons/torso_aprons_apron"
    assert "idle" in r[-1]["missing_animations"]
    assert all(x["complete"] for x in s.search_items(category="torso", complete_only=True, limit=30))
    espada = s.search_items("arming", category="weapons")[0]
    assert "slash_128" in espada["equipment_only_in"]


def test_aleatorios_so_com_itens_completos():
    for seed in range(60):
        body = "female" if seed % 2 else "male"
        r = s.random_character(body, seed=seed)
        assert s.animation_report(r["items"], body)["complete"], r["items"]


def test_previa_e_lote_informam_completude(tmp_path):
    note = __import__("json").loads(s.preview_character(FERREIRO)[1])
    assert note["animation_check"].startswith("ATENÇÃO")
    lote = s.generate_batch(2, seed=3, animations=["walk"], layout="compact")
    assert all(c["complete"] for c in lote["characters"])


def test_demo_web_avisa_itens_faltando(tmp_path):
    import json
    s.generate_character(FERREIRO, filename="dw.png", export=["web"])
    atlas = json.loads((tmp_path / "dw.json").read_text(encoding="utf8"))
    assert "Apron" in atlas["meta"]["missing"]["idle"]
    assert "Apron" not in atlas["meta"]["missing"].get("walk", [])
