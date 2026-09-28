"""Testes do MCP. Rode com: python -m pytest -q
Na primeira vez baixam as definições e alguns PNGs do GitHub (precisa de internet)."""
import asyncio

import pytest
from PIL import Image

import server as s

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
                             animations=["walk", "idle", "shoot"], filename="elfa.png")
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
