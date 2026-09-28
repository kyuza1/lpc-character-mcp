"""Testes do MCP. Rode com: python -m pytest -q
Na primeira vez baixam as definições e alguns PNGs do GitHub (precisa de internet)."""
import asyncio

import pytest
from PIL import Image

from lpc_character_mcp import links, render
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
    verde = render._layer_image(d, layer, "female", "walk", None, ["forest"])
    vermelha = render._layer_image(d, layer, "female", "walk", None, ["red"])
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
    # a túnica não tem idle; o arco é equipamento e aparece em equipment_only_in
    assert r["missing"] == {"torso/shirts/torso_clothes_tunic": ["idle"]}
    assert "weapons/ranged/bow/weapon_ranged_bow_normal" in r["animation_check"]["equipment_only_in"]


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
    assert a["tool_hammer"]["y"] == render.SHEET_HEIGHT
    assert r["size"] == [9 * 128, render.SHEET_HEIGHT + 4 * 128]


def test_layout_padrao_sem_especiais_tem_tamanho_do_site():
    r = s.generate_character(FERREIRO[:2], filename="p2.png")
    assert r["size"] == [render.SHEET_WIDTH, render.SHEET_HEIGHT]


def test_layout_invalido():
    assert "error" in s.generate_character(FERREIRO, layout="xyz")


def test_split_salva_animacoes_separadas(tmp_path):
    s.generate_character(FERREIRO, animations=["walk", "slash"], filename="sp.png", split=True)
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
    assert a["url"].startswith(links.SITE)


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
    assert "unknown animation" in s.preview_character(FERREIRO, animation="xyz")


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
                     "from_site_url", "to_site_url", "update_definitions", "clear_cache"}


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
    assert r["warnings"] == ["hair/long/hair_long replaced hair/short/hair_plain (same type: hair)"]


def test_aviso_curto_de_item_faltando():
    r = s.generate_character(FERREIRO, filename="curto.png")
    # o avental falta na maioria: aviso curto dizendo onde ele aparece
    assert r["missing"]["torso/aprons/torso_aprons_apron"] == {
        "only_in": ["spellcast", "thrust", "walk", "slash", "shoot", "hurt"]}
    # martelo é equipamento: não entra em missing
    assert "tools/tool_hammer" not in r["missing"]


def test_faltas_intencionais_fora_do_missing():
    r = s.generate_character([{"id": "body/body"}, {"id": "head/heads/human/heads_human_male"},
                              {"id": "hair/beards/beards_trimmed"}], filename="barba.png")
    assert "hair/beards/beards_trimmed" not in r.get("missing", {})
    assert r["animation_check"]["complete"] is True


def test_downloads_em_paralelo(monkeypatch):
    chamadas = []
    monkeypatch.setattr(render, "_prefetch", lambda rels: chamadas.append(len(rels)))
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
    assert "region = Rect2(64, 512, 64, 64)" in txt  # walk_up começa no quadro 1 (o 0 é a pose parada)
    assert r["exports"]["godot"]["animations"] == 12


def test_exporta_unity(tmp_path):
    s.generate_character(FERREIRO, animations=["walk"], filename="u.png", export=["unity"])
    meta = (tmp_path / "u.png.meta").read_text(encoding="utf8")
    assert "spriteMode: 2" in meta and "filterMode: 0" in meta and "walk_down_0:" in meta
    anim = (tmp_path / "u_unity_anims" / "walk_down.anim").read_text(encoding="utf8")
    assert "m_Sprite" in anim and "m_LoopTime: 1" in anim
    assert anim.count("time: ") == 8  # walk: quadros 1 a 8, como no gerador oficial
    # os ids do clipe apontam para sprites do .meta
    import re
    ids = set(re.findall(r"fileID: (\d{6,})", anim))
    assert ids and all(f": {i}\n" in meta for i in ids)


def test_exporta_web(tmp_path):
    import json
    s.generate_character(FERREIRO, animations=["walk"], filename="w.png", export=["web"])
    atlas = json.loads((tmp_path / "w.json").read_text(encoding="utf8"))
    assert atlas["meta"]["image"] == "w.png"
    assert len(atlas["animations"]["walk_down"]) == 8
    assert atlas["frames"]["walk_down_0"]["frame"] == {"x": 64, "y": 640, "w": 64, "h": 64}
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
    assert 'img.src = "dm.png?v=' in html and "<title>dm · LPC character</title>" in html
    assert "__T:" not in html and '<html lang="en">' in html


