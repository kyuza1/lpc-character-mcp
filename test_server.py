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
    assert img.height == 3 * 256
    assert set(r["animations"]) == {"walk", "idle", "shoot"}
    assert r["frame"] == 64
    # sem arte no repositório: túnica em "idle", arco fora de "shoot" — deve ser avisado
    assert r["missing"] == {"torso/shirts/torso_clothes_tunic": ["idle"],
                            "weapons/ranged/bow/weapon_ranged_bow_normal": ["walk", "idle"]}


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