def test_demo_web_em_portugues(tmp_path, monkeypatch):
    monkeypatch.setenv("LPC_LANG", "pt")
    s.generate_character(FERREIRO, animations=["walk"], filename="dp.png", export=["web"])
    html = (tmp_path / "dp_demo.html").read_text(encoding="utf8")
    assert "__T:" not in html and "<span>Animação</span>" in html and 'lang="pt-BR"' in html


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
    assert check["summary"].startswith("WARNING")
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
    assert note["animation_check"].startswith("WARNING")
    lote = s.generate_batch(2, seed=3, animations=["walk"], layout="compact")
    assert all(c["complete"] for c in lote["characters"])


def test_demo_web_avisa_itens_faltando(tmp_path):
    import json
    s.generate_character(FERREIRO, filename="dw.png", export=["web"])
    atlas = json.loads((tmp_path / "dw.json").read_text(encoding="utf8"))
    assert atlas["meta"]["missing"]["idle"] == ["Apron"]  # martelo (equipamento) não entra
    assert "Apron" not in atlas["meta"]["missing"].get("walk", [])


# ---------- outros corpos ----------
@pytest.mark.parametrize("body", ["teen", "child", "muscular", "pregnant"])
def test_outros_corpos_geram_com_tronco(body):
    for seed in range(5):
        r = s.random_character(body, seed=seed)
        assert any(i["id"].startswith("head/heads/") for i in r["items"])
        assert any(i["id"].startswith("torso/") for i in r["items"]), r["items"]
        g = s.generate_character(r["items"], body, ["walk"], f"{body}{seed}.png", "compact")
        assert "error" not in g


def test_limitacao_do_corpo_separada_das_pecas():
    rep = s.animation_report([{"id": "body/body"}, {"id": "head/heads/human/heads_human_male"},
                              {"id": "hair/short/hair_plain"}], "muscular")
    assert rep["body_missing"] == ["shoot", "climb", "emote", "combat_idle", "backslash", "halfslash"]
    assert rep["incomplete_items"] == {}  # o cabelo não é culpado pelo que o corpo não tem
    assert "the LPC muscular body has no" in rep["summary"]
    assert "prefer_complete" not in rep["summary"]  # nada a trocar


def test_corpo_e_cabeca_nunca_sao_trocados():
    assert s.complete_alternatives("body/body", "muscular") == []
    assert s.complete_alternatives("head/heads/human/heads_human_male", "male") == []
    r = s.generate_character([{"id": "body/body"}, {"id": "head/heads/human/heads_human_male"}],
                             "muscular", ["walk"], "nt.png", prefer_complete=True)
    assert "replaced" not in r


# ---------- salvar no projeto do jogo ----------
def test_output_dir_salva_na_pasta_pedida(tmp_path):
    destino = tmp_path / "meu_jogo" / "sprites"
    r = s.generate_character(FERREIRO, animations=["walk"], filename="npc.png", output_dir=str(destino))
    assert (destino / "npc.png").exists() and (destino / "npc_credits.txt").exists()
    assert r["file"] == str(destino / "npc.png")


def test_godot_detecta_projeto_e_usa_res_path(tmp_path):
    (tmp_path / "project.godot").write_text("config_version=5\n")
    r = s.generate_character(FERREIRO, animations=["walk"], filename="npc.png", export=["godot"],
                             output_dir=str(tmp_path / "art" / "npcs"))
    tres = (tmp_path / "art" / "npcs" / "npc.tres").read_text(encoding="utf8")
    assert 'path="res://art/npcs/npc.png"' in tres
    assert r["exports"]["godot"]["res_path"] == "res://art/npcs/npc.tres"


def test_godot_fora_de_projeto_usa_padrao(tmp_path):
    r = s.generate_character(FERREIRO, animations=["walk"], filename="npc.png", export=["godot"])
    assert r["exports"]["godot"]["res_path"] == "res://characters/npc.tres"


def test_lote_com_output_dir(tmp_path):
    s.generate_batch(2, seed=1, animations=["walk"], layout="compact", output_dir=str(tmp_path / "vila"))
    assert all((tmp_path / "vila" / f"npc_0{n}.png").exists() for n in (1, 2))


def test_unity_gera_controller_com_todos_os_clipes(tmp_path):
    import re
    s.generate_character(FERREIRO, animations=["walk", "idle", "slash"], filename="uc.png", export=["unity"])
    ctrl = (tmp_path / "uc.controller").read_text(encoding="utf8")
    clips = sorted(p.stem for p in (tmp_path / "uc_unity_anims").glob("*.anim"))
    estados = sorted(re.findall(r"m_Name: (\w+)\n  m_Speed", ctrl))
    assert estados == clips and "idle_down" in estados
    # cada estado aponta para o guid do .meta do clipe correspondente
    for nome in clips:
        meta = (tmp_path / "uc_unity_anims" / f"{nome}.anim.meta").read_text(encoding="utf8")
        guid = re.search(r"guid: (\w+)", meta).group(1)
        assert f"guid: {guid}, type: 2" in ctrl
    assert "mainObjectFileID: 9100000" in (tmp_path / "uc.controller.meta").read_text(encoding="utf8")


# ---------- cache ----------
def test_limpa_cache(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    (cache / "body" / "x").mkdir(parents=True)
    (cache / "body" / "x" / "walk.png").write_bytes(b"x" * 2048)
    (cache / "_files_abc.txt").write_text("lista")
    monkeypatch.setattr(s, "CACHE", cache)
    previa = s.clear_cache(dry_run=True)
    assert previa["files"] == 1 and (cache / "body" / "x" / "walk.png").exists()
    r = s.clear_cache()
    assert r["files"] == 1 and not (cache / "body").exists()
    assert (cache / "_files_abc.txt").exists()  # arquivos internos ficam
    assert "clear_cache" in {t.name for t in asyncio.run(s.mcp.list_tools())}


# ---------- atualização e lote ----------
def _git(*args, cwd):
    import subprocess
    return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=cwd,
                          check=True, capture_output=True, text=True).stdout.strip()


def _repos(tmp_path):
    """Um "origin" com 2 commits e um clone parado no 1º (definições desatualizadas)."""
    origin, local = tmp_path / "origin", tmp_path / "local"
    origin.mkdir()
    _git("init", "-q", "-b", "master", cwd=origin)
    _git("commit", "-q", "--allow-empty", "-m", "v1", cwd=origin)
    _git("clone", "-q", str(origin), str(local), cwd=tmp_path)
    _git("commit", "-q", "--allow-empty", "-m", "v2", cwd=origin)
    return origin, local


def test_update_definitions_atualiza(tmp_path, monkeypatch):
    origin, local = _repos(tmp_path)
    recargas = []
    monkeypatch.setattr(s, "REPO", local)
    monkeypatch.setattr(s.catalog, "reload", lambda: recargas.append("catalog"))
    monkeypatch.setattr(s.render, "reset_caches", lambda: recargas.append("render"))
    r = s.update_definitions()
    assert r["updated"] is True and r["to"] == _git("rev-parse", "HEAD", cwd=origin)[:10]
    assert recargas == ["catalog", "render"]
    # de novo: já está na versão mais nova
    assert s.update_definitions()["updated"] is False and len(recargas) == 2


def test_update_definitions_limpa_imagens_se_pedido(tmp_path, monkeypatch):
    _, local = _repos(tmp_path)
    cache = tmp_path / "cache"
    (cache / "body").mkdir(parents=True)
    (cache / "body" / "walk.png").write_bytes(b"x")
    monkeypatch.setattr(s, "REPO", local)
    monkeypatch.setattr(s, "CACHE", cache)
    monkeypatch.setattr(s.catalog, "reload", lambda: None)
    monkeypatch.setattr(s.render, "reset_caches", lambda: None)
    r = s.update_definitions(clear_image_cache=True)
    assert r["image_cache_cleared"] is True and not (cache / "body").exists()


def test_reload_do_catalogo_mantem_o_mesmo_dicionario():
    antes = s.ITEMS
    s.catalog.reload()
    assert s.ITEMS is antes and "body/body" in antes


def test_lote_com_corpo_invalido_informa_erro():
    r = s.generate_batch(2, body_types=["robot"], seed=1, animations=["walk"])
    assert r["count"] == 2 and all("error" in c for c in r["characters"])


# ---------- linha de comando ----------
@pytest.mark.parametrize("flag, texto", [
    (["--version"], "lpc-character-mcp 0."),
    (["--help"], "--setup"),
    (["--where"], "characters:"),
    (["--setup"], "lpc-character-mcp ready:"),
    (["--clear-cache", "9999"], "files deleted"),
])
def test_cli(flag, texto, capsys):
    from lpc_character_mcp import cli
    cli.main(flag)
    assert texto in capsys.readouterr().out


# ---------- idioma ----------
def test_mensagens_em_portugues_com_lpc_lang(monkeypatch, capsys):
    monkeypatch.setenv("LPC_LANG", "pt-BR")
    rep = s.animation_report([{"id": "body/body"}, {"id": "torso/aprons/torso_aprons_apron"}], "male")
    assert rep["summary"].startswith("ATENÇÃO") and "Apron não tem" in rep["summary"]
    r = s.generate_character([{"id": "body/body"}, {"id": "hair/short/hair_plain"},
                              {"id": "hair/long/hair_long"}], animations=["walk"], filename="pt.png")
    assert "substituiu" in r["warnings"][0]
    assert "Autores:" in open(r["credits"]["file"], encoding="utf8").read()
    from lpc_character_mcp import cli
    cli.main(["--where"])
    assert "personagens:" in capsys.readouterr().out


def test_mensagens_em_ingles_por_padrao(monkeypatch):
    monkeypatch.delenv("LPC_LANG", raising=False)
    rep = s.animation_report([{"id": "body/body"}], "male")
    assert rep["summary"] == "All animations are complete for every item."
    from lpc_character_mcp.i18n import MESSAGES
    assert all(set(v) == {"en", "pt"} for v in MESSAGES.values())  # toda mensagem nos 2 idiomas


# ---------- publicação ----------
def test_versoes_iguais_em_todos_os_arquivos():
    import json
    from pathlib import Path
    from lpc_character_mcp import __version__
    root = Path(__file__).parent.parent
    server = json.loads((root / "server.json").read_text(encoding="utf8"))
    manifest = json.loads((root / "mcpb" / "manifest.json").read_text(encoding="utf8"))
    assert server["version"] == server["packages"][0]["version"] == __version__
    assert manifest["version"] == __version__
    assert manifest["server"]["mcp_config"]["args"] == [f"lpc-character-mcp=={__version__}"]
    # o registro confere o dono do pacote por esta linha no README do PyPI
    assert f"mcp-name: {server['name']}" in (root / "README.md").read_text(encoding="utf8")
    # o manifesto do MCPB lista as mesmas ferramentas do servidor
    assert {t["name"] for t in manifest["tools"]} == {t.name for t in asyncio.run(s.mcp.list_tools())}


# ---------- ordem dos quadros e animações extras ----------
def test_sequencias_iguais_ao_gerador_oficial(tmp_path):
    import json
    s.generate_character(FERREIRO, animations=["idle", "sit", "slash"], filename="cy.png", export=["web"])
    a = json.loads((tmp_path / "cy.json").read_text(encoding="utf8"))
    frame_x = lambda clip: [a["frames"][k]["frame"]["x"] // a["frames"][k]["frame"]["w"] for k in a["animations"][clip]]
    assert frame_x("idle_down") == [0, 0, 1]
    assert frame_x("sit_left") == [0] * 5 + [1] * 5 + [2] * 5
    assert frame_x("slash_up") == [0, 1, 2, 3, 4, 5]


def test_golpe_de_uma_mao_e_regar(tmp_path):
    import json
    base = [{"id": "body/body"}, {"id": "head/heads/human/heads_human_male"}]
    s.generate_character(base, animations=["backslash", "thrust"], filename="ex.png", export=["web", "godot"])
    a = json.loads((tmp_path / "ex.json").read_text(encoding="utf8"))
    assert "1h_slash_down" in a["animations"] and len(a["animations"]["1h_slash_down"]) == 7
    assert len(a["animations"]["backslash_down"]) == 12  # pula o quadro 6
    assert "watering_down" not in a["animations"]  # só com o regador
    assert '&"1h_slash_left"' in (tmp_path / "ex.tres").read_text(encoding="utf8")
    s.generate_character(base + [{"id": "tools/tool_watering_can"}], animations=["thrust"],
                         filename="rg.png", export=["web"])
    a = json.loads((tmp_path / "rg.json").read_text(encoding="utf8"))
    xs = [a["frames"][k]["frame"]["x"] // 64 for k in a["animations"]["watering_down"]]
    assert xs == [0, 1, 4, 4, 4, 4, 5]


# ---------- licenças ----------
def test_familia_de_licenca():
    from lpc_character_mcp.catalog import license_family
    assert license_family("OGA-BY-3.0") == license_family("OGA-BY 3.0+") == "OGA-BY"
    assert license_family("CC-BY-SA 4.0") == "CC-BY-SA" and license_family("CC-BY 3.0+") == "CC-BY"


def test_filtro_de_licenca_na_busca_e_no_sorteio():
    from lpc_character_mcp.catalog import item_license_ok
    safe = s.search_items(licenses=["CC0", "OGA-BY"], body_type="male", limit=999)
    assert safe and all(x["drm_safe"] for x in safe)
    assert len(safe) < len(s.search_items(body_type="male", limit=999))
    for seed in range(10):
        r = s.random_character("female", seed=seed, licenses=["CC0", "OGA-BY"])
        assert all(item_license_ok(i["id"], ["CC0", "OGA-BY"], "female") for i in r["items"])


def test_license_check_no_resultado():
    r = s.random_character("male", seed=4, licenses=["CC0", "OGA-BY"])
    g = s.generate_character(r["items"], animations=["walk"], filename="lc.png", licenses=["CC0", "OGA-BY"])
    assert g["license_check"]["drm_safe"] is True and "warnings" not in g
    from lpc_character_mcp.catalog import license_report
    rep = license_report([{"file": "x", "licenses": ["CC-BY-SA 3.0", "GPL 3.0"]}])
    assert rep["drm_safe"] is False and rep["share_alike_required"] is True
    assert rep["not_drm_safe_parts"] == ["x"]


def test_aviso_de_item_fora_das_licencas():
    from lpc_character_mcp.catalog import item_license_ok
    fora = next(i for i in s.ITEMS if i.startswith("torso/") and "male" in s._item_bodies(s.ITEMS[i])
                and not item_license_ok(i, ["CC0"], "male"))
    g = s.generate_character([{"id": "body/body"}, {"id": fora}], animations=["walk"],
                             filename="lf.png", licenses=["CC0"])
    assert any(fora in w for w in g["warnings"])


# ---------- créditos, zip e json do site ----------
def test_texto_pronto_de_creditos(tmp_path):
    r = s.generate_character(FERREIRO, animations=["walk"], filename="ct.png")
    st = r["credits"]["statement"]
    assert "Sprites by: " in st and "Stephen Challener (Redshrike)" in st and "ct_credits.txt" in st
    assert st in (tmp_path / "ct_credits.txt").read_text(encoding="utf8")


def test_zip_com_tudo(tmp_path):
    import zipfile
    r = s.generate_character(FERREIRO, animations=["walk"], filename="zp.png",
                             export=["godot", "web"], split=["animation"], zip=True)
    nomes = zipfile.ZipFile(r["zip"]).namelist()
    assert {"zp.png", "zp.tres", "zp.json", "zp_demo.html", "zp_credits.txt", "zp_anims/walk.png"} <= set(nomes)


def test_importa_json_do_site():
    import json
    v1 = json.dumps({"version": 1, "url": URL})
    assert s.from_site_url(v1)["items"][0] == {"id": "body/body", "color": "light"}
    v2 = json.dumps({"version": 2, "bodyType": "female", "selections": {
        "body": {"itemId": "body/body", "recolor": "olive"},
        "apron": {"itemId": "torso/aprons/torso_aprons_apron", "variant": "leather"}}})
    r = s.from_site_url(v2)
    assert r["body_type"] == "female"
    assert r["items"] == [{"id": "body/body", "color": "olive"},
                          {"id": "torso/aprons/torso_aprons_apron", "variant": "leather"}]
